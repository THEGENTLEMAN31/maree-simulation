# Correspondance aux 32 exigences du cahier des charges

Chaque exigence du projet « Mondes Vivants » a une **preuve** livrée et un
**emplacement** dans le dépôt. Le cadrage complet est dans
`docs/cadrage-maree.md` ; ici on dit *où* chaque chose vit dans le code.

Légende : ✔ = couvert par le socle actuel, ⚠ = à compléter d'ici la soutenance.

## A — Agents qui pensent et se souviennent

| Exigence | Niveau | Où dans le projet | Preuve livrée |
|----------|--------|-------------------|---------------|
| A1 Mémoire propre | Socle | `agents/llm_agent.py` — `agent.remember()` event-sourcé | Tests : un échange ancien change la décision (X5) |
| A2 Échanges langage naturel | Socle | `orchestrator.py` — `_messages()` publie `agent.message` | Contrôle négatif : communication coupée → I1 chute |
| A3 Profils différents | Standard | `agents/profiles.py` — 6 profils, prompts distincts | X6 : profils échangés → décisions échangées |
| A4 Robustesse dérives | Standard | `llm_gateway.py` + `llm_agent.py` — repli, journal `drift_events` | Compteurs de dérives dans le rapport |
| A5 Modèles différents | Standard | `presets/maree.ini` — gemma4-e2b et gemma4-e4b | Table de population : securite/habitués sur E4B |
| A6 Règles cohabitent | Standard | `agents/rules_agent.py` + 25–45 agents de foule | Justification dans le rapport |

## B — Contexte commun mesurable

| Exigence | Niveau | Où | Preuve |
|----------|--------|----|--------|
| B1 Contexte commun défini | Socle | `metrics/indicators.py` I1/I2 + docs/architecture | Définition du consensus en termes observables |
| B2 Indicateur live | Socle | `metrics/indicators.py` + Godot `indicators.gd` | Démo live synchronisée |
| B3 Distingue émergence | Socle | `experiments/runner.py` X4 + contrôles négatifs | Résultats X4 (LLM vs règles) |
| B4 Causalité | Excellence | `events.py` `causation_id` + décision 16 | Vue de causalité dans Godot |

## C — Temps et asynchronisme

| Exigence | Niveau | Où | Preuve |
|----------|--------|----|--------|
| C1 Kafka justifié | Socle | `kafka_client.py` + docs/architecture | Granularité : 1 événement/fait + instantanés agrégés |
| C2 Population paramétrable | Socle | `config/simulation.yaml` + `agents/profiles.py` | `mode`, `count` depuis le YAML |
| C3 Double horodatage | Socle | `events.py` `t_prod` / `t_trait` | Champs dans chaque enveloppe |
| C4 Sync/async | Socle | `temporal.py` `Scheduler` | `mode` au lancement |
| C5 Comparaison modes | Standard | `experiments/runner.py` X3 + docs/hypotheses | Hypothèse H3 préenregistrée |
| C6 Cohérence temporelle | Standard | `oracle.py` + `rag/rag.py` disponible_tick | I5 = 0 attendu, test automatique |
| C7 Décalage sous charge | Excellence | `temporal.py` `processing_delay` | Distribution t_trait - t_prod |
| C8 Deux tailles | Excellence | `config/simulation.yaml` (count) | Runs 20 et 60 agents |

## D — Observation, inspection, perturbation

| Exigence | Niveau | Où | Preuve |
|----------|--------|----|--------|
| D1 Godot lisible | Socle | `godot/project/scripts/agent_view.gd` | Cercles colorés par croyance |
| D2 Inspection agent | Socle | `inspector_panel.gd` + `orchestrator._inspect()` | Mémoire + justification + RAG |
| D3 Injection live | Socle | `ws_server.py` `_handle_control()` | Annonce, fausse info, fermeture sortie |

## E — Démarche expérimentale

| Exigence | Niveau | Où | Preuve |
|----------|--------|----|--------|
| E1 Baseline règles | Socle | `experiments/runner.py` X4 + `rules_agent.py` | Même scénario, agents à seuils |
| E2 ≥5 runs × configs | Socle | `experiments/runner.py` — `n_runs`, `validate_experiments()` | 5 runs × 14 configurations ; médiane ± IQR + test exact de Mann-Whitney |
| E3 Rejeu identique | Socle | `replay.py` + test `test_rejeu_identique` | Hash des indicateurs identique |
| E4 Coût mesuré | Socle | `llm_gateway.py` `CostLog` | Bilan appels/tokens/latence |
| E5 Sobriété | Standard | `presets/maree.ini` E2B + bge-m3 Q4 résidents | Mesuré : 3692 Mio / 4096 ; E4B hors RAG (ne cohabite pas) |

## F — Données, RAG, traçabilité

| Exigence | Niveau | Où | Preuve |
|----------|--------|----|--------|
| F1 RAG décisions | Socle | `rag/rag.py` `retrieve_for()` (FAISS + bge-m3) | X7 : RAG activé vs désactivé ; taux de citation mesuré |
| F2 Qualité récup | Socle | `experiments/rag_eval.py` + `RagClient.degraded` | 30 questions annotées : P@1 = 0,733, P@3 = 0,867, MRR = 0,79 |
| F3 Stockage justifié | Socle | docs/architecture § stockage | Kafka=flux, JSONL=journal, DB=analyse |
| F4 Schémas versionnés | Socle | `events.py` `schema_version` + `EVENT_TYPES` | Événement invalide → dlq |
| F5 Requêtes reproductibles | Standard | `experiments/report.py` — `SQL_QUERIES` exécutées par DuckDB | Contrôle croisé journal ↔ résumé + tests non paramétriques |
| F6 Offsets sources | Standard | décision 16 + `metrics/indicators.py` | Clic indicateur → événements bruts |