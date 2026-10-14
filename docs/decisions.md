# Décisions d'architecture (figées au jour 1)

Source : cadrage § « Décisions à figer dès le jour 1 ». Ces décisions sont
**contractuelles** : les ajouter après coup reviendrait à tout reprendre.
Chaque décision indique ce qui casse si on ne la tient pas.

| # | Décision | Ce qui casse si on l'ajoute après | Exigences liées |
|---|----------|-------------------------------------|-----------------|
| 1 | Le journal d'événements est la source de vérité ; toute sortie LLM y est enregistrée (modèle, graine, prompt, tokens, latence) | Une sortie LLM non enregistrée est perdue : rejeu impossible | E3, F6, E4 |
| 2 | Double horodatage sur chaque événement : t_prod, t_trait, heure réelle | Il faut rouvrir tous les schémas ; aucun décalage mesurable | C3, C6, C7 |
| 3 | Déterminisme : graine par run/agent, ordre canonique (seq), pas d'horloge système dans la logique | Un non-déterminisme se traque très mal ; rejeu non identique | E3 |
| 4 | Enveloppe commune versionnée : run_id, event_id, type, schema_version, agent_id, t_prod, t_trait, causation_id | Sans causation_id, remonter aux échanges est impossible | F4, F6, B4 |
| 5 | Identité de run = run_id + hash de configuration | Les 5 runs/config ne s'agrègent pas | E2, F5 |
| 6 | Interface unique `decide(perception) -> Intention` (LLM et règles) | Baseline et agents divergent, comparaison invalide | A6, E1 |
| 7 | Passerelle LLM unique (quotas, retries, timeout, repli règle, coût) | Mesurer le coût après coup = retoucher chaque appel | E4, A4, O7 |
| 8 | Frontière boucle rapide/lente : le moteur exécute les intentions | Passer graphe→continu impose de réécrire les agents | Échelle de repli |
| 9 | Godot est un consommateur pur du flux | Si Godot calcule un état, le rejeu ne reproduit pas la visu | D1, E3 |
| 10 | Ordonnanceur sync/async séparé des agents, perception figée à T | Le mode de temps s'infiltre dans les agents | C4, C5, C6 |
| 11 | Tous les paramètres dans le fichier de configuration | C2 interdit de modifier le code pour changer la population | C2 |
| 12 | Traçabilité RAG : chaque décision journalise les passages retrouvés | La qualité de la récupération n'est pas évaluable | F1, F2 |
| 13 | Hypothèses et graines préenregistrées, datées, avant expérience | Le jury peut soupçonner des hypothèses a posteriori | C5, E2 |
| 14 | Versions figées (lockfiles, tags Docker, modèles) | Un run ancien ne se rejoue plus | E3 |
| 15 | Chaque passage RAG porte date de disponibilité + profils autorisés | Un agent retrouve du futur → C6 violé | F1, C6, A1 |
| 16 | Chaque indicateur référence les offsets sources | Remonter aux événements bruts devient approximatif | F6, B4, D2 |

## État d'implémentation

| # | État | Où |
|---|------|----|
| 1 | ✔ | `replay.py` + `orchestrator._journal()` |
| 2 | ✔ | `events.py` |
| 3 | ✔ | `config.seed` + `seq` dans RunLogger + `temporal.py` |
| 4 | ✔ | `events.py` |
| 5 | ✔ | `config.config_hash()` |
| 6 | ✔ | `agents/base.py` |
| 7 | ✔ | `llm_gateway.py` |
| 8 | ✔ | `orchestrator._apply_intention()` |
| 9 | ✔ | `godot/` (scripts de rendu uniquement) |
| 10 | ✔ | `temporal.py` |
| 11 | ✔ | `config/simulation.yaml` |
| 12 | ⚠ | `rag/rag.py` journalise `last_rag` ; à alimenter par l'orchestrateur |
| 13 | ✔ | `docs/hypotheses.md` + `experiments/runner.py` |
| 14 | ⚠ | `uv.lock` à générer, tags Docker à fixer |
| 15 | ✔ | `rag/rag.py` (available_tick + allowed_profiles) |
| 16 | ⚠ | structure prête dans `_indicator_state` ; à câbler les offsets |

**Le test qui protège le reste** : `test_rejeu_identique_meme_config`
(tourne à chaque commit, compare le hash des indicateurs). S'il passe, les
décisions 1–4 et 9 tiennent.