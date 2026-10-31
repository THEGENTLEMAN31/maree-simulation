# MARÉE — résultats X1–X7 (campagne v2)

Rapport généré par `scripts/rapport_experiences.py` à partir des
`runs/experiment_x*.json` et des journaux JSONL. Aucun chiffre n'est
écrit à la main.

- **230 runs** mesurés, 14 protocoles.
- **13791 / 13791** appels LLM aboutis.
- Population de référence : 12 agents LLM + 48 à règles (X4 varie).
- Graines par protocole : X1 5, X2 5, X3 5, X4 5, X5 10, X6 10, X7 10, X8 5, X9 5, X10 5, X11 5, X12 5, X13 5, X14 10.
- Médiane [Q1–Q3], test de Mann-Whitney bilatéral entre le premier
  bras et chacun des autres.
- **Censure** : un run qui atteint `max_ticks` avant que tout le
  monde soit sorti produit un I4 égal au plafond (720 s en scénario
  `demo`, 900 s en `e2e`). Ce n'est pas une durée d'évacuation :
  c'est un run interrompu. Dans ce cas, lire I3 (part sortie).
  La table « runs non terminés » donne le compte par bras.
- **I4 et I7** : I4 est une horloge — le temps écoulé depuis t0 —
  donc il inclut l'attente avant le premier signal et se fige au
  plafond `max_ticks` dès qu'une partie de la foule ne sort pas
  (X1 ambigu : I4 = 720 s pour un dernier sorti à t31). I7 part du
  premier signal de danger et s'arrête au dernier sorti : il reste
  défini sous censure. Il ne retire pas l'heure de l'annonce (X1 :
  fumée à t5 dans tous les bras, donc I7 = I4 − 50 s), il retire
  le temps d'avant-signal et le plancher de censure. Il est publié
  avec I3 à côté : un délai court sur une foule à moitié sortie ne
  dit pas la même chose.

## Ce que mesure chaque indicateur

| indicateur | définition |
|---|---|
| I1 consensus | part des agents qui partagent la croyance majoritaire |
| I2 entropie | incertitude moyenne des croyances (0 = tous sûrs) |
| I3 évacués | part des agents sortis |
| I4 durée | durée d'évacuation observée (s) |
| I5 densité max | densité locale max, noyau de 2 m (pers/m²) |
| I6 écart | part des agents croyant en une sortie fermée |
| I7 délai | premier signal de danger → dernier sorti (s) |
| appels LLM | tentatives d'appel |
| temps mural | durée réelle du run (s) |

## X1 — H1

Indicateurs déclarés : I3_evacuated, I7_delay, I1_consensus, I2_entropy

### Par bras

| bras | n | I3 évacués | I7 délai | I1 consensus | I2 entropie |
|---|---|---|---|---|---|
| clair_tot | 5 | 1.00 [1.00–1.00] | 160.00 [160.00–160.00] | 0.98 [0.98–0.99] | 0.47 [0.46–0.52] |
| ambigu_tot | 5 | 0.98 [0.97–0.98] | 260.00 [260.00–260.00] | 0.99 [0.98–1.00] | 0.58 [0.57–0.60] |
| clair_tard | 5 | 1.00 [1.00–1.00] | 280.00 [270.00–290.00] | 0.98 [0.97–0.99] | 0.50 [0.47–0.56] |
| ambigu_tard | 5 | 0.98 [0.97–1.00] | 270.00 [270.00–270.00] | 0.99 [0.98–0.99] | 0.56 [0.50–0.58] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| clair_tot | 0/5 | 1.00 | 210.00 |
| ambigu_tot | 4/5 | 0.98 | 370.00 |
| clair_tard | 0/5 | 1.00 | 330.00 |
| ambigu_tard | 3/5 | 0.98 | 350.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I3_evacuated | clair_tot vs ambigu_tot | 0.0248 |
| I7_delay | clair_tot vs ambigu_tot | 0.0185 |
| I1_consensus | clair_tot vs ambigu_tot | 0.4206 |
| I2_entropy | clair_tot vs ambigu_tot | 0.0079 |
| I3_evacuated | clair_tot vs clair_tard | constante |
| I7_delay | clair_tot vs clair_tard | 0.0107 |
| I1_consensus | clair_tot vs clair_tard | 1.0000 |
| I2_entropy | clair_tot vs clair_tard | 0.4206 |
| I3_evacuated | clair_tot vs ambigu_tard | 0.0720 |
| I7_delay | clair_tot vs ambigu_tard | 0.0102 |
| I1_consensus | clair_tot vs ambigu_tard | 0.4206 |
| I2_entropy | clair_tot vs ambigu_tard | 0.0952 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| clair_tot | 160.00 [160.00–160.00] | 1.00 | 21, 21, 21, 20, 26 | llm, rules, rules, llm, llm | 3/5 |
| ambigu_tot | 260.00 [260.00–260.00] | 0.98 | 37, 31, 25, 31, 31 | rules, rules, llm, rules, rules | 1/5 |
| clair_tard | 280.00 [270.00–290.00] | 1.00 | 32, 34, 34, 32, 33 | rules, rules, rules, rules, rules | 0/5 |
| ambigu_tard | 270.00 [270.00–270.00] | 0.98 | 38, 32, 27, 32, 32 | rules, rules, llm, rules, rules | 1/5 |

### Annonces délivrées

| bras | runs avec au moins une décision déclenchée par l'annonce |
|---|---|
| clair_tot | 5/5 |
| ambigu_tot | 5/5 |
| clair_tard | 5/5 |
| ambigu_tard | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| clair_tot | A 52, B 5, C 5 | A 201, B 8, C 23 |
| ambigu_tot | A 46, B 4, C 7 | A 169, B 8, C 39 |
| clair_tard | A 48, B 4, C 9 | A 187, B 8, C 37 |
| ambigu_tard | A 47, B 4, C 8 | A 168, B 8, C 39 |

## X2 — H2

Indicateurs déclarés : I6_belief_gap, I3_evacuated, I7_delay, I5_max_density

### Par bras

| bras | n | I6 écart | I3 évacués | I7 délai | I5 densité max |
|---|---|---|---|---|---|
| avec_meneurs | 5 | 1.00 [1.00–1.00] | 0.90 [0.78–0.92] | 220.00 [220.00–220.00] | 0.40 [0.32–0.56] |
| sans_meneurs | 5 | 1.00 [1.00–1.00] | 0.92 [0.78–0.93] | 150.00 [150.00–150.00] | 0.48 [0.40–0.56] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_meneurs | 4/5 | 0.90 | 290.00 |
| sans_meneurs | 4/5 | 0.92 | 210.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I6_belief_gap | avec_meneurs vs sans_meneurs | constante |
| I3_evacuated | avec_meneurs vs sans_meneurs | 0.7518 |
| I7_delay | avec_meneurs vs sans_meneurs | 0.0833 |
| I5_max_density | avec_meneurs vs sans_meneurs | 0.7424 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec_meneurs | 220.00 [220.00–220.00] | 0.90 | 28, 28, 29, 28, 21 | llm, llm, llm, llm, llm | 5/5 |
| sans_meneurs | 150.00 [150.00–150.00] | 0.92 | 21, 21, 21, 21, 28 | llm, llm, rules, rules, llm | 3/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_meneurs | A 56, B 15, C 23 | A 108, B 14, C 87 |
| sans_meneurs | A 39, B 4, C 19 | A 131, B 12, C 85 |

## X3 — H3

Indicateurs déclarés : I1_consensus, I5_max_density, wall_s

### Par bras

| bras | n | I1 consensus | I5 densité max | temps mural |
|---|---|---|---|---|
| synchrone | 5 | 0.96 [0.95–0.97] | 0.48 [0.40–0.48] | 34.00 [34.00–34.60] |
| asynchrone | 5 | 0.96 [0.95–0.97] | 0.40 [0.40–0.48] | 20.90 [20.90–21.10] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| synchrone | 0/5 | 1.00 | 200.00 |
| asynchrone | 0/5 | 1.00 | 200.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | synchrone vs asynchrone | 0.8413 |
| I5_max_density | synchrone vs asynchrone | 0.5839 |
| wall_s | synchrone vs asynchrone | 0.0117 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| synchrone | 100.00 [100.00–100.00] | 1.00 | 20, 21, 20, 20, 20 | rules, llm, rules, llm, rules | 2/5 |
| asynchrone | 100.00 [100.00–100.00] | 1.00 | 20, 20, 20, 20, 20 | rules, rules, rules, llm, rules | 1/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| synchrone | A 50, B 5, C 13 | A 169, B 8, C 55 |
| asynchrone | A 52, B 6, C 12 | A 169, B 8, C 55 |

## X4 — H4

Indicateurs déclarés : I6_belief_gap, I3_evacuated, I7_delay, llm_calls, wall_s

### Par bras

| bras | n | I6 écart | I3 évacués | I7 délai | appels LLM | temps mural |
|---|---|---|---|---|---|---|
| hybride_12 | 5 | 1.00 [1.00–1.00] | 0.92 [0.90–0.92] | 220.00 [150.00–220.00] | 43.00 [43.00–59.00] | 30.90 [30.50–39.80] |
| regles_60 | 5 | 1.00 [1.00–1.00] | 0.92 [0.90–0.95] | 150.00 [150.00–150.00] | 0.00 [0.00–0.00] | 9.60 [9.10–9.60] |
| llm_60 | 5 | 1.00 [1.00–1.00] | 0.67 [0.67–0.68] | 350.00 [340.00–410.00] | 520.00 [515.00–586.00] | 234.80 [228.50–264.70] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| hybride_12 | 5/5 | 0.92 | — |
| regles_60 | 4/5 | 0.92 | 210.00 |
| llm_60 | 5/5 | 0.67 | — |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I6_belief_gap | hybride_12 vs regles_60 | constante |
| I3_evacuated | hybride_12 vs regles_60 | 0.7503 |
| I7_delay | hybride_12 vs regles_60 | 0.1175 |
| llm_calls | hybride_12 vs regles_60 | 0.0073 |
| wall_s | hybride_12 vs regles_60 | 0.0119 |
| I6_belief_gap | hybride_12 vs llm_60 | constante |
| I3_evacuated | hybride_12 vs llm_60 | 0.0117 |
| I7_delay | hybride_12 vs llm_60 | 0.0117 |
| llm_calls | hybride_12 vs llm_60 | 0.0119 |
| wall_s | hybride_12 vs llm_60 | 0.0079 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| hybride_12 | 220.00 [150.00–220.00] | 0.92 | 28, 29, 21, 28, 21 | llm, llm, llm, llm, rules | 4/5 |
| regles_60 | 150.00 [150.00–150.00] | 0.92 | 21, 20, 21, 27, 21 | rules, rules, rules, rules, rules | 0/5 |
| llm_60 | 350.00 [340.00–410.00] | 0.67 | 49, 47, 35, 40, 41 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| hybride_12 | A 54, B 13, C 21 | A 110, B 14, C 87 |
| regles_60 | — | A 156, B 14, C 103 |
| llm_60 | A 560, B 89, C 101 | — |

## X5 — H5

Indicateurs déclarés : I1_consensus, I2_entropy, I3_evacuated, I7_delay

### Par bras

| bras | n | I1 consensus | I2 entropie | I3 évacués | I7 délai |
|---|---|---|---|---|---|
| avec_memoire | 10 | 0.96 [0.95–0.97] | 0.44 [0.43–0.45] | 1.00 [1.00–1.00] | 100.00 [100.00–100.00] |
| sans_memoire | 10 | 0.96 [0.95–0.97] | 0.44 [0.41–0.45] | 1.00 [1.00–1.00] | 100.00 [100.00–100.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_memoire | 0/10 | 1.00 | 200.00 |
| sans_memoire | 0/10 | 1.00 | 200.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | avec_memoire vs sans_memoire | 0.6776 |
| I2_entropy | avec_memoire vs sans_memoire | 0.5205 |
| I3_evacuated | avec_memoire vs sans_memoire | constante |
| I7_delay | avec_memoire vs sans_memoire | 0.5428 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec_memoire | 100.00 [100.00–100.00] | 1.00 | 20, 20, 20, 20, 20, 20, 21, 20, 20, 25 | rules, rules, rules, llm, rules, rules, rules, rules, llm, llm | 3/10 |
| sans_memoire | 100.00 [100.00–100.00] | 1.00 | 20, 20, 20, 20, 20, 20, 21, 20, 20, 20 | rules, rules, rules, rules, rules, rules, rules, rules, rules, rules | 0/10 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_memoire | A 98, B 14, C 25 | A 336, B 33, C 102 |
| sans_memoire | A 100, B 15, C 14 | A 336, B 33, C 102 |

## X6 — H6

Indicateurs déclarés : I1_consensus, I3_evacuated, I7_delay

### Par bras

| bras | n | I1 consensus | I3 évacués | I7 délai |
|---|---|---|---|---|
| visiteurs_seuls | 10 | 1.00 [1.00–1.00] | 1.00 [1.00–1.00] | 90.00 [90.00–100.00] |
| habitues_seuls | 10 | 0.93 [0.92–0.95] | 1.00 [1.00–1.00] | 100.00 [100.00–100.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| visiteurs_seuls | 0/10 | 1.00 | 190.00 |
| habitues_seuls | 0/10 | 1.00 | 200.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | visiteurs_seuls vs habitues_seuls | 0.0001 |
| I3_evacuated | visiteurs_seuls vs habitues_seuls | constante |
| I7_delay | visiteurs_seuls vs habitues_seuls | 0.0252 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| visiteurs_seuls | 90.00 [90.00–100.00] | 1.00 | 19, 20, 19, 19, 20, 20, 19, 19, 20, 19 | llm, rules, llm, llm, rules, rules, llm, llm, rules, llm | 6/10 |
| habitues_seuls | 100.00 [100.00–100.00] | 1.00 | 20, 20, 20, 19, 20, 20, 20, 20, 20, 20 | rules, rules, llm, rules, rules, rules, llm, rules, rules, rules | 2/10 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| visiteurs_seuls | A 40 | A 160 |
| habitues_seuls | A 31, B 13, C 4 | A 90, B 66, C 21 |

## X7 — H7

Indicateurs déclarés : I2_entropy, I1_consensus, I3_evacuated, I7_delay

### Par bras

| bras | n | I2 entropie | I1 consensus | I3 évacués | I7 délai |
|---|---|---|---|---|---|
| avec_rag | 10 | 0.44 [0.43–0.45] | 0.96 [0.95–0.97] | 1.00 [1.00–1.00] | 100.00 [100.00–100.00] |
| sans_rag | 10 | 0.54 [0.49–0.64] | 0.96 [0.95–0.99] | 1.00 [0.99–1.00] | 150.00 [102.50–160.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_rag | 0/10 | 1.00 | 200.00 |
| sans_rag | 3/10 | 1.00 | 260.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I2_entropy | avec_rag vs sans_rag | 0.0008 |
| I1_consensus | avec_rag vs sans_rag | 0.4274 |
| I3_evacuated | avec_rag vs sans_rag | 0.0776 |
| I7_delay | avec_rag vs sans_rag | 0.0160 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec_rag | 100.00 [100.00–100.00] | 1.00 | 20, 20, 20, 20, 20, 20, 21, 20, 20, 25 | rules, rules, rules, llm, rules, rules, rules, rules, llm, llm | 3/10 |
| sans_rag | 150.00 [102.50–160.00] | 1.00 | 32, 25, 26, 21, 20, 26, 25, 26, 20, 20 | llm, llm, rules, llm, rules, llm, llm, llm, llm, rules | 7/10 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_rag | A 98, B 15, C 23 | A 336, B 33, C 102 |
| sans_rag | A 110, B 5, C 9 | A 337, B 33, C 102 |

## X8 — B3

Indicateurs déclarés : I1_consensus, I2_entropy, I3_evacuated, I7_delay, messages

### Par bras

| bras | n | I1 consensus | I2 entropie | I3 évacués | I7 délai | messages |
|---|---|---|---|---|---|---|
| avec | 5 | 0.99 [0.99–0.99] | 0.33 [0.29–0.37] | 0.97 [0.95–0.98] | 460.00 [330.00–460.00] | 58.00 [57.00–58.00] |
| sans | 5 | 0.99 [0.99–0.99] | 0.46 [0.45–0.47] | 0.85 [0.85–0.87] | 210.00 [100.00–210.00] | 0.00 [0.00–0.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec | 5/5 | 0.97 | — |
| sans | 5/5 | 0.85 | — |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | avec vs sans | 0.3095 |
| I2_entropy | avec vs sans | 0.1508 |
| I3_evacuated | avec vs sans | 0.0107 |
| I7_delay | avec vs sans | 0.0150 |
| messages | avec vs sans | 0.0073 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec | 460.00 [330.00–460.00] | 0.97 | 43, 56, 38, 67, 56 | llm, llm, llm, llm, llm | 5/5 |
| sans | 210.00 [100.00–210.00] | 0.85 | 31, 20, 31, 38, 20 | llm, rules, llm, llm, llm | 4/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec | A 48, B 2, C 4 | A 169, B 8, C 55 |
| sans | A 17, C 1 | A 169, B 8, C 56 |

## X9 — A1

Indicateurs déclarés : I1_consensus, I3_evacuated, I7_delay, llm_calls

### Par bras

| bras | n | I1 consensus | I3 évacués | I7 délai | appels LLM |
|---|---|---|---|---|---|
| sans_passe | 5 | 0.99 [0.99–0.99] | 0.97 [0.95–0.98] | 390.00 [340.00–390.00] | 78.00 [77.00–78.00] |
| avec_passe | 5 | 0.99 [0.99–0.99] | 0.98 [0.97–0.98] | 460.00 [460.00–460.00] | 73.00 [72.00–80.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| sans_passe | 5/5 | 0.97 | — |
| avec_passe | 4/5 | 0.98 | 680.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | sans_passe vs avec_passe | 1.0000 |
| I3_evacuated | sans_passe vs avec_passe | 0.4432 |
| I7_delay | sans_passe vs avec_passe | 0.1339 |
| llm_calls | sans_passe vs avec_passe | 0.4620 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| sans_passe | 390.00 [340.00–390.00] | 0.97 | 61, 44, 38, 49, 49 | llm, llm, llm, llm, llm | 5/5 |
| avec_passe | 460.00 [460.00–460.00] | 0.98 | 49, 68, 56, 56, 56 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| sans_passe | A 50, B 2, C 3 | A 170, B 8, C 55 |
| avec_passe | A 44, B 1, C 9 | A 169, B 8, C 55 |

## X10 — C8 + C7

Indicateurs déclarés : I1_consensus, I3_evacuated, I7_delay, lag_indicator, lag_llm

### Par bras

| bras | n | I1 consensus | I3 évacués | I7 délai | lag_indicator | lag_llm |
|---|---|---|---|---|---|---|
| petite | 5 | 0.99 [0.99–0.99] | 0.95 [0.90–0.95] | 110.00 [100.00–150.00] | 1.50 [1.00–1.50] | 0.00 [0.00–0.00] |
| petite_async | 5 | 0.99 [0.99–0.99] | 0.90 [0.85–0.90] | 210.00 [210.00–250.00] | 3.50 [2.50–4.50] | 5.50 [4.50–5.50] |
| grande | 5 | 0.97 [0.97–0.97] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] | 1.50 [1.50–1.50] | 0.00 [0.00–0.00] |
| grande_async | 5 | 0.99 [0.98–0.99] | 1.00 [0.98–1.00] | 340.00 [330.00–340.00] | 2.50 [2.00–3.00] | 8.00 [8.00–8.50] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| petite | 5/5 | 0.95 | — |
| petite_async | 5/5 | 0.90 | — |
| grande | 1/5 | 1.00 | 325.00 |
| grande_async | 2/5 | 1.00 | 440.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | petite vs petite_async | 1.0000 |
| I3_evacuated | petite vs petite_async | 0.3193 |
| I7_delay | petite vs petite_async | 0.0117 |
| lag_indicator | petite vs petite_async | 0.0107 |
| lag_llm | petite vs petite_async | 0.0073 |
| I1_consensus | petite vs grande | 0.0952 |
| I3_evacuated | petite vs grande | 0.0088 |
| I7_delay | petite vs grande | 0.0887 |
| lag_indicator | petite vs grande | 0.6005 |
| lag_llm | petite vs grande | constante |
| I1_consensus | petite vs grande_async | 0.4206 |
| I3_evacuated | petite vs grande_async | 0.0099 |
| I7_delay | petite vs grande_async | 0.0117 |
| lag_indicator | petite vs grande_async | 0.0867 |
| lag_llm | petite vs grande_async | 0.0073 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| petite | 110.00 [100.00–150.00] | 0.95 | 20, 20, 26, 21, 25 | rules, rules, llm, llm, llm | 3/5 |
| petite_async | 210.00 [210.00–250.00] | 0.90 | 35, 29, 39, 31, 31 | llm, llm, llm, llm, llm | 5/5 |
| grande | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 20 | llm, llm, llm, llm, rules | 4/5 |
| grande_async | 340.00 [330.00–340.00] | 1.00 | 57, 36, 44, 44, 43 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| petite | A 30, C 1 | A 42, C 23 |
| petite_async | A 22, C 6 | A 57, C 24 |
| grande | A 59, B 2, C 2 | A 170, B 8, C 55 |
| grande_async | A 68, B 4, C 7 | A 249, B 8, C 59 |

## X11 — C4

Indicateurs déclarés : I1_consensus, I3_evacuated, I7_delay, lag_ticks_median, lag_ticks_max

### Par bras

| bras | n | I1 consensus | I3 évacués | I7 délai | lag_ticks_median | lag_ticks_max |
|---|---|---|---|---|---|---|
| sync | 5 | 0.98 [0.97–0.98] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] | 0.00 [0.00–0.00] | 0.00 [0.00–0.00] |
| async | 5 | 0.99 [0.99–0.99] | 0.98 [0.98–1.00] | 470.00 [310.00–480.00] | 5.00 [5.00–5.00] | 12.00 [12.00–13.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| sync | 1/5 | 1.00 | 325.00 |
| async | 3/5 | 0.98 | 575.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | sync vs async | 0.2222 |
| I3_evacuated | sync vs async | 0.2320 |
| I7_delay | sync vs async | 0.0107 |
| lag_ticks_median | sync vs async | 0.0040 |
| lag_ticks_max | sync vs async | 0.0067 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| sync | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| async | 470.00 [310.00–480.00] | 0.98 | 37, 41, 58, 58, 57 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| sync | A 58, B 1, C 1 | A 169, B 8, C 55 |
| async | A 75, B 1, C 6 | A 249, B 8, C 58 |

## X12 — E5

Indicateurs déclarés : I3_evacuated, I7_delay, llm_calls, tokens_in, tokens_out

### Par bras

| bras | n | I3 évacués | I7 délai | appels LLM | tokens_in | tokens_out |
|---|---|---|---|---|---|---|
| tous_grand | 5 | 1.00 [1.00–1.00] | 110.00 [100.00–160.00] | 48.00 [46.00–51.00] | 18492.00 [17786.00–20096.00] | 1964.00 [1907.00–2087.00] |
| protocole_seul | 5 | 1.00 [1.00–1.00] | 160.00 [110.00–160.00] | 45.00 [42.00–47.00] | 13745.00 [11887.00–14198.00] | 1102.00 [976.00–1157.00] |
| deux_tiers | 5 | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] | 47.00 [46.00–51.00] | 13058.00 [12692.00–14618.00] | 1009.00 [969.00–1128.00] |
| tiers_regles | 5 | 1.00 [1.00–1.00] | 110.00 [100.00–160.00] | 25.00 [25.00–27.00] | 11294.00 [11096.00–12004.00] | 1102.00 [1091.00–1163.00] |
| petit_json_ouvert | 5 | 0.95 [0.93–0.97] | 390.00 [270.00–460.00] | 83.00 [83.00–93.00] | 38240.00 [35243.00–39329.00] | 4136.00 [3767.00–4257.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| tous_grand | 1/5 | 1.00 | 235.00 |
| protocole_seul | 1/5 | 1.00 | 260.00 |
| deux_tiers | 1/5 | 1.00 | 325.00 |
| tiers_regles | 1/5 | 1.00 | 235.00 |
| petit_json_ouvert | 5/5 | 0.95 | — |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I3_evacuated | tous_grand vs protocole_seul | 1.0000 |
| I7_delay | tous_grand vs protocole_seul | 0.6664 |
| llm_calls | tous_grand vs protocole_seul | 0.2492 |
| tokens_in | tous_grand vs protocole_seul | 0.0079 |
| tokens_out | tous_grand vs protocole_seul | 0.0079 |
| I3_evacuated | tous_grand vs deux_tiers | 1.0000 |
| I7_delay | tous_grand vs deux_tiers | 0.0227 |
| llm_calls | tous_grand vs deux_tiers | 1.0000 |
| tokens_in | tous_grand vs deux_tiers | 0.0159 |
| tokens_out | tous_grand vs deux_tiers | 0.0119 |
| I3_evacuated | tous_grand vs tiers_regles | 1.0000 |
| I7_delay | tous_grand vs tiers_regles | 1.0000 |
| llm_calls | tous_grand vs tiers_regles | 0.0119 |
| tokens_in | tous_grand vs tiers_regles | 0.0079 |
| tokens_out | tous_grand vs tiers_regles | 0.0079 |
| I3_evacuated | tous_grand vs petit_json_ouvert | 0.0095 |
| I7_delay | tous_grand vs petit_json_ouvert | 0.0212 |
| llm_calls | tous_grand vs petit_json_ouvert | 0.0119 |
| tokens_in | tous_grand vs petit_json_ouvert | 0.0079 |
| tokens_out | tous_grand vs petit_json_ouvert | 0.0079 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| tous_grand | 110.00 [100.00–160.00] | 1.00 | 32, 21, 26, 20, 20 | llm, llm, rules, llm, rules | 3/5 |
| protocole_seul | 160.00 [110.00–160.00] | 1.00 | 32, 21, 26, 20, 26 | llm, llm, llm, llm, llm | 5/5 |
| deux_tiers | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| tiers_regles | 110.00 [100.00–160.00] | 1.00 | 32, 21, 20, 20, 26 | llm, llm, rules, llm, llm | 4/5 |
| petit_json_ouvert | 390.00 [270.00–460.00] | 0.95 | 49, 56, 31, 68, 37 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| tous_grand | A 64, B 4, C 3 | A 170, B 8, C 55 |
| protocole_seul | A 59, B 2, C 1 | A 169, B 8, C 55 |
| deux_tiers | A 58, B 2, C 2 | A 170, B 8, C 55 |
| tiers_regles | A 29, B 2, C 2 | A 193, B 8, C 62 |
| petit_json_ouvert | A 42, B 4, C 4 | A 169, B 8, C 55 |

## X13 — A3

Indicateurs déclarés : I1_consensus, I2_entropy, I3_evacuated, I7_delay

### Par bras

| bras | n | I1 consensus | I2 entropie | I3 évacués | I7 délai |
|---|---|---|---|---|---|
| avec_securite | 5 | 0.98 [0.97–0.98] | 0.56 [0.54–0.59] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] |
| sans_securite | 5 | 0.98 [0.98–0.99] | 0.55 [0.48–0.71] | 1.00 [0.98–1.00] | 220.00 [220.00–230.00] |
| avec_securite_piege | 5 | 0.97 [0.96–0.97] | 0.16 [0.12–0.17] | 0.92 [0.88–0.92] | 270.00 [270.00–270.00] |
| sans_securite_piege | 5 | 0.98 [0.96–0.98] | 0.22 [0.08–0.24] | 0.90 [0.88–0.92] | 250.00 [250.00–270.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_securite | 1/5 | 1.00 | 325.00 |
| sans_securite | 2/5 | 1.00 | 320.00 |
| avec_securite_piege | 5/5 | 0.92 | — |
| sans_securite_piege | 5/5 | 0.90 | — |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | avec_securite vs sans_securite | 0.5476 |
| I2_entropy | avec_securite vs sans_securite | 0.6905 |
| I3_evacuated | avec_securite vs sans_securite | 0.6005 |
| I7_delay | avec_securite vs sans_securite | 0.9049 |
| I1_consensus | avec_securite_piege vs sans_securite_piege | 0.8413 |
| I2_entropy | avec_securite_piege vs sans_securite_piege | 1.0000 |
| I3_evacuated | avec_securite_piege vs sans_securite_piege | 0.7503 |
| I7_delay | avec_securite_piege vs sans_securite_piege | 0.4978 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec_securite | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| sans_securite | 220.00 [220.00–230.00] | 1.00 | 33, 32, 34, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| avec_securite_piege | 270.00 [270.00–270.00] | 0.92 | 33, 31, 33, 33, 33 | llm, llm, llm, llm, llm | 5/5 |
| sans_securite_piege | 250.00 [250.00–270.00] | 0.90 | 31, 39, 31, 21, 33 | llm, llm, llm, rules, llm | 4/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_securite | A 58, B 1, C 1 | A 169, B 8, C 55 |
| sans_securite | A 57, B 1, C 1 | A 184, B 6, C 51 |
| avec_securite_piege | A 44, B 3, C 22 | A 124, B 14, C 84 |
| sans_securite_piege | A 38, B 1, C 14 | A 136, B 8, C 86 |

## X14 — A3

Indicateurs déclarés : I1_consensus, I2_entropy, I3_evacuated, I7_delay

### Par bras

| bras | n | I1 consensus | I2 entropie | I3 évacués | I7 délai |
|---|---|---|---|---|---|
| avec_familles | 10 | 0.98 [0.97–0.99] | 0.55 [0.53–0.77] | 1.00 [0.99–1.00] | 220.00 [220.00–230.00] |
| sans_familles | 10 | 0.99 [0.98–0.99] | 0.46 [0.42–0.69] | 1.00 [0.99–1.00] | 225.00 [220.00–230.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_familles | 3/10 | 1.00 | 320.00 |
| sans_familles | 3/10 | 1.00 | 320.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | avec_familles vs sans_familles | 0.2123 |
| I2_entropy | avec_familles vs sans_familles | 0.0312 |
| I3_evacuated | avec_familles vs sans_familles | 1.0000 |
| I7_delay | avec_familles vs sans_familles | 0.6934 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec_familles | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32, 32, 32, 32, 33, 33 | llm, llm, llm, llm, llm, llm, llm, llm, llm, llm | 10/10 |
| sans_familles | 225.00 [220.00–230.00] | 1.00 | 32, 32, 33, 33, 32, 32, 33, 32, 33, 33 | llm, llm, llm, llm, llm, llm, llm, llm, llm, llm | 10/10 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_familles | A 120, B 5, C 2 | A 337, B 33, C 102 |
| sans_familles | A 116, B 4 | A 418, B 33, C 19 |

