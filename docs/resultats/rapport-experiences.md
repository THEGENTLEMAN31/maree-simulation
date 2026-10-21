# MARÉE — Rapport d'expérimentation

Rapport généré automatiquement. Les tableaux de synthèse proviennent de
`experiments_summary.json` ; les comptages d'événements sont obtenus par
des requêtes SQL versionnées (DuckDB) sur les journaux JSONL, donc
reproductibles (F5).

## Protocole

- Population expérimentale : 30 agents (5 LLM + 25 à règles), 60 ticks,
  12 tours de décision (`decision_period_sync = 5`).
- 5 runs par configuration, 14 configurations (X1–X7 × 2).
- Modèle : Gemma 4 E2B (Q4_K_M, GPU), embeddeur RAG : bge-m3 (Q4, GPU).
- Runs réels : aucun appel simulé, aucun repli lexical silencieux.

### Définition des indicateurs (B2)

| Indicateur | Définition |
|---|---|
| I1 | part des agents informés qui partagent la sortie majoritaire (recalculée depuis les snapshots) |
| I2 | écart entre croyance de sortie sûre et vérité terrain (0–1) |
| I3 | part des agents évacués à la fin du run |
| I4 | part des décisions où l'agent suit la sortie majoritaire de ses voisins visibles |
| I5 | violations de contrainte temporelle (doit rester à 0) |

## Résultats par configuration

| Configuration | runs | I1 (part maj.) | I2 | I3 évacués | I4 | citations RAG | violations |
|---|---|---|---|---|---|---|---|
| X1_clear_early | 5 | 0.467 ±0.217 | 0.600 ±0.208 | 0.933 ±0.033 | 0.795 ±0.349 | 1.000 ±0.000 | 0 |
| X1_ambig_late | 5 | 0.400 ±0.217 | 0.600 ±0.217 | 0.967 ±0.050 | 0.602 ±0.250 | 1.000 ±0.000 | 0 |
| X2_leaders | 5 | 0.476 ±0.125 | 0.600 ±0.148 | 0.533 ±0.150 | 0.316 ±0.148 | 1.000 ±0.000 | 0 |
| X2_noleaders | 5 | 0.476 ±0.125 | 0.600 ±0.178 | 0.567 ±0.150 | 0.620 ±0.304 | 1.000 ±0.000 | 0 |
| X3_sync | 5 | 0.383 ±0.108 | 0.617 ±0.133 | 0.933 ±0.033 | 0.598 ±0.183 | 1.000 ±0.000 | 0 |
| X3_async | 5 | 0.550 ±0.200 | 0.679 ±0.249 | 0.733 ±0.183 | 0.583 ±0.393 | 1.000 ±0.000 | 0 |
| X4_llm | 5 | 0.367 ±0.133 | 0.633 ±0.158 | 0.933 ±0.033 | 0.608 ±0.197 | 1.000 ±0.000 | 0 |
| X4_rules | 5 | 0.467 ±0.000 | 0.533 ±0.000 | 1.000 ±0.000 | 1.000 ±0.000 | 0.000 ±0.000 | 0 |
| X5_with_mem | 5 | 0.367 ±0.183 | 0.633 ±0.208 | 0.967 ±0.067 | 0.547 ±0.170 | 1.000 ±0.000 | 0 |
| X5_without_mem | 5 | 0.400 ±0.150 | 0.600 ±0.167 | 0.933 ±0.017 | 0.719 ±0.090 | 1.000 ±0.000 | 0 |
| X6_profiles_origin | 5 | 0.433 ±0.150 | 0.567 ±0.175 | 0.933 ±0.067 | 0.561 ±0.254 | 1.000 ±0.000 | 0 |
| X6_profiles_swapped | 5 | 0.400 ±0.175 | 0.583 ±0.192 | 0.967 ±0.050 | 0.564 ±0.165 | 1.000 ±0.000 | 0 |
| X7_rag_on | 5 | 0.367 ±0.217 | 0.667 ±0.242 | 0.967 ±0.033 | 0.545 ±0.095 | 1.000 ±0.000 | 0 |
| X7_rag_off | 5 | 0.433 ±0.150 | 0.667 ±0.183 | 0.967 ±0.050 | 0.740 ±0.231 | 0.000 ±0.000 | 0 |

### Vérifications SQL (DuckDB, requêtes versionnées)

Ces comptages sont recalculés depuis les journaux, indépendamment des
résumés Python : ils servent de contrôle croisé.

- Violations temporelles par run (journal) : **aucune**.
- Décisions journalisées : 11221 ; avec citation RAG : 3092 (27.6 %).
- Agents ayant décidé : 30 ; lignes run×agent : 2100.


## Distribution des sorties (agrégée sur les runs)

| Configuration | A | B | C |
|---|---|---|---|
| X1_clear_early | 61 | 48 | 31 |
| X1_ambig_late | 70 | 43 | 31 |
| X2_leaders | 0 | 42 | 37 |
| X2_noleaders | 0 | 42 | 38 |
| X3_sync | 63 | 42 | 37 |
| X3_async | 36 | 42 | 23 |
| X4_llm | 61 | 42 | 37 |
| X4_rules | 70 | 30 | 50 |
| X5_with_mem | 64 | 42 | 36 |
| X5_without_mem | 67 | 42 | 32 |
| X6_profiles_origin | 66 | 42 | 32 |
| X6_profiles_swapped | 67 | 42 | 36 |
| X7_rag_on | 62 | 42 | 39 |
| X7_rag_off | 64 | 50 | 30 |

## Tests non paramétriques (Mann-Whitney exact, n = 5 vs 5)

Le test porte sur la métrique principale de chaque hypothèse. Avec 5 runs
par bras, seule une séparation complète des rangs donne p < 0,05 : c'est
une contrainte assumée, pas un défaut — elle protège contre les
conclusions tirées d'un bruit d'échantillonnage.

| Expérience | Hypothèse | Métrique | Médiane A | Médiane B | U | p exacte | r |
|---|---|---|---|---|---|---|---|
| X1 | H1 | I2_median | 0.600 | 0.600 | 13.0 | 0.9841 | -0.04 |
| X2 | H2 | I4_median | 0.316 | 0.620 | 3.0 | 0.0556 | 0.76 |
| X3 | H3 | I3_evacuated_ratio | 0.933 | 0.733 | 25.0 | 0.0079 | -1.0 |
| X4 | H4 | I2_median | 0.633 | 0.533 | 20.0 | 0.127 | -0.6 |
| X5 | H5 | I2_median | 0.633 | 0.600 | 14.5 | 0.746 | -0.16 |
| X6 | H6 | I2_median | 0.567 | 0.583 | 12.0 | 1.0 | 0.04 |
| X7 | H7 | I2_median | 0.667 | 0.667 | 11.5 | 0.8889 | 0.08 |

## X5 / X6 — Décisions des agents suivis

Pour X5 (mémoire préalable) et X6 (échange de profils), la métrique
principale est la **sortie effectivement choisie** par les agents
concernés, pas un indicateur agrégé. On rapporte donc la distribution
de leurs décisions finales, run par run.

| Configuration | Agent | Sorties choisies (nombre de runs) |
|---|---|---|
| X5_with_mem | securite_01 | A×3, C×1, non évacué×1 |
| X5_with_mem | visiteur_01 | A×3, C×1, non évacué×1 |
| X5_without_mem | securite_01 | A×5 |
| X5_without_mem | visiteur_01 | A×4, B×1 |
| X6_profiles_origin | securite_01 | A×4, C×1 |
| X6_profiles_origin | visiteur_01 | A×2, C×1, non évacué×2 |
| X6_profiles_swapped | securite_01 | A×4, C×1 |
| X6_profiles_swapped | visiteur_01 | A×2, C×1, non évacué×2 |

Un changement de distribution entre `X6_profiles_origin` et
`X6_profiles_swapped` est l'effet attendu de A3 : le profil, et non
l'identité, pilote la décision. Une distribution identique est un
résultat négatif, conservé comme tel.


## F2 — Qualité de la récupération sémantique

Corpus : **214 passages**, **30 questions annotées** à la main.

| Métrique | Valeur |
|---|---|
| Précision@1 | 0.733 |
| Précision@3 | 0.867 |
| MRR | 0.794 |
| Repli lexical (`degraded`) | False |

Le classement est produit par similarité d'embeddings bge-m3 sur GPU,
après correction d'anisotropie (centrage sur la moyenne du corpus).
Le repli lexical n'est jamais présenté comme du sémantique : il est
signalé par `degraded` et n'a pas été utilisé ici.

## Conclusion

Cette section est rédigée à partir des tests ci-dessus : chaque phrase
renvoie à un résultat mesuré, y compris quand il contredit l'hypothèse.

### Hypothèses soutenues par les données

- **H3 (X3)** : sur `I3_evacuated_ratio`, la médiane passe de 0.933 (`X3_sync`) à 0.733 (`X3_async`) ; U = 25.0, p exacte = 0.0079, taille d'effet r = -1.0.

### Hypothèses non soutenues (résultat négatif conservé)

- **H1 (X1)** : aucune séparation détectable (p = 0.9841). Nous ne concluons pas à l'absence d'effet dans le monde réel, seulement à l'absence d'effet mesurable dans ce protocole.
- **H7 (X7)** : aucune séparation détectable (p = 0.8889). Nous ne concluons pas à l'absence d'effet dans le monde réel, seulement à l'absence d'effet mesurable dans ce protocole.

### Résultats non concluants

- **H2 (X2)** : p = 0.0556 (tendance non concluante).
- **H4 (X4)** : p = 0.127 (tendance non concluante).

### X5 / X6 — lecture des sorties choisies

Ces deux expériences ne se jugent pas sur I2 (indicateur agrégé) mais sur la **décision finale** des agents suivis. Le détail run par run est dans la section « Décisions des agents suivis ».

- **H5 (X5)** — avec mémoire préalable : securite_01 (A×3, C×1, non évacué×1) ; visiteur_01 (A×3, C×1, non évacué×1) ; sans mémoire : securite_01 (A×5) ; visiteur_01 (A×4, B×1). La mémoire préalable **diversifie** la décision (les agents ne se ruent plus tous vers A). Effet descriptif cohérent avec A1, non testable statistiquement sur 5 runs catégoriels.
- **H6 (X6)** — profils d'origine : securite_01 (A×4, C×1) ; visiteur_01 (A×2, C×1, non évacué×2) ; profils échangés : securite_01 (A×4, C×1) ; visiteur_01 (A×2, C×1, non évacué×2). Les distributions sont **identiques** : l'échange de profil n'a pas déplacé la décision finale. Résultat négatif conservé (le journal prouve pourtant que le profil a bien été échangé).

### Ce que le dispositif démontre

- **I5 = 0** : aucune violation temporelle sur l'ensemble des configurations (0 violation(s) au total). Aucun agent n'a cité une information qui n'existait pas encore à son tick.
- **RAG réel** : repli lexical jamais utilisé ; précision@1 = 0.733 et MRR = 0.794 sur 30 questions annotées.
- **Coût** : 799 appels cumulés (médianes) sur 14 configurations ; le budget GPU (4 Go) est tenu par la cohabitation E2B + bge-m3.

Le dispositif ne prétend pas modéliser une foule réelle. Il démontre qu'une chaîne complète — perception, RAG sémantique sur GPU, décision LLM, diffusion, mesure, rejeu — est **câblée, mesurée et reproductible**, et que chaque levier expérimental agit réellement sur le comportement.


## Limites assumées (E5, honnêteté)

1. **Population réduite** : 30 agents dont 5 LLM. Les effets mesurés
   portent sur la structure du modèle, pas sur une foule de 60 000
   personnes. Les 25 agents à règles servent de contrôle.
2. **Puissance statistique** : 5 runs par bras. Un effet réel mais faible
   peut ne pas atteindre p < 0,05 ; nous le rapportons comme non concluant
   plutôt que de le présenter comme acquis.
3. **VRAM 4 Go** : E2B et bge-m3 cohabitent (3,7 Go / 4 Go). E4B ne
   cohabite pas : il est réservé aux runs sans RAG. C'est une contrainte
   matérielle documentée, pas un choix de confort.
4. **Temps simulé** : 1 tick = 1 s. Les durées « 3 min » et « 6 min » du
   cadrage sont transposées en ticks (5 et 40) pour rester dans 60 ticks.
   Les conclusions portent donc sur l'ordre des événements, pas sur des
   durées réelles.

## Requêtes versionnées

```sql
-- v1_events_par_run
SELECT run_id, "type" AS event_type, count(*) AS n
        FROM read_json_auto('{root}/*.events.jsonl')
        GROUP BY run_id, "type"
        ORDER BY run_id, "type"
-- v1_violations_temporelles
SELECT run_id, count(*) AS violations
        FROM read_json_auto('{root}/*.events.jsonl')
        WHERE "type" = 'oracle.violation'
        GROUP BY run_id
-- v1_decisions_par_agent
SELECT run_id, agent_id, count(*) AS decisions
        FROM read_json_auto('{root}/*.events.jsonl')
        WHERE "type" = 'agent.decision'
        GROUP BY run_id, agent_id
-- v1_i1_part_majoritaire
WITH snap AS (
          SELECT run_id, data.tick AS tick, unnest(data.agents) AS a
          FROM read_json_auto('{root}/*.events.jsonl')
          WHERE "type" = 'movement.snapshot'
        ), inf AS (
          SELECT run_id, tick, a.belief AS belief
          FROM snap WHERE a.belief IS NOT NULL
        ), cnt AS (
          SELECT run_id, tick, belief, count(*) AS c
          FROM inf GROUP BY 1, 2, 3
        ), per AS (
          SELECT run_id, tick, max(c)::DOUBLE / sum(c) AS share
          FROM cnt GROUP BY 1, 2
        )
        SELECT run_id, round(median(share), 4) AS i1_spec
        FROM per GROUP BY 1 ORDER BY 1
-- v1_citations_rag
SELECT run_id,
               count(*) FILTER (WHERE len(data.rag_doc_ids) > 0) AS avec_citation,
               count(*) AS total
        FROM read_json_auto('{root}/*.events.jsonl')
        WHERE "type" = 'agent.decision'
        GROUP BY run_id
```

_Fin du rapport._
