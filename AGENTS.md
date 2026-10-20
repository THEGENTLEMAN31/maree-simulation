# AGENTS.md — Fil conducteur pour les agents IA travaillant sur MARÉE

Ce fichier est la **mémoire de contexte unique** du projet. Lis-le en entier
avant toute modification. Il te dit quoi faire, où sont les choses, et ce
qu'il ne faut JAMAIS casser.

## Qu'est-ce que MARÉE ?

MARÉE est la simulation pour le projet 5A IABD (EIGSI Casablanca). Monde 02
du catalogue : **foule et évacuation** à la Fête des Lanternes de Port-Aubel
(ville fictive). Question de recherche : *une foule qui ne sait rien
construit-elle une croyance partagée sur la sortie sûre, et cette croyance la
sauve-t-elle ou la piège-t-elle ?*

Le cahier des charges complet est dans `../monde vivant` (fichier HTML
téléchargé) et le cadrage détaillé dans `docs/cadrage-maree.md` (copie de
`MARÉE — Cadrage du projet.md` dans `~/school/mondes_vivants/`).

## Stack (ne pas diverger sans mettre à jour ce fichier)

- **LLM** : Gemma 4 E2B (rapide) + E4B (raisonnement), en local via llama.cpp
  router (Docker `llama-cpp`, binaires officiels **b11609** — voir
  `llama.cpp/Dockerfile.prebuilt`). **N'utilise pas Ollama** : il ne gère pas
  l'expert offload MoE et évince les modèles sur 4 Go de VRAM.
  Contraintes matérielles (RTX 3050, 4 Go) :
  - E2B (2,9 Go) tient intégralement sur le GPU ;
  - E4B (4,7 Go) **ne tient pas** → offload partiel CPU
    (`n-gpu-layers = 20` dans `presets/maree.ini`), latence plus élevée ;
  - en mode router, `ctx-size` est **réparti entre les `--parallel` slots** :
    dimensionner `ctx-size = slots × fenêtre voulue` (sinon les prompts réels
    sont rejetés et les agents replient silencieusement sur la règle) ;
  - les deux modèles ne peuvent pas être résidents ensemble :
    `--models-max 1`.
- **Streaming** : Redpanda (Kafka API) dans Docker, `schema_version` par
  enveloppe, topics `world.events`, `agent.decisions`, `metrics.indicators`,
  `control.commands`, `dlq.invalid`.
- **Simulation** : Python 3.11+ asyncio dans `python-sim/`.
- **Visualisation** : Godot 4.4 (headless pour CI, VNC pour démo jury).
- **RAG** : corpus Markdown dans `world_corpus/`, client Léger dans
  `python-sim/src/rag/` (mode mémoire par défaut, pas Chroma — décision prise
  pour la simplicité solo ; le cadrage disait Chroma, on le documente).

## Arborescence

```
maree-simulation/
├── docker-compose.yml           # stack principale
├── docker-compose.demo.yml      # + Godot VNC (profil demo) + éditeur (profil editor)
├── docker-compose.e2e.yml       # override du test de bout en bout
├── presets/maree.ini            # config llama.cpp router (2 modèles)
├── models/                      # GGUF + binaires llama.cpp (jamais commités)
├── python-sim/
│   ├── src/
│   │   ├── orchestrator.py      # TISSU CONNECTEUR : câble tout
│   │   ├── events.py            # enveloppe d'événements (schema_version)
│   │   ├── config.py            # pydantic, chargé depuis YAML
│   │   ├── temporal.py          # SimClock + Scheduler (sync/async)
│   │   ├── world.py             # esplanade, fumée, vérité terrain
│   │   ├── kafka_client.py      # wrapper aiokafka (+ mode mémoire tests)
│   │   ├── llm_gateway.py       # passerelle LLM unique (retry, coût, dry_run)
│   │   ├── ws_server.py         # relais Websocket -> Godot
│   │   ├── replay.py            # RunLogger + ReplayEngine (E3)
│   │   ├── oracle.py            # cohérence temporelle (C6, I5)
│   │   ├── agents/              # base, profiles, llm_agent, rules_agent
│   │   ├── rag/rag.py           # retrieve_by_profil + C6 + traçabilité F2
│   │   ├── metrics/indicators.py# I1..I5
│   │   └── experiments/         # X1..X7 (runner) + report (F5)
│   ├── tests/                   # pytest — 12 tests verts
│   └── config/                  # simulation.yaml + configs e2e (sync/async/E4B)
├── godot/project/               # scenes + scripts GDScript
│   └── tests/                   # run_tests.gd (26), run_ws_tests.gd (8), run_e2e_client.gd
├── world_corpus/                # corpus RAG (5 collections)
├── docs/                        # decisions.md, architecture.md, cadrage…
└── scripts/                     # download_models.sh + run_e2e.sh
```

## Les 16 décisions d'architecture (ne JAMAIS violer)

1. **Journal = source de vérité.** Tout événement passe par le JSONL
   (`replay.py`) et Kafka. Une sortie LLM non enregistrée = événement perdu.
2. **Double horodatage** `t_prod` / `t_trait` (+ réel) dans l'enveloppe.
3. **Déterminisme.** Graine par run/agent, ordre canonique (tri `seq`),
   aucune horloge système dans la logique `world.py`.
4. **Enveloppe versionnée.** `schema_version`, `causation_id`.
5. **Identité de run** = `run_id` + `config_hash()`. Un run seul par run_id
   (append du JSONL : ne réutilise PAS un run_id).
6. **Interface unique** `decide(perception) -> Intention` pour LLM et règles.
7. **Passerelle LLM unique** (retries, timeout, repli règle, journal coût).
8. **Moteur exécute les intentions** — Godot ne calcule rien.
9. **Godot = consommateur pur.**
10. **Ordonnanceur séparé**, perception figée à l'instant T.
11. **Tout paramètre dans le YAML**, rien en dur.
12. **Traçabilité RAG** : chaque décision stocke les passages retrouvés.
13. **Hypothèses préenregistrées** dans `docs/hypotheses.md`, datées.
14. **Versions figées** (lockfiles, tags images, modèles GGUF précis).
15. **Accès RAG par profil + date de disponibilité simulée** (C6).
16. **Chaque indicateur référence les offsets sources** (F6).

## Exigences couvertes (32)

La correspondance complète est dans `docs/correspondance-exigences.md`.
**Règle : après toute modification, mets à jour cette correspondance** si
une exigence change de statut.

## Commandes utiles

```bash
make up           # stack complète (headless)
make up-demo      # + Godot VNC (navigateur :6080)
make editor       # éditeur Godot dans le navigateur (:6081, projet monté)
make pull-models  # télécharge les GGUF sur l'hôte
make test         # pytest (12 tests)
make test-godot   # tests des composants Godot (headless, hors ligne)
make e2e          # chaîne réelle sync (Redpanda + LLM + Godot + rejeu E3)
make e2e-async    # idem en mode asynchrone
make e2e-e4b      # idem avec le grand modèle (offload partiel)
make run          # run single dry-run
make replay       # rejeu E3
make experiments  # protocole X1–X7
make report       # rapport F5
```

## Cartographier la codebase (graphify)

Le dépôt inclut un **graphe de connaissances** de la codebase dans
`graphify-out/` (graph.json + graph.html interactif + GRAPH_REPORT.md).
Il est versionné : sans relire le code, interroge-le :

```bash
# après une modification du code, régénère le graphe (aucun coût API)
graphify update . --code-only --no-viz
graphify explain "Orchestrator"     # un nœud et ses voisins
graphify path "Orchestrator" "Perception"  # chemin entre deux nœuds
graphify query "comment agents et RAG se relient-ils ?"
```

- Install : `uv tool install graphifyy` puis `graphify install --project`.
- Nœuds centraux attendus : `Orchestrator` (48 arêtes), `Perception`,
  `LLMAgent`, `EventEnvelope`. Si ces nœuds disparaissent du rapport, c'est
  un signal d'alerte.
- `graphify-out/` est commité : ne le supprime pas sans raison.

## Règles pour un agent IA ici

1. **Lis les docs avant de modifier.** Surtout `docs/decisions.md`.
2. **Ne casse jamais le replay (E3)** : si tu changes le format d'enveloppe,
   tu dois mettre à jour `replay.py` ET `schema_version`.
3. **Tests verts avant de pousser** : `cd python-sim && pytest`.
4. **Le JSONL est append-only** : chaque run a son `run_id` unique.
5. **Language de code et commentaires : français** (sujet francophone) sauf
   noms de variables en anglais (conventions de code).
6. **Ne touche pas à la config Ollama de l'hôte** (gemma4/qwen3) : la
   simulation utilise ses propres GGUF dans `models/`.

## État courant

- Socle Python complet + tests verts (orchestrateur, agents, RAG, replay,
  indicateurs) — **12 tests pytest**.
- **Godot réparé et validé** : scène `.tscn` réécrite en syntaxe Godot 4
  valide, scripts (client WS, rendu, inspection D2, courbes B2, HUD D3)
  fonctionnels. Tests : 26 composants + 8 chaîne WS (mock) + 6 e2e réel.
- **Chaîne réelle validée de bout en bout** le 20/10 : Redpanda + llama.cpp
  (E2B réel) + python-sim + Godot, en sync, async et avec E4B ; rejeu E3 OK.
  Tout est reproductible via `make e2e` / `make e2e-async` / `make e2e-e4b`.
- Corpus RAG : 13 passages initiaux — **à étendre** (objectif ~200, le cadrage
  demande 200 passages de 100–200 mots, répartis en 5 collections).
- Variantes expérimentales X1–X7 : **câblées** dans l'orchestrateur
  (`_apply_experiment_events` consomme `world.announcement_tick`,
  `annonce_clarity`, `exits_closed`) ; le runner `experiments/runner.py`
  génère les configurations et le résumé médiane/IQR.
- Graphify : graphe de la codebase généré (339 nœuds, 11 communautés).
- À faire : étendre le corpus RAG, README GitHub de qualité, synchroniser le
  dépôt distant.

## Prochaines tâches (ordre suggéré)

1. Étendre le corpus RAG vers ~200 passages (les 5 collections).
2. Lancer les variantes X1–X7 et produire le rapport F5 (`make experiments`,
   `make report`).
3. Écrire README GitHub de qualité + synchroniser le dépôt distant.