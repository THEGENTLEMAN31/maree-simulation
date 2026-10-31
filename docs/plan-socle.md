# Plan de complétude — les 32 exigences du défi commun

> **Ce document est un plan de chantier, pas de la documentation.** Il se met à
> jour à chaque étape validée. Une case cochée = testé, committé, poussé.
>
> Référence : `Mondes-Vivants_Projet-5A-IABD.html`, défi commun.
> 20 exigences de socle, 9 de standard, 3 d'excellence.
>
> **Principe directeur** : le moteur reste modulable et le client (Godot, front)
> garde toute sa liberté. Le moteur n'impose rien au client : il publie des
> **trames JSON** autoportantes (un événement → une trame), et le client peut
> ignorer, agréger ou rejouer ce qu'il veut. Toute fonctionnalité d'affichage
> passe par une trame documentée dans `docs/protocol-ui.md`, jamais par une
> dépendance du client au moteur.

---

## 1. État de départ (audit du 2026-10-29)

| Statut | Exigences | Nombre |
|---|---|---|
| **Tenu** | A3, A6, B1, B2, C2, C5, D1, E1, E2, F1 | 10 |
| **Partiel** | A1, A2, B3, C1, C3, D2, E3, E4, F2, F3, F4, F5, F6 | 13 |
| **Absent** | A4, A5, B4, C4, C6, C7, C8, D3, E5 | 9 |

Trois « partiels » cachent un bug qui rend l'exigence **impossible** :

- `causation_id` = **0 / 1 181** événements d'un journal réel : `_emit` n'appelle
  jamais `Event.child()`. Sans cela, B4 ne peut pas exister.
- les passages RAG **ne sont pas journalisés** : F2 n'est pas recalculable.
- `t_trait == t_prod` en dur (`simulation.py`) : C3 est faux, C7 impossible.

Et une ligne oubliée : `Profile.model` n'est **jamais** passé à `chat()` → A5 absent.

---

## 2. Les quatre vagues

### Vague 1 — bugs d'une ligne et preuves gratuites

- [x] **A5** — modèle par profil (`two_tier`), tiers `big`/`small` résolus dans
      l'adaptateur. Un profil garde son tier, le YAML choisit le nom.
      *Sortie* : deux noms de modèles coexistent dans un run ; `llm.model`
      journalisé par décision.
- [x] **B4** — `causation_id` réel : `_emit(..., cause=…)`, chaîne
      message → décision → croyance → message suivant. Script
      `scripts/trace_indicator.py` qui remonte d'un saut d'indicateur aux
      échanges qui l'ont précédé.
      *Sortie* : un journal réel où ≥ 50 % des décisions ont une cause.
- [x] **F2** — journaliser `retrieved` (doc_id, texte, score, collection) et
      `memory` (épisodes utilisés) dans `agent.decision`. Corpus d'évaluation
      annoté + `scripts/eval_rag.py` (P@1, P@3, MRR).
      *Sortie* : un rapport de récupération calculé, pas un artefact v1.
- [x] **E3** — un run enregistré dans le dépôt (`runs/demo_replay/`), exception
      `.gitignore`, `make replay-demo`, hash d'indicateurs identique.
- [x] **Docs honnêtes** — corriger les 5 affirmations fausses de
      `docs/cadrage-maree.md`, archiver les artefacts v1.

### Vague 2 — le socle manquant

- [x] **D3** — injection en direct : file de contrôle drainée en tête de
      `_world_events` (perception figée préservée), trame entrante documentée,
      `control.injection` journalisé avec `causation_id`.
      *Sortie* : `maree live` + un client qui envoie `{"type":"inject",…}`.
- [x] **D2** — `snapshot` porte `memory`, `last_decision` (raison, règle,
      passages) → inspection sans reconstruction côté client.
- [x] **C6** — vérificateur de cohérence temporelle : aucun agent n'agit sur une
      info postérieure à sa décision ; compteur dans `run.ended` et dans le
      journal (`temporal.violation`).
- [x] **A2 / B3** — bras `sans_communication` (X8). *Résultat contre
      l'attente* : I1 **ne bouge pas** (0,990 → 0,992), donc I1 ne mesure pas
      l'influence sociale dans cette population — c'est l'artefact que B3
      devait révéler, et il est publié tel quel. Ce sont I2 (0,333 → 0,461),
      I3 (0,967 → 0,850) et le nombre de messages (58 → 0) qui distinguent les
      deux bras.
- [x] **E4** — `tokens_in/out`, mural, appels et violations agrégés par run et
      par bras ; bilan dans `docs/resultats/sobriete-v2.md`, mis en regard de
      l'apport mesuré.
- [x] **F4** — schémas par type documentés et versionnés, validation à l'écriture,
      `dlq.invalid` réellement émis, quarantaine sans arrêt du run.
- [x] **A1** — préhistoire : de vrais `message.sent`/`heard` entre agents,
      datés d'un tick négatif (J−3 = −25 920), mémorisés avec le nom de
      l'émetteur ; ablation `prehistory_days=0|3` (X9).
- [x] **F6** — `sources` (seq) sur la trame `indicators` : remontée exacte.

### Vague 3 — le temps, le vrai

- [x] **C4** — `run.mode = sync | async`. En asynchrone, chaque agent décide
      à son rythme et sa décision s'applique **quand la réponse arrive** : la
      latence est réelle (mesurée), pas tirée d'une graine. La tâche est
      lancée au tick de la perception, ramassée au tick où elle aboutit ;
      `t_trait − t_prod` porte la latence. À la clôture, ce qui est encore en
      vol est drainé puis annulé en `timeout` (A4). Protocole X11.
- [x] **C3** — `t_prod` (moment où l'événement se produit) et `t_trait`
      (moment où il est traité) sont distincts dans l'enveloppe **et** dans
      les trames client. En synchrone ils coïncident (c'est la définition du
      mode) ; en asynchrone et avec `message_delay_ticks > 0` ils diffèrent,
      et la différence est journalisée, donc mesurable après coup.
- [x] **C7** — `maree lag` et `metrics/lag.py` : deux décalages par événement
      du monde — le premier descendant causal (le monde a été **perçu**) et le
      premier bloc d'indicateurs qui bouge (le monde a été **mesuré**).
      Mesuré à 20 et à 60 agents (X10) : c'est la comparaison sous charge.
- [x] **C8** — deux tailles de population en soutenance : `x10.yaml` joue 20
      agents (7 LLM + 13 règles) et 60 agents (12 + 48) sur le même scénario,
      et la comparaison est scriptée (mêmes indicateurs, mêmes graines).
- [x] **A4** — `agent.incident` avec une cause nommée : `no_response`,
      `unparseable`, `unknown_action`, `unknown_exit`, `unknown_zone`,
      `out_of_role`, `timeout`. Le run continue (repli sur les règles), le
      compteur par cause est dans `run.ended` et dans la CLI. Mesuré sur un
      run réel : 5 incidents, 2 causes.

### Vague 4 — le coûteux

- [x] **A5 / E5** — le tier « small » reçoit une **politique explicite**
      (règle + drapeaux oui/non), parce qu'un modèle de 0,6 Md suit la
      forme du prompt et non son contenu. Protocole X12 en plan 2×2 :
      taille du modèle × protocole (JSON ouvert / politique), 4 bras ×
      5 graines. La référence est « tous les agents sur le plus grand
      modèle » ; `llm.small_protocol: open` rejoue le défaut.
- [x] **F3** — `adapters/state.py::JsonStateStore` : l'état courant a son
      fichier (`state.json`, écriture atomique, dernière valeur seule),
      distinct du flux d'événements. `maree state`. Le raisonnement et les
      volumes mesurés sont dans `docs/stockage.md`.
- [x] **F5** — `queries/*.sql` + `maree query` : DuckDB lit les JSONL
      ligne par ligne (aucune inférence de schéma, aucun Parquet), les
      requêtes sont versionnées avec le code.
- [ ] **C1 / O3 — pont Kafka côté client** (`maree serve --source kafka`).
      C1 est tenu (1 002 messages vérifiés sur un Redpanda réel) ; ce pont
      est un confort pour le client Godot, pas une exigence. Non fait, et
      c'est dit.

### État au 2026-10-31 (fin de la vague 4)

| Statut | Exigences | Nombre |
|---|---|---|
| **Tenu** | les 32 | **32** |
| **Partiel** | — | 0 |
| **Absent** | — | 0 |

Les trois dernières sont tombées ensemble, et pas comme prévu : E5
supposait qu'un petit modèle saurait décider « en plus petit ». Il ne
sait pas — il suit la première option de la liste, ou la dernière consigne
du prompt. Le levier de sobriété existe quand même, mais il faut lui
donner une **politique explicite** au lieu d'une question ouverte, et le
dire : le petit modèle applique, le grand juge.

Deux réserves restent écrites noir sur blanc plutôt que masquées :
`maree serve --source kafka` n'existe pas (C1 est tenu sans lui), et
l'énergie n'est pas re-mesurée par bras dans X12 (E4 l'a mesurée une
fois).

---

## 3. Journal d'exécution

| Date | Étape | Commit | Tests | Notes |
|---|---|---|---|---|
| 2026-10-29 | plan écrit | — | 138 passent | point de départ |
| 2026-10-29 | A5 deux tiers + B4 causalité + F2 RAG journalisé + E3 run versionné + docs corrigées | `vague1` | 149 passent, ruff propre | voir ci-dessous |
| 2026-10-30 | C4 async + C3 horodatages + A4 incidents + C7 lag + C8 populations + C1 Kafka | `vague3` | 178 passent, ruff propre | X10 (20 runs), X11 (10 runs), Kafka réel (1 002 messages) |
| 2026-10-30 | D3 injection + D2 justification + C6 cohérence + A1 préhistoire + A2/B3 + E4 coût + F4 schémas + F6 sources | `vague2` | 167 passent, ruff propre | X8 et X9 joués (5 graines) |
| 2026-10-31 | E5 politique du petit modèle + F3 état courant + F5 requêtes SQL | `vague4` | 186 passent, ruff propre | X12 (4 bras × 5), X10 et X11 refaits après correction du petit modèle |

### Mesures de la vague 1

- **A5** : `Profile.tier` (`big`/`small`) remplace `Profile.model` ; le YAML
  choisit les noms (`gemma4-e2b`, `qwen3-0.6b`). `two_tier: true` par défaut.
  L'adaptateur retombe sur le grand modèle si le petit manque, et la trace
  porte `requested_model` ≠ `model`.
- **B4** : `_emit(cause=…)` → `Event.child()`. Run réel : **820 / 1 023**
  événements avec `causation_id`, 54 / 212 décisions causées (les autres
  sont périodiques, sans parent inventé), **160 chaînes** distinctes.
  `maree trace --run-id … --indicator I1_consensus` remonte la chaîne.
- **F2** : `retrieved` + `memory` journalisés par décision. Évaluation
  mesurée sur 24 requêtes annotées : **P@1 0,417 · P@3 0,750 · MRR 0,569**.
  La faiblesse est expliquée (corpus généré, doublons de template), pas
  maquillée.
- **E3** : `runs/demo_replay/` versionné — 32 ticks, 1 020 événements,
  **49 appels / 49 succès**, 18 s, 60/60, `maree replay` → `ok: true`,
  49/49 décisions concordantes, 3 replis règles annoncés.
- **Docs** : `cadrage-maree.md` porte un bandeau et cinq sections corrigées ;
  les artefacts v1 sont archivés dans `docs/resultats/v1/`.

### Mesures de la vague 2

- **D3** : `maree live` (moteur + diffusion + file de contrôle dans un seul
  processus). Vérifié de bout en bout avec un client WebSocket :
  `inject` → `ack` → trame `injection` → trame `world`, appliqué au tick
  suivant, `causation_id` reliant les deux. Une injection inconnue est
  isolée (`invalid.jsonl`) et le run continue.
- **D2** : `snapshot.agents[].last_decision` (raison, règle, passages,
  mémoire) et `memory` (3 épisodes datés). L'inspection d'un agent ne
  demande plus de recoller trois événements.
- **C6** : `_check_temporal` vérifie messages, passages RAG et signal
  déclencheur ; **0 violation** sur les 20 runs X8/X9 et sur les runs de
  test. Un compteur `temporal_violations` est dans `run.ended`.
- **A2/B3 (X8, 5 graines)** : I1 **ne bouge pas** (0,990 → 0,992) — c'est
  l'artefact que B3 devait révéler, et il est publié. I2 0,333 → 0,461,
  I3 0,967 → 0,850, messages 58 → 0. Coût : **77 → 131 appels** sans
  communication (+70 %).
- **A1 (X9, 5 graines)** : échanges J−3 journalisés ; **188 / 379**
  décisions LLM (50 %) citent un épisode de préhistoire ; la sortie **C**
  est choisie 9 fois contre 3 sans passé. Au niveau agrégé, I3 0,967 →
  0,976 : l'effet est dilué par les 48 agents à règles.
- **E4** : `tokens_in/out` par run et par bras ; bilan dans
  `docs/resultats/sobriete-v2.md`. Énergie mesurée : **0,46 Wh** par run
  hybride (52,5 W de surcoût pendant 31,6 s).
- **F4** : `SCHEMAS` + `validate()` ; un événement non conforme part dans
  `runs/<id>/invalid.jsonl` et laisse un `dlq.invalid`, sans arrêter le
  run. `quarantined` est compté dans `run.ended`.
- **F6** : `indicators.sources = {from_seq, to_seq, count}` ; vérifié
  (t1 : 1 → 122).
- **Deux tiers (A5)** : conteneur recréé avec `--models-max 3` ; mesuré
  24 appels `gemma4-e2b` + 73 `qwen3-0-6b`, 0 repli, 2 691 MiB / 4 096.

### Mesures de la vague 4

- **E5 (X12, 4 bras × 5 graines, médianes)** : `tous_grand` 50 appels /
  21 619 jetons / I3 1,00 / I7 150 s / 21,4 s mural ; `deux_tiers` 48 /
  **14 698 (−32 %)** / 1,00 / 220 s / 12,4 s ; `protocole_seul` 42 /
  12 857 (−41 %) / 1,00 / **110 s** / 13,9 s ; `petit_json_ouvert` 79 /
  39 161 (+81 %) / 0,95 / 330 s / 27,1 s. Le gain est réel (−32 % de
  jetons, −42 % de mural, I3 identique) mais **il vient du protocole, pas
  de la taille du modèle** : `protocole_seul` fait mieux avec le grand
  modèle. Le petit coûte 70 s d'I7 (annonces suivies 2 fois sur 6).
- **A5, quatre formats essayés** sur `qwen3-0-6b` : JSON ouvert →
  `search` 55/55 ; liste de mots-clés → **toujours la première option** ;
  question binaire → instable ; **règle + drapeaux oui/non** → calme 6/6,
  fumée 6/6, annonce 2/6. Retenu tel quel, limite consignée.
- **F3** : `state.json` pèse **70 581 octets** là où le journal du même run
  en pèse 1 777 302, dont **77 % d'instantanés** ; `maree state` le lit en
  0,40 s.
- **F5** : **449 970 événements, 451 runs, 3,4 s** pour la requête la plus
  large (1,2 Go de JSONL), sans serveur ni Parquet.
- **X10 refait** : `lag_llm` 0 (sync) → 5,5 (20 agents) → **8,0** (60) ;
  `lag_indicator` 1,5 → 3,5 → 2,5. La prédiction de C7 tient.
- **X11 refait** : sync I3 1,00 / I7 220 s / lag 0 ; async **0,98 /
  470 s** / lag médian 5, max 12 / 60 appels contre 47.
- **La question de MARÉE, re-mesurée** : le petit modèle réagit en 5 ticks
  contre 6 à 8,5, mais l'ordre de sortie suit le **profil** — la famille
  (grand) sort à t12,5, le vendeur (petit, le plus rapide) à t29,5.

---

## 4. Décisions prises en autonomie

1. **Pas de Parquet.** DuckDB lit les JSONL nativement (`read_json_auto`) :
   ajouter un format serait un coût sans bénéfice. F3 documente les quatre
   stockages réels, F5 fournit des requêtes `.sql` reproductibles.
2. **Petit modèle = `qwen3-0-6b`**, grand = `gemma4-e2b`. Écart de taille 3,3×,
   défendable. Le petit est attribué aux profils dont la décision est simple
   (`visiteur`, `vendeur`), jamais selon une catégorie sociale. Le nom est
   celui **annoncé** par le routeur (il normalise les points en tirets).
3. **Deux sous-modes asynchrones.** `simulated` garde E2 (runs reproductibles) ;
   `real` satisfait C4 à la lettre. Les deux sont journalisés, donc rejouables.
4. **Kafka hors du chemin de mesure.** `bus.backend=memory` reste la règle des
   campagnes ; Kafka sert la démonstration C1/O3. La publication devient
   best-effort.
5. **Le client ne dépend jamais du moteur.** Une fonction pure
   `frame_for(event)` est la seule interface ; tout ajout passe par une trame.

---

## 5. Risques

- **VRAM** : e2b + qwen3-0.6b + bge-m3 ≈ 2,5 Go sur 4 Go. Mesuré 1 980 MiB pour
  e2b+bge-m3 ; marge ~1,5 Go. Si OOM : `parallel=2`, `ctx-size=4096`.
- **Kafka injoignable ici** : le pont est testé avec un faux bus ; la démo se
  fait en `memory`.
- **Quota LLM** : les runs LLM exigent le conteneur ; à défaut, les tests
  utilisent un faux LLM et les campagnes sont documentées comme non rejouées.
- **Bruit LangSmith** : préfixer les commandes par `LANGCHAIN_TRACING_V2=false`.
