# Correspondance aux 32 exigences du cahier des charges

Le cadrage complet est dans `docs/cadrage-maree.md` (copie de
`MARÉE — Cadrage du projet.md`). Ce document dit **où** chaque exigence vit
dans le dépôt, avec quel niveau de preuve réel.

**Légende des statuts**

- **LIVRÉ** : le code existe, il est exercé par un test ou un artefact
  reproductible, et la preuve correspond à ce que demande le cadrage.
- **PARTIEL** : une partie substantielle existe, mais il manque un élément
  nommé dans la colonne « ce qui manque ».
- **ABSENT** : rien de vérifiable dans le dépôt.

> **Honnêteté.** Un audit du 22/10 a confronté chaque revendication au code.
> Plusieurs lignes étaient marquées « couvertes » à tort (B4, C7, E3, F6,
> B3, I5). Elles sont corrigées ci-dessous. Le socle exécutable est réel,
> mais il ne faut pas confondre « le code existe » et « l'exigence est
> prouvée ».

## A — Agents qui pensent et se souviennent

| Exigence | Statut | Où | Preuve / ce qui manque |
|---|---|---|---|
| A1 Mémoire propre | PARTIEL | `agents/llm_agent.py` (`remember`, `MemoryEntry`), `orchestrator._seed_memories` | Mémoire datée en temps simulé, utilisée par X5. Manque : phase de 3 jours (le saut `pre_days_ticks` ne dure que 72 min), un seul souvenir amorcé par profil, `agent.memory_set` jamais émis. |
| A2 Échanges langage naturel | PARTIEL | `orchestrator._messages` (`agent.message`) | Les agents LLM émettent un message, journalisé et mémorisé par les voisins. Manque : les agents à règles n'émettent pas ; le levier `communication` coupe désormais `neighbor_beliefs` (correctif 22/10) mais aucun run dédié ne mesure la chute de I1. |
| A3 Profils différenciés | LIVRÉ | `agents/profiles.py`, prompts `llm_agent.py`, `swap_profiles` | 6 profils, priorités et savoirs distincts ; X6 exécuté. Résultat négatif (décisions identiques) conservé. Le swap ne change que le profil, pas le modèle. |
| A4 Robustesse aux dérives | PARTIEL | `llm_agent.drift_events`, `llm_gateway` | Détection JSON invalide / action invalide, repli `stay`, compteur dans le résumé. Depuis le 22/10 chaque dérive est journalisée (`agent.drift`). Manque : 2 types seulement, pas de détection de sortie de rôle. |
| A5 Modèles différents | PARTIEL | `config/simulation.yaml`, `presets/maree.ini` | E2B et E4B configurés et testés en e2e. Manque : X1–X7 utilisent tous E2B ; E5 (mixte vs tout-grand-modèle) n'est pas mesuré. |
| A6 Règles + LLM | LIVRÉ | `agents/rules_agent.py`, `profiles.py` | 15 LLM + 45 règles dans la config de démo ; protocole expérimental à 5 LLM + 25 règles. |

## B — Contexte commun mesurable

| Exigence | Statut | Où | Preuve / ce qui manque |
|---|---|---|---|
| B1 Contexte commun défini | PARTIEL | `metrics/indicators.py` (I1, I2) | Le consensus et l'écart portent sur la **sortie** ; `belief_danger` existe mais n'entre dans aucun indicateur agrégé. |
| B2 Indicateurs live | LIVRÉ | `metrics/indicators.py`, `godot/project/scripts/indicators.gd` | I1, I2, I4 en courbes, I3 en pourcentage, I5 en compteur ; axe = tick réel, échelle fixe 0..1, pas d'interpolation mensongère. Réserve : I1 live (composite) et I1 du rapport (part majoritaire recalculée) sont deux définitions documentées. |
| B3 Distingue émergence / ressemblance | PARTIEL | `control_panel.gd` (annonce neutre), `_perception_for` (levier `communication`) | Correctifs 22/10 : annonce neutre disponible, croyances voisines réellement coupées quand `communication=False`. Manque : aucun run de contrôle « communication off » ni « annonce neutre » dans les 70 runs ; diversité des justifications non mesurée. X4 n'est pas un contrôle négatif. |
| B4 Vue de causalité | ABSENT | — | Aucune vue de causalité, `causation_id` jamais renseigné, pas d'offsets. Non revendiqué. |

## C — Temps et asynchronisme

| Exigence | Statut | Où | Preuve / ce qui manque |
|---|---|---|---|
| C1 Kafka justifié | PARTIEL | `kafka_client.py`, `orchestrator._emit_snapshot` | 1 instantané agrégé par tick, types versionnés, `control.inject` journalisé. Godot interpole entre instantanés (correctif 22/10). Manque : `agent.perception`, `agent.belief_change`, `movement.zone_enter`, `agent.rag_retrieval` déclarés mais jamais émis. |
| C2 Population paramétrable | LIVRÉ | `config.py`, `simulation.yaml`, `profiles.py` | Population, mode, ticks depuis le YAML. Quelques constantes restent en dur (port, intervalles de pensée) : ce n'est pas parfait, c'est documenté. |
| C3 Double horodatage | PARTIEL | `events.py` (`t_prod`, `t_trait`, `t_real_ms`) | Champs présents dans chaque enveloppe. Manque : `processing_delay_ticks=0`, donc `t_trait == t_prod` en pratique. |
| C4 Sync/async | PARTIEL | `temporal.py`, `Scheduler` | Deux modes exécutés (X3). L'asynchrone reste séquentiel : décision et application dans le même tick, pas de décision sur état périmé. |
| C5 Comparaison modes | PARTIEL | `experiments/runner.py` X3 | X3 significatif (93,3 % vs 73,3 %, p=0,0079), mais confondu par le nombre d'appels (64 vs 19) et testé sur le taux d'évacuation, pas la répartition entre sorties de H3. |
| C6 Cohérence temporelle | PARTIEL | `oracle.py`, `orchestrator.run`, `events.py` | Correctif 22/10 : l'oracle est appelé à chaque tick, `oracle.violation` est un type versionné et un test vérifie qu'il détecte un message arrivé après la décision. Limite : délai nul, donc I5=0 ne prouve pas l'absence de péremption async. |
| C7 Décalage sous charge | ABSENT | `temporal.processing_delay_ticks` (jamais alimenté) | Aucune distribution `t_trait - t_prod`, aucun test sous rafale. Non revendiqué. |
| C8 Deux tailles de population | ABSENT | `simulation.yaml` (count) | Aucun run 20/60 enregistré et comparé. Non revendiqué. |

## D — Observation, inspection, perturbation

| Exigence | Statut | Où | Preuve |
|---|---|---|---|
| D1 Godot lisible | LIVRÉ | `godot/project/scripts/agent_view.gd`, `header.gd` | Carte par zones (nord en haut), sorties A/B/C avec état, fumée, éventail déterministe, interpolation, couleurs + formes redondantes, compteurs. Captures dans `docs/resultats/captures/`. |
| D2 Inspection agent | LIVRÉ | `orchestrator._inspect`, `inspector_panel.gd` | Zone, croyance, mémoire, passages RAG avec scores, règle appliquée et **justification de la dernière décision** (correctif 22/10). |
| D3 Injection live | LIVRÉ | `ws_server.py`, `control_panel.gd` | 4 événements (annonce claire, annonce neutre, fausse info, fermeture A avec double confirmation), journalisés (`control.inject`) et accusés réception (`control_ack`). Réserve : la fausse info n'est pas lue par les agents à règles. |

## E — Démarche expérimentale

| Exigence | Statut | Où | Preuve / ce qui manque |
|---|---|---|---|
| E1 Baseline règles | LIVRÉ | `rules_agent.py`, X4 | Agents miroirs à règles, même scénario ; X4 exécuté (p=0,127, non concluant). |
| E2 ≥5 runs × configs | LIVRÉ | `experiments/runner.py`, `docs/resultats/` | 14 configurations × 5 runs = 70 runs réels ; médiane/IQR, Mann-Whitney exact (252 partitions), rapport et JSON de synthèse. |
| E3 Rejeu identique | PARTIEL | `replay.py`, `scripts/run_e2e.sh` | Le rejeu relit le journal et recalcule les indicateurs ; le hash est identique. Manque : reconstruction des décisions LLM (prompt/graine/sortie brute non journalisés) et test « run original vs rejeu ». |
| E4 Coût mesuré | PARTIEL | `llm_gateway.CostLog` | Appels, tokens et latences agrégés par run. Manque : coût par appel dans le journal, énergie (CodeCarbon/EcoLogits). |
| E5 Sobriété | ABSENT | — | Aucun bras « mixte vs tout-grand-modèle ». La mesure VRAM (3692/4096 Mio) n'est pas une preuve E5. Non revendiqué. |

## F — Données, RAG, traçabilité

| Exigence | Statut | Où | Preuve / ce qui manque |
|---|---|---|---|
| F1 RAG décisions | LIVRÉ | `rag/rag.py` (`bge-m3` + FAISS), `llm_agent.decide` | RAG réel, accès par profil + date, `rag_doc_ids` journalisés ; X7 exécuté (résultat négatif). Manque : scores non journalisés. |
| F2 Qualité récupération | PARTIEL | `experiments/rag_eval.py`, `docs/resultats/rag_eval.json` | 30 questions annotées : P@1=0,733, P@3=0,867, MRR=0,794, `degraded=false`. Ce ne sont pas 30 décisions tirées au hasard par run ; pas de seuil « récupération douteuse ». |
| F3 Stockage justifié | PARTIEL | `docs/architecture.md`, JSONL | Kafka = flux, JSONL = journal, DuckDB pour l'analyse. Pas de writer Parquet ; le tableau d'architecture mentionne encore Chroma alors que l'index est FAISS. |
| F4 Schémas versionnés + DLQ | PARTIEL | `events.py` (`schema_version`, `EVENT_TYPES`) | Types validés et versionnés. Manque : `dlq.invalid` n'est jamais publié ; un type inconnu lève au lieu d'être isolé. |
| F5 Requêtes reproductibles | PARTIEL | `experiments/report.py` (SQL DuckDB) | Requêtes versionnées exécutées, contrôle croisé journal ↔ résumé. Les tableaux principaux viennent du JSON de résumé, pas tous du SQL ; pas de figures générées. |
| F6 Offsets sources | ABSENT | — | `sources={}`, offsets Kafka non capturés, aucun clic indicateur → événements. Non revendiqué. |

## Corrections du 22/10 (traçables dans le journal)

1. Refonte de l'interface Godot (D1/B2/D3) : panneaux hors écran corrigés,
   carte réorientée, agents éventaillés, fumée, sorties, courbes avec axe
   temporel, inspecteur D2 complet.
2. `state` enrichi (compteurs, sorties, `max_ticks`, évacués/piégés) ;
   `inspection` enrichie (profil, justification, intention) ; `control_ack`.
3. Injections D3 journalisées (`control.inject`) ; annonce neutre ajoutée ;
   double confirmation de fermeture.
4. Oracle C6 branché à chaque tick ; type `oracle.violation` versionné ;
   test de non-régression.
5. Dérives A4 journalisées (`agent.drift`).
6. Levier `communication` (B3) coupe réellement les croyances voisines.
7. Tests : 22 pytest hôte (20 conteneur), 27 composants Godot, 8 WS, e2e réel
   6/6 + rejeu 47 événements.

## Ce qui n'est pas revendiqué

- **B4** (vue de causalité), **C7** (décalage sous charge), **C8** (runs
  20/60), **E5** (mixte vs grand modèle), **F6** (offsets → clic indicateur).
- **B3** au sens complet : les contrôles « communication off » et « annonce
  neutre » sont câblés mais n'ont pas de runs dédiés dans le protocole ; la
  diversité des justifications n'est pas mesurée.
- **E3** comme rejeu intégral : les décisions LLM ne sont pas reconstructibles
  à partir du journal seul.
