# MARÉE — schémas d’architecture

_Ce document rassemble les schémas du système, du plus large au plus fin.
Chaque schéma est un bloc Mermaid : il se rend tel quel dans GitHub,
VS Code, Obsidian ou Notion, et reste lisible dans un diff._

Date : 2026-11-04

> Convention de lecture : les nœuds disent **ce qui se passe**, la légende
> sous chaque schéma dit **où le vérifier dans le code**. Un schéma qui ne
> renvoie pas à un fichier n’aurait pas sa place ici.

---

## Sommaire

| Niveau | Schéma | Question à laquelle il répond |
|---|---|---|
| 0 | Contexte | Qui parle à qui ? |
| 1 | Couches / ports | Pourquoi c’est remplaçable ? |
| 2 | Un tick | Que se passe-t-il en 10 s simulées ? |
| 3 | Graphe LangGraph | Comment un agent décide ? |
| 3 bis | Déclencheurs | Quand décide-t-il ? |
| 4 | Modèle mémoire | De quoi se souvient-il ? |
| 4 bis | Séquence mémoire | Comment la mémoire est-elle lue et écrite ? |
| 4 ter | Cloisonnement | Pourquoi ne peut-il pas tricher ? |
| 5 | Pipeline RAG | Que lit-il, et sous quels filtres ? |
| 5 bis | Pas de base vectorielle | Pourquoi un fichier suffit ? |
| 6 | Événements / Kafka | Qu’est-ce qui circule ? |
| 6 bis | Enveloppe d’événement | Que porte chaque fait ? |
| 7 | Journal / rejeu | Comment prouve-t-on tout ça ? |
| 7 bis | Chaîne causale | Pourquoi la foule a-t-elle basculé ? |

---

## Niveau 0 — Contexte : qui parle à qui

```mermaid
flowchart LR
  CFG["Hydra YAML<br/>configs/"] --> SIM["Moteur MARÉE<br/>Simulation"]
  SIM -->|"chat + embed"| LLM["llama.cpp router<br/>gemma4-e2b · qwen3-0.6b · bge-m3"]
  SIM -->|"positions, pas de 0,05 s"| PHY["JuPedSim 1.4"]
  SIM -->|"publish : faits"| RP["Redpanda<br/>API Kafka"]
  SIM -->|"append-only"| J["Journal JSONL<br/>runs/id/events.jsonl"]
  J --> CLI["CLI<br/>replay · trace · state · query"]
  RP --> WS["maree serve / live<br/>WebSocket 8765"]
  J --> WS
  WS --> UI["Godot · Observatoire web"]
  UI -->|"injections live"| SIM
```

**Où le vérifier** : `src/maree/cli.py` (`_build`), `docker-compose.yml`,
`docs/architecture-v2.md` §11.

---

## Niveau 1 — Couches et ports/adaptateurs

```mermaid
flowchart TB
  subgraph DOM["domain/ — aucune dépendance externe"]
    EV["events.py"]
    BE["beliefs.py"]
    IN["intentions.py"]
    GE["geometry.py"]
    CL["clock.py"]
  end

  subgraph PORT["ports/ — Protocol, aucun import concret"]
    P1["LLMPort"]
    P2["CrowdPhysics"]
    P3["JournalPort"]
    P4["EventBus"]
    P5["MemoryPort"]
    P6["RetrieverPort"]
  end

  subgraph ADP["adapters/ — implémentations"]
    A1["LlamaCppLLM"]
    A2["JuPedSimPhysics"]
    A3["JsonlJournal"]
    A4["RedpandaBus / InMemoryBus"]
    A5["EventSourcedMemory"]
    A6["FaissRetriever"]
  end

  subgraph ENG["engine/"]
    SI["Simulation"]
    RE["replay.py"]
    TRC["trace.py"]
  end

  subgraph AG["agents/"]
    PR["profiles.py"]
    TG["triggers.py"]
    RU["rules.py"]
    GR["graph.py LangGraph"]
    PA["parsing.py"]
  end

  SI --> P2
  SI --> P3
  SI --> P4
  GR --> P1
  GR --> P5
  GR --> P6
  SI --> GR
  SI --> TG
  SI --> RU
  GR --> PA

  P1 -.-> A1
  P2 -.-> A2
  P3 -.-> A3
  P4 -.-> A4
  P5 -.-> A5
  P6 -.-> A6
```

**Où le vérifier** : `src/maree/ports/__init__.py` pour les contrats ;
`src/maree/adapters/` pour les implémentations. Le domaine ne connaît aucun
outil : c’est ce qui permet les tests sans GPU, sans Kafka, sans JuPedSim.

---

## Niveau 2 — Un tick, pas à pas

```mermaid
flowchart TD
  S(["tick N commence"]) --> A1["1 · Physique<br/>200 pas JuPedSim de 0,05 s"]
  A1 --> A2["2 · Évacuations détectées<br/>agent.evacuated"]
  A2 --> A3["3 · Événements du monde<br/>fumée, fermeture, annonce"]
  A3 --> A4["4 · Perception figée<br/>un seul instant T pour tous"]
  A4 --> A5{"5 · should_decide ?"}
  A5 -->|oui| A6["6 · Décision<br/>règles ou graphe LangGraph"]
  A5 -->|non| A7["garde son intention"]
  A6 --> A8["7 · _apply<br/>destination, croyances, mémoire"]
  A7 --> A9
  A8 --> A9["8 · Diffusion des messages<br/>_diffuse"]
  A9 --> A10["9 · Indicateurs I1–I7<br/>+ plage de seq"]
  A10 --> A11["10 · state.json<br/>+ world.snapshot"]
  A11 --> A12{"11 · chroniqueur dû ?"}
  A12 -->|oui| A13["Narration LLM<br/>+ validation anti-hallucination"]
  A12 -->|non| A14
  A13 --> A14{"12 · tout le monde sorti ?"}
  A14 -->|oui| Z(["fin du run"])
  A14 -->|non| A15["attente tick_delay"]
  A15 --> S
```

**Où le vérifier** : `src/maree/engine/simulation.py`, boucle `run()`
(lignes ~695-830). L’ordre n’est pas cosmétique : la perception est figée
avant les décisions, et les messages sont diffusés après leur application.

---

## Niveau 3 — Le graphe de décision (LangGraph)

```mermaid
flowchart LR
  ST(["START"]) --> R["recall<br/>5 souvenirs + croyances"]
  R --> Q{"_needs_rag ?"}
  Q -->|"fumée, annonce ou sortie fermée<br/>ou confiance &lt; 0,5"| RET["retrieve<br/>RAG top-3 filtré"]
  Q -->|non| DEC
  RET --> DEC{"_decide<br/>tier small ?"}
  DEC -->|small| SC["prompt fermé<br/>RESTER | SORTIR<br/>parse_choice"]
  DEC -->|big| BG["prompt JSON<br/>parse_decision"]
  SC --> V["validate<br/>_to_intention"]
  BG --> V
  V -->|valide| OK["Intention"]
  V -->|"invalide : unparseable,<br/>unknown_exit, out_of_role…"| FB["repli règles<br/>fallback_reason nommée"]
  OK --> E(["END"])
  FB --> E
```

**Où le vérifier** : `src/maree/agents/graph.py` (`_build`, `_recall`,
`_needs_rag`, `_retrieve`, `_decide`, `_validate`).

---

## Niveau 3 bis — Les déclencheurs, par ordre de priorité

```mermaid
flowchart TD
  START(["should_decide"]) --> T1{"sortie crue fermée<br/>et pas déjà traitée ?"}
  T1 -->|oui| D1["sortie_fermee · urgence 1,0"]
  T1 -->|non| T2{"fumée visible<br/>et pas déjà traitée ?"}
  T2 -->|oui| D2["fumee_visible · 0,9"]
  T2 -->|non| T3{"annonce nouvelle ?"}
  T3 -->|oui| D3["annonce · 0,85"]
  T3 -->|non| T4{"message jamais vu ?"}
  T4 -->|oui| D4["message:sender · 0,7"]
  T4 -->|non| T5{"proche disparu<br/>et pas déjà traité ?"}
  T5 -->|oui| D5["proche_disparu · 0,75"]
  T5 -->|non| T6{"densité ≥ 3 pers/m² ?"}
  T6 -->|oui| D6["densite_critique · 0,6"]
  T6 -->|non| T7{"jamais décidé ?"}
  T7 -->|oui| D7["premiere_decision · 0,5"]
  T7 -->|non| T8{"inactivité ≥ max_idle, cadence ?"}
  T8 -->|oui| D8["periodique · 0,2"]
  T8 -->|non| N["rien_de_nouveau"]
```

**Où le vérifier** : `src/maree/agents/triggers.py`. Les signaux persistants
sont des **fronts** : `known_signals` empêche la fumée, visible jusqu’à la
fin, de redéclencher une décision à chaque tick.

---

## Niveau 4 — Le modèle de mémoire

```mermaid
classDiagram
  class MemoryPort {
    <<interface>>
    +remember(agent_id, episode)
    +recall(agent_id, query, k, tick)
    +beliefs(agent_id)
    +trust(agent_id)
    +consolidate(agent_id, tick)
  }

  class EventSourcedMemory {
    -_mem
    -_n_exits
    -_window
    +read_all(principal)
    +all_beliefs(principal)
    +size(agent_id)
  }

  class NullMemory {
    +recall() aucun épisode
  }

  class AgentMemory {
    +episodes
    +beliefs
    +trust
  }

  class Episode {
    +tick
    +kind
    +content
    +source
    +salience
    +tags
  }

  class BeliefTable {
    +exits
    +danger
    +confidence(exit_id)
    +best()
    +distribution(n)
    +entropy(n)
    +set(exit_id, confidence, source, tick)
    +reinforce(exit_id, delta, source, tick)
    +decay(factor, floor)
    +snapshot()
  }

  class ExitBelief {
    +exit_id
    +confidence
    +source
    +tick
  }

  MemoryPort <|.. EventSourcedMemory
  MemoryPort <|.. NullMemory
  EventSourcedMemory --> AgentMemory
  AgentMemory --> Episode
  AgentMemory --> BeliefTable
  BeliefTable --> ExitBelief
```

**Où le vérifier** : `src/maree/memory/store.py`,
`src/maree/domain/beliefs.py`, `src/maree/ports/__init__.py`.
`kind ∈ {vu, entendu, dit, decide, resume}`. Le champ `trust` existe dans le
contrat mais n’est pas encore branché à la décision — c’est une extension,
pas un mécanisme actif.

---

## Niveau 4 bis — Cycle de vie d’une mémoire, sur une décision

```mermaid
sequenceDiagram
  autonumber
  participant S as Simulation
  participant G as DecisionGraph
  participant M as EventSourcedMemory
  participant L as LLM

  S->>S: perception figée à T
  S->>G: decide(agent, prof, percept, trigger)
  G->>M: recall(A19, query, k=5, tick)
  M-->>G: 5 épisodes scorés
  G->>M: beliefs(A19)
  M-->>G: snapshot des croyances
  G->>L: prompt = persona + croyances + souvenirs + RAG
  L-->>G: sortie brute
  G->>G: parse puis validate
  G-->>S: intention ou repli règles
  S->>M: remember(decide)
  S->>M: remember(vu) si fumée
  S->>M: consolidate(tick)
  M->>M: si > window : 1 résumé + 12 récents
  S->>S: beliefs.decay(0.92) puis set(cible)
```

**Où le vérifier** : `DecisionGraph._recall` et `Simulation._apply`. L’écriture
de croyance passe par la **décision**, jamais directement par un message reçu :
un message entre en mémoire épisodique et dans le prompt ; la décision
suivante l’adopte ou non.

---

## Niveau 4 ter — Cloisonnement, la garantie centrale

```mermaid
flowchart LR
  subgraph MEM["EventSourcedMemory._mem"]
    A01["A01<br/>épisodes · croyances · trust"]
    A02["A02<br/>épisodes · croyances · trust"]
    A19["A19<br/>épisodes · croyances · trust"]
  end

  AG["Agent A19"] -->|"recall(A19)"| A19
  AG -.->|"interdit"| A01
  NAR["narrateur"] -->|"read_all('narrator')"| MEM
  ANA["analyste"] -->|"read_all('analyst')"| MEM
  X["tout autre principal"] -->|"read_all('A19')"| KO["PermissionError"]
```

**Où le vérifier** : `tests/test_memory.py`, testé par propriété (Hypothesis,
50 exemples). Sans cette garantie, un visiteur « saurait » ce qu’un habitué
sait, et l’expérience ne mesurerait plus la circulation d’une croyance.

---

## Niveau 5 — Le pipeline RAG

```mermaid
flowchart LR
  P["Perception + trigger"] --> Q["_query_for()<br/>évacuation + fumée + messages"]
  Q --> N{"_needs_rag ?"}
  N -->|"signal fort ou confiance &lt; 0,5"| E["embed bge-m3<br/>via LLMPort"]
  N -->|non| S["prompt sans RAG"]
  E --> F["filtres AVANT recherche<br/>collections du profil<br/>available_tick ≤ tick<br/>allowed_profiles"]
  F --> I["FAISS IndexFlatIP<br/>215 vecteurs centrés"]
  I --> T["top-k = 3"]
  T --> C{"score de tête &lt; 0,17 ?"}
  C -->|oui| D["rag.suspect journalisé<br/>drapeau, pas filtre"]
  C -->|non| INJ
  D --> INJ["injection<br/>Extraits du guide"]
  INJ --> PR["prompt LLM"]
  S --> PR
```

**Où le vérifier** : `src/maree/adapters/retrieval/faiss_corpus.py`,
`configs/rag/bge_m3_faiss.yaml`. Le centrage sur la moyenne du corpus n’est
pas un détail : il fait passer la précision@1 de 0,17 à 0,73.

---

## Niveau 5 bis — Pourquoi pas de base vectorielle

```mermaid
flowchart TB
  C["Corpus : 215 passages annotés"] --> V["vectors.npy<br/>215 × 1024 float32 ≈ 0,9 Mo"]
  V --> M["mean.npy<br/>centrage d’anisotropie"]
  M --> I["FAISS IndexFlatIP<br/>recherche exacte"]
  I --> R["top-k en mémoire<br/>moins de 1 ms"]
  R --> J["décision"]
  X["Vector DB<br/>conteneur · réseau · auth · backup"] -.->|"écarté : 0,9 Mo ne le justifie pas"| R
```

**Où le vérifier** : `docs/architecture-v2.md` §9 et §10. Le corpus est figé,
annoté, et le seul traitement qui compte (le centrage) tiendrait en trois
lignes de numpy.

---

## Niveau 6 — Les événements, du moteur jusqu’aux consommateurs

```mermaid
flowchart LR
  EM["_emit()"] --> VA{"validate()<br/>forme + temps"}
  VA -->|invalide| DLQ["dlq.invalid"]
  VA -->|valide| J["journal JSONL<br/>source de vérité"]
  J --> TF["TOPIC_FOR"]
  TF --> W["world.events<br/>run · fumée · fermeture · annonce · injection · préhistoire"]
  TF --> D["agent.decisions<br/>décision · évacué · incident · rag.suspect · violation"]
  TF --> SO["agent.social<br/>message.sent · message.heard · belief"]
  TF --> MI["metrics.indicators<br/>I1–I7 par tick"]
  TF --> NA["narrative.generated<br/>récit validé"]
  W --> C["maree serve / live<br/>WebSocket"]
  D --> C
  SO --> C
  MI --> C
  NA --> C
  C --> UI["Godot · Web"]
  J --> RP["maree replay<br/>sans bus"]
```

**Où le vérifier** : `TOPIC_FOR` dans `src/maree/engine/simulation.py`.
Ne sont **pas** publiés : `world.snapshot` (61 à 89 % des octets d’un run) et
`tick`. Le bus transporte des **faits**, pas de l’**état** ; le journal reste
la source de vérité, et un broker mort ne tue pas un run rejouable.

---

## Niveau 6 bis — Enveloppe d’un événement

```mermaid
classDiagram
  class Event {
    +seq
    +run_id
    +type
    +t_prod
    +t_trait
    +t_real
    +causation_id
    +correlation_id
    +schema_version
    +data
    +id()
    +child()
    +to_dict()
    +from_dict(d)
  }
  class EventType {
    <<enumeration>>
    RUN_STARTED
    RUN_ENDED
    TICK
    SNAPSHOT
    WORLD_SMOKE
    EXIT_CLOSED
    ANNOUNCEMENT
    INJECTION
    MEMORY_SEEDED
    RAG_SUSPECT
    DECISION
    EVACUATED
    BELIEF_UPDATED
    MESSAGE_SENT
    MESSAGE_HEARD
    INCIDENT
    INDICATORS
    NARRATIVE
    TEMPORAL_VIOLATION
    INVALID
  }
  Event --> EventType
```

**Où le vérifier** : `src/maree/domain/events.py`. `t_prod` est le tick de
production, `t_trait` celui du traitement ; `causation_id` est rempli
mécaniquement par `Event.child()`, jamais à la main.

---

## Niveau 7 — Journal, rejeu et trace

```mermaid
flowchart TB
  RUN["maree run"] --> J["runs/id/events.jsonl"]
  J --> RP["maree replay"]
  J --> TR["maree trace"]
  J --> ST["maree state<br/>state.json"]
  J --> Q["maree query<br/>DuckDB"]

  RP --> P1["re-parse selon le tier<br/>parse_choice / parse_decision"]
  P1 --> P2["parsed → intention<br/>normalisations connues"]
  P2 --> P3["hash des indicateurs<br/>+ narrations revalidées"]

  TR --> T1["variation max d’un indicateur"]
  T1 --> T2["fenêtre de ticks précédents"]
  T2 --> T3["chaînes causales<br/>causation_id → racine"]

  J --> SRV["maree serve<br/>diffusion WebSocket"]
  SRV --> GD["Godot · Web"]
```

**Où le vérifier** : `src/maree/engine/replay.py`,
`src/maree/engine/trace.py`, `src/maree/cli.py`. Le rejeu ne fait **aucun**
appel LLM ni Kafka ; un journal sans `run.ended` est refusé, pas « réparé ».

---

## Niveau 7 bis — La chaîne causale (B4)

```mermaid
flowchart LR
  SM["t6 · world.smoke<br/>seq 120"] --> DE["t6 · A01 agent.decision<br/>cause = smoke"]
  DE --> BE["t6 · agent.belief<br/>cause = décision"]
  DE --> MS["t6 · agent.message.sent<br/>cause = décision"]
  MS --> MH["t6 · agent.message.heard<br/>A04 · cause = sent"]
  MH --> DE2["t7 · A04 agent.decision<br/>cause = heard"]
  DE2 --> EV["t9 · agent.evacuated<br/>cause = décision"]
```

**Où le vérifier** : `src/maree/engine/trace.py`. `correlation_id` est la
racine de toute la chaîne ; `ancestors()` la remonte sans boucler, et la CLI
`maree trace` l’affiche tick par tick.

---

## Ce que ces schémas ne disent pas

Trois limites, écrites ici plutôt que découvertes en soutenance :

- **Le store mémoire vit en RAM.** Le journal contient de quoi reconstruire
  les épisodes, mais `EventSourcedMemory` n’est pas rechargé depuis le
  journal au démarrage : le nom est prospectif.
- **`control.commands` n’est pas utilisé par le moteur.** Les injections
  arrivent par WebSocket (`maree live`) et sont journalisées comme
  `control.injection` dans `world.events`. Le topic existe dans le
  `docker-compose` et le `Makefile` pour un pilotage externe, pas encore
  branché.
- **La mémoire sociale (`trust`) est un contrat sans effet.** Le champ est
  stocké et cloisonné, mais aucune décision ne le lit aujourd’hui.
