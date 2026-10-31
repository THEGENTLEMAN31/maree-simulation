# MARÉE — foule et évacuation interprétative

> Monde 02 · Fête des Lanternes de Port-Aubel · esplanade du quai, 60 × 40 m.
> Soixante personnes, trois sorties, une fumée près de la scène.

MARÉE simule une évacuation de foule où **chaque agent se construit sa
propre croyance** sur la sortie à prendre. Le sujet n'est pas de savoir
si les gens courent vite : c'est de mesurer comment une croyance circule,
se déforme, et parfois piège la foule qui l'a adoptée.

---

## Ce que le projet démontre

| Question | Réponse mesurée |
|---|---|
| Peut-on simuler 60 agents ? | Oui. JuPedSim fait 60 agents × 100 s simulées en **0,06 s** → **1 761× le temps réel**. |
| Où est le coût ? | Uniquement dans l'appel LLM : **2,8 s** par décision. |
| Combien d'appels par run ? | **Quelques centaines**, pas 2 160 — parce qu'on ne décide que sur changement, et qu'un signal persistant ne déclenche qu'une fois. |
| Le run est-il rejouable ? | Oui, depuis le journal JSONL seul, sans LLM ni Kafka. |

---

## Démarrage

### Sans GPU, sans Docker — le chemin le plus court

```bash
uv sync --all-extras
make smoke            # run complet, 60 agents à règles, 0 appel LLM
make test             # toute la suite (physique factice)
make replay-demo      # rejoue le run versionné (E3), sans LLM
make replay-pair      # rejoue la paire 20 / 60 agents (C8), sans LLM
```

### Avec le LLM (deux modèles, un serveur llama.cpp)

Le serveur est un conteneur `llama.cpp` qui sert `gemma4-e2b` (grand),
`qwen3-0-6b` (petit) et `bge-m3` (embeddings). **Le nom du petit modèle
est `qwen3-0-6b`** : le routeur normalise les points en tirets, et
`qwen3-0.6b` renvoie 404.

```bash
make pull-models                    # une fois : télécharge les GGUF
docker run -d --name maree-llama-cpp --gpus all -p 8080:8080 \
  -v "$PWD/models:/models" maree/llama-cpp:b11609   # 4 slots, ctx 8192
make index                          # index RAG (bge-m3, 215 passages)
```

Puis, **dans chaque shell qui lance un run LLM**, l'URL du conteneur :

```bash
export MAREE_LLM_URL=http://$(docker inspect maree-llama-cpp \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'):8080/v1
uv run maree run population=hybrid narrative.enabled=true
```

L'IP change à chaque recréation du conteneur : la relire, ne pas la
recopier. `MAREE_LLM_URL` est la seule variable lue par
`configs/llm/llamacpp.yaml` ; sans elle, le client vise `llama-cpp:8080`,
tous les appels échouent, et le run **ressemble** à un run normal — la
CLI crie quand `llm_ok == 0`, et `run.ended` porte le compte.

### Démonstration en direct (injection d'événements)

```bash
uv run maree live --tick-ms 600     # moteur + WebSocket + file de contrôle
godot --path godot/project          # client : plan, inspection, injection (D2/D3)
```

`make godot-test` vérifie le contrat d'affichage sans serveur ni GPU.

### `make up` (Redpanda + llama.cpp + simulateur)

`docker compose up` suppose une image `maree/llama-cpp` construite
localement et la publication de ports — deux choses qui **n'ont pas
fonctionné sur la machine de développement** (apt sans réseau pendant le
build, publication de ports cassée). La procédure réellement utilisée est
le `docker run` ci-dessus. Les campagnes d'expérience tournent de toute
façon en `bus.backend=memory` : Redpanda est prouvé par un run dédié
(C1, 1 002 messages), pas par les mesures.

Sans serveur LLM du tout, `make smoke` fait un run complet de 60 agents
**sans aucun appel LLM**.

---

## Architecture en une page

Trois horloges, un seul état du monde.

```
       0,05 s            10,00 s              0,10 s
   ┌───────────┐     ┌──────────────┐     ┌───────────┐
   │  physique │     │   cognition  │     │   rendu   │
   │ JuPedSim  │     │  LangGraph   │     │   Godot   │
   └─────┬─────┘     └──────┬───────┘     └─────┬─────┘
         │                  │                   │
         └──────────┬───────┴───────────────────┘
                    ▼
            ┌───────────────┐
            │  journal JSONL│  ← source de vérité, append-only
            └───────┬───────┘
                    ▼
            ┌───────────────┐
            │ bus           │  mémoire (campagnes) ou Redpanda (démo)
            └───────┬───────┘
                    ▼
        Godot · chroniqueur · indicateurs
```

**Le mouvement n'attend jamais la pensée.** JuPedSim avance à 20 Hz, les
agents réfléchissent toutes les 10 s simulées, et Godot interpole entre
deux instantanés. C'est ce découplage qui rend 60 agents tenables.

Le bus n'est **pas** dans le chemin de la mesure : les campagnes
tournent en `bus.backend=memory` et le rejeu lit le journal. Redpanda
sert la démonstration temps réel (C1 : 1 002 messages vérifiés sur un
broker réel).

### Les trois moteurs

| Couche | Outil | Rôle |
|---|---|---|
| Foule | **JuPedSim 1.4** | `CollisionFreeSpeedModel` et `SocialForceModel` (Helbing & Molnár 1995) |
| Cognition | **LangGraph 1.2** | `recall → retrieve? → decide → validate` |
| Configuration | **Hydra 1.3** | tout paramètre en YAML, rien en dur |
| LLM | **SDK OpenAI** → llama.cpp | décisions, embeddings, récit |
| RAG | **FAISS** + bge-m3 | 215 passages, filtres profil/tick |
| Bus | **Redpanda** | diffusion temps réel, jamais persistance |
| Mesure | **scipy**, **DuckDB** | médianes, Mann-Whitney, agrégats |

### Ce qu'on n'utilise pas, et pourquoi

- **Mesa** : son ordonnanceur (`Model.run_until`) est synchrone et ne peut
  pas héberger un appel LLM asynchrone. L'utiliser aurait signifié le
  combattre. LangGraph couvre le besoin multi-agents, JuPedSim la physique.
- **LlamaIndex** : le corpus est déjà découpé en 215 passages annotés. Le
  seul traitement qui compte — le centrage sur la moyenne du corpus, qui
  fait passer la précision@1 de 0,17 à 0,73 — aurait dû être réécrit
  par-dessus l'abstraction. Voir `docs/architecture-v2.md`.

---

## Les cinq profils

Un profil n'est pas un caractère : c'est un **jeu de connaissances
initiales** et un contrat de décision.

| Profil | Sorties connues | Priorité |
|---|---|---|
| `securite` | A, B, C | évaluer, guider |
| `habitue` | A, B, C | éviter la foule |
| `famille` | A, C | retrouver un proche |
| `visiteur` | A | comprendre, suivre |
| `vendeur` | A, C | protéger son stand |

La ruelle B (1,5 m) n'est connue que de l'habitué. C'est le levier
narratif : **le savoir local sauve, l'ignorance piège**.

---

## Indicateurs

| ID | Mesure | Ce qu'elle dit |
|---|---|---|
| I1 | consensus | part de la croyance majoritaire |
| I2 | entropie | incertitude moyenne (0 = sûrs, 1 = perdus) |
| I3 | évacués | part des agents sortis |
| I4 | temps | l'horloge : tick × 10 s, **censurée** à `max_ticks` |
| I5 | densité max | le goulot, en personnes/m² (pic ; sature à 2,0 à 60 agents) |
| I6 | écart | part des agents croyant en une sortie fermée |
| I7 | délai | premier signal de danger → dernier sorti, défini sous censure |

I6 est l'indicateur central : la croyance partagée qui sauve à t10 et
piège à t40. I4 dit « quand », I7 dit « combien de temps » : I7 retire le
temps d'avant-signal, donc il reste comparable entre bras qui ne voient
pas la fumée au même tick. Lire I3 et I7 ensemble dès qu'une partie de la
foule ne sort pas — I4 est alors censuré à `max_ticks` et ne mesure plus
une durée réelle. `metrics.summarise()` prend le **pic** pour I5/I6 et la
moyenne sur la partie active pour I1/I2 : le dernier tick est dégénéré
(tout le monde est sorti, tous les indicateurs valent 0).

---

## Structure

```
configs/        Hydra : monde, population, run, expériences
src/maree/
  domain/       plan, horloges, croyances, intentions, événements
  ports/        les contrats (Protocol) — aucun import concret
  agents/       profils, déclencheurs, règles, graphe LangGraph
  memory/       mémoire épisodique cloisonnée
  metrics/      I1..I6
  narrative/    digest + chroniqueur + validateur
  engine/       boucle à trois horloges, rejeu
  adapters/     JuPedSim, llama.cpp, FAISS, JSONL, Redpanda
  cli.py        run | index | replay | trace | query | state | lag |
                experiment | serve | live | report
tests/          domaine, cloisonnement, déterminisme, rejeu
godot/          client de visualisation
docs/           cadrage, hypothèses, architecture, résultats
```

## Commandes

| Commande | Ce qu'elle fait |
|---|---|
| `maree run [overrides…]` | un run ; `population=rules_only` pour se passer de LLM |
| `maree experiment --name x12 --seeds 5` | un protocole de `configs/experiment/` : bras × graines |
| `maree index` | (re)construit l'index RAG |
| `maree replay [--run-id …]` | rejoue le journal et vérifie chaque décision |
| `maree trace --indicator I1_consensus` | remonte d'un saut d'indicateur aux événements qui l'ont causé |
| `maree query runs` | requête DuckDB versionnée sur les journaux |
| `maree state` | état courant (`state.json`), sans lire le journal |
| `maree lag` | monde → perception → mesure, par événement (C7) |
| `maree serve [--prompts]` | diffuse un run en WebSocket vers Godot |
| `maree live` | run + diffusion + injections (D3) |
| `maree report` | tableau agrégé des runs mesurés (I1–I7) |

## Documentation

- **`docs/resultats/rapport-hybride.md` — le rapport demandé** : partie
  technique, partie scientifique en mini-article, bilan de sobriété,
  réponses aux six questions du jury.
- `docs/architecture-v2.md` — décisions, et ce qu'on a écarté
- `docs/hypotheses.md` — hypothèses préenregistrées H1..H7
- `docs/protocol-ui.md` — le contrat d'affichage (trames) pour écrire un autre client
- `docs/cadrage-maree.md` — cadrage du monde
- `docs/audit-consigne-2026-10-31.md` — ce qui manquait, et ce qui reste partiel
- `AGENTS.md` — mémoire de chantier (pièges, mesures, conventions)
