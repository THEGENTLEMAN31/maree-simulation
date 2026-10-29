# MARÉE — résultats X1–X7 (campagne v2)

Rapport généré par `scripts/rapport_experiences.py` à partir des
`runs/experiment_x*.json` et des journaux JSONL. Aucun chiffre n'est
écrit à la main.

- **115 runs** mesurés, 7 protocoles.
- **6906 / 6906** appels LLM aboutis.
- Population de référence : 12 agents LLM + 48 à règles (X4 varie).
- Graines par protocole : X1 5, X2 5, X3 5, X4 5, X5 10, X6 10, X7 10.
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

### Tests (Mann-Whitney, premier bras contre les autres)

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

### Tests (Mann-Whitney, premier bras contre les autres)

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

### Tests (Mann-Whitney, premier bras contre les autres)

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

### Tests (Mann-Whitney, premier bras contre les autres)

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

### Tests (Mann-Whitney, premier bras contre les autres)

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

### Tests (Mann-Whitney, premier bras contre les autres)

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

### Tests (Mann-Whitney, premier bras contre les autres)

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

