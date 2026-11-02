# MARÉE — résultats X1–X7 (campagne v2)

Rapport généré par `scripts/rapport_experiences.py` à partir des
`runs/experiment_x*.json` et des journaux JSONL. Aucun chiffre n'est
écrit à la main.

- **260 runs** mesurés, 16 protocoles.
- **14181 / 14181** appels LLM aboutis.
- Population de référence : 12 agents LLM + 48 à règles (X4 varie).
- Graines par protocole : X1 5, X2 10, X3 5, X3K 5, X3M 5, X4 5, X5 10, X6 10, X7 10, X8 5, X9 5, X10 5, X11 5, X12 5, X13 5, X14 10.
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
| clair_tot | 5 | 1.00 [1.00–1.00] | 380.00 [380.00–390.00] | 0.99 [0.99–0.99] | 0.57 [0.56–0.58] |
| ambigu_tot | 5 | 0.95 [0.93–0.95] | 370.00 [260.00–440.00] | 0.99 [0.98–0.99] | 0.56 [0.55–0.58] |
| clair_tard | 5 | 1.00 [1.00–1.00] | 280.00 [280.00–290.00] | 0.99 [0.98–0.99] | 0.51 [0.50–0.52] |
| ambigu_tard | 5 | 0.95 [0.93–0.95] | 440.00 [270.00–560.00] | 0.99 [0.99–1.00] | 0.54 [0.52–0.57] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| clair_tot | 1/5 | 1.00 | 435.00 |
| ambigu_tot | 5/5 | 0.95 | — |
| clair_tard | 1/5 | 1.00 | 335.00 |
| ambigu_tard | 5/5 | 0.95 | — |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I3_evacuated | clair_tot vs ambigu_tot | 0.0095 |
| I7_delay | clair_tot vs ambigu_tot | 0.6714 |
| I1_consensus | clair_tot vs ambigu_tot | 0.4206 |
| I2_entropy | clair_tot vs ambigu_tot | 0.5476 |
| I3_evacuated | clair_tot vs clair_tard | 1.0000 |
| I7_delay | clair_tot vs clair_tard | 0.0097 |
| I1_consensus | clair_tot vs clair_tard | 0.1508 |
| I2_entropy | clair_tot vs clair_tard | 0.0952 |
| I3_evacuated | clair_tot vs ambigu_tard | 0.0088 |
| I7_delay | clair_tot vs ambigu_tard | 0.6704 |
| I1_consensus | clair_tot vs ambigu_tard | 0.8413 |
| I2_entropy | clair_tot vs ambigu_tard | 0.2222 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| clair_tot | 380.00 [380.00–390.00] | 1.00 | 44, 44, 43, 43, 43 | llm, llm, llm, llm, llm | 5/5 |
| ambigu_tot | 370.00 [260.00–440.00] | 0.95 | 54, 24, 42, 49, 31 | llm, rules, llm, llm, rules | 3/5 |
| clair_tard | 280.00 [280.00–290.00] | 1.00 | 33, 34, 34, 33, 33 | rules, rules, rules, llm, rules | 1/5 |
| ambigu_tard | 440.00 [270.00–560.00] | 0.95 | 61, 31, 49, 61, 32 | llm, llm, llm, llm, rules | 4/5 |

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
| clair_tot | A 53, B 1, C 1 | A 202, B 7, C 23 |
| ambigu_tot | A 42, B 2, C 2 | A 168, B 8, C 39 |
| clair_tard | A 54, B 1, C 2 | A 189, B 7, C 37 |
| ambigu_tard | A 42, B 1, C 2 | A 168, B 8, C 39 |

## X2 — H2

Indicateurs déclarés : I6_belief_gap, I3_evacuated, I7_delay, I5_max_density

### Par bras

| bras | n | I6 écart | I3 évacués | I7 délai | I5 densité max |
|---|---|---|---|---|---|
| avec_meneurs | 10 | 1.00 [1.00–1.00] | 0.90 [0.86–0.93] | 265.00 [250.00–270.00] | 0.48 [0.40–0.48] |
| sans_meneurs | 10 | 1.00 [1.00–1.00] | 0.89 [0.85–0.91] | 265.00 [250.00–270.00] | 0.56 [0.56–0.56] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_meneurs | 10/10 | 0.90 | — |
| sans_meneurs | 10/10 | 0.89 | — |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I6_belief_gap | avec_meneurs vs sans_meneurs | constante |
| I3_evacuated | avec_meneurs vs sans_meneurs | 0.6205 |
| I7_delay | avec_meneurs vs sans_meneurs | 0.9072 |
| I5_max_density | avec_meneurs vs sans_meneurs | 0.0581 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec_meneurs | 265.00 [250.00–270.00] | 0.90 | 26, 31, 33, 33, 33, 26, 40, 63, 32, 31 | llm, llm, llm, llm, llm, llm, llm, llm, llm, llm | 10/10 |
| sans_meneurs | 265.00 [250.00–270.00] | 0.89 | 31, 32, 31, 33, 33, 31, 33, 34, 38, 31 | llm, llm, llm, llm, llm, llm, llm, llm, llm, llm | 10/10 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_meneurs | A 77, B 12, C 37 | A 240, B 41, C 169 |
| sans_meneurs | A 72, B 5, C 25 | A 269, B 32, C 166 |

## X3 — H3

Indicateurs déclarés : I1_consensus, I5_max_density, wall_s

### Par bras

| bras | n | I1 consensus | I5 densité max | temps mural |
|---|---|---|---|---|
| synchrone | 5 | 0.98 [0.97–0.98] | 0.40 [0.40–0.48] | 18.10 [17.80–21.10] |
| asynchrone | 5 | 0.97 [0.96–0.99] | 0.40 [0.32–0.48] | 14.10 [14.00–14.90] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| synchrone | 1/5 | 1.00 | 325.00 |
| asynchrone | 1/5 | 1.00 | 325.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | synchrone vs asynchrone | 0.8413 |
| I5_max_density | synchrone vs asynchrone | 0.8248 |
| wall_s | synchrone vs asynchrone | 0.0952 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| synchrone | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| asynchrone | 220.00 [220.00–230.00] | 1.00 | 33, 33, 26, 32, 32 | llm, llm, rules, llm, llm | 4/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| synchrone | A 50, B 1, C 2 | A 169, B 8, C 55 |
| asynchrone | A 55, B 1, C 1 | A 170, B 8, C 55 |

## X3K — C1

Indicateurs déclarés : I1_consensus, I5_max_density, wall_s

### Par bras

| bras | n | I1 consensus | I5 densité max | temps mural |
|---|---|---|---|---|
| synchrone | 5 | 0.98 [0.97–0.98] | 0.48 [0.40–0.48] | 24.20 [23.40–26.70] |
| asynchrone | 5 | 0.97 [0.97–0.99] | 0.40 [0.40–0.48] | 22.10 [18.70–30.60] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| synchrone | 1/5 | 1.00 | 325.00 |
| asynchrone | 2/5 | 1.00 | 320.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | synchrone vs asynchrone | 1.0000 |
| I5_max_density | synchrone vs asynchrone | 0.7337 |
| wall_s | synchrone vs asynchrone | 0.6905 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| synchrone | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| asynchrone | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| synchrone | A 53, C 2 | A 169, B 8, C 55 |
| asynchrone | A 53, B 2, C 2 | A 170, B 8, C 55 |

## X3M — H3

Indicateurs déclarés : I1_consensus, I5_max_density, wall_s

### Par bras

| bras | n | I1 consensus | I5 densité max | temps mural |
|---|---|---|---|---|
| synchrone | 5 | 0.98 [0.97–0.98] | 0.48 [0.40–0.48] | 18.20 [17.90–20.90] |
| asynchrone | 5 | 0.97 [0.97–0.97] | 0.40 [0.40–0.48] | 15.70 [14.40–16.90] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| synchrone | 1/5 | 1.00 | 325.00 |
| asynchrone | 1/5 | 1.00 | 325.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | synchrone vs asynchrone | 0.5284 |
| I5_max_density | synchrone vs asynchrone | 0.6312 |
| wall_s | synchrone vs asynchrone | 0.1508 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| synchrone | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| asynchrone | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| synchrone | A 51, B 1, C 2 | A 169, B 8, C 55 |
| asynchrone | A 52, B 2, C 1 | A 170, B 8, C 55 |

## X4 — H4

Indicateurs déclarés : I6_belief_gap, I3_evacuated, I7_delay, llm_calls, wall_s

### Par bras

| bras | n | I6 écart | I3 évacués | I7 délai | appels LLM | temps mural |
|---|---|---|---|---|---|---|
| hybride_12 | 5 | 1.00 [1.00–1.00] | 0.88 [0.85–0.92] | 270.00 [270.00–270.00] | 78.00 [53.00–84.00] | 24.70 [23.00–25.20] |
| regles_60 | 5 | 1.00 [1.00–1.00] | 0.92 [0.90–0.95] | 150.00 [150.00–150.00] | 0.00 [0.00–0.00] | 11.10 [10.90–11.20] |
| llm_60 | 5 | 1.00 [1.00–1.00] | 0.70 [0.65–0.72] | 440.00 [430.00–460.00] | 477.00 [416.00–496.00] | 89.50 [78.30–99.20] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| hybride_12 | 5/5 | 0.88 | — |
| regles_60 | 4/5 | 0.92 | 210.00 |
| llm_60 | 5/5 | 0.70 | — |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I6_belief_gap | hybride_12 vs regles_60 | constante |
| I3_evacuated | hybride_12 vs regles_60 | 0.3457 |
| I7_delay | hybride_12 vs regles_60 | 0.0102 |
| llm_calls | hybride_12 vs regles_60 | 0.0075 |
| wall_s | hybride_12 vs regles_60 | 0.0079 |
| I6_belief_gap | hybride_12 vs llm_60 | constante |
| I3_evacuated | hybride_12 vs llm_60 | 0.0159 |
| I7_delay | hybride_12 vs llm_60 | 0.0147 |
| llm_calls | hybride_12 vs llm_60 | 0.0079 |
| wall_s | hybride_12 vs llm_60 | 0.0079 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| hybride_12 | 270.00 [270.00–270.00] | 0.88 | 33, 31, 39, 33, 33 | llm, llm, llm, llm, llm | 5/5 |
| regles_60 | 150.00 [150.00–150.00] | 0.92 | 21, 20, 21, 27, 21 | rules, rules, rules, rules, rules | 0/5 |
| llm_60 | 440.00 [430.00–460.00] | 0.70 | 70, 50, 49, 39, 52 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| hybride_12 | A 35, B 4, C 21 | A 120, B 14, C 87 |
| regles_60 | — | A 156, B 14, C 103 |
| llm_60 | A 277, B 11, C 60 | — |

## X5 — H5

Indicateurs déclarés : I1_consensus, I2_entropy, I3_evacuated, I7_delay

### Par bras

| bras | n | I1 consensus | I2 entropie | I3 évacués | I7 délai |
|---|---|---|---|---|---|
| avec_memoire | 10 | 0.98 [0.97–0.98] | 0.52 [0.52–0.55] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] |
| sans_memoire | 10 | 0.98 [0.97–0.98] | 0.50 [0.49–0.50] | 1.00 [1.00–1.00] | 220.00 [220.00–227.50] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_memoire | 2/10 | 1.00 | 320.00 |
| sans_memoire | 0/10 | 1.00 | 320.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | avec_memoire vs sans_memoire | 0.3075 |
| I2_entropy | avec_memoire vs sans_memoire | 0.0073 |
| I3_evacuated | avec_memoire vs sans_memoire | 0.1675 |
| I7_delay | avec_memoire vs sans_memoire | 0.5107 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec_memoire | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32, 32, 32, 32, 33, 33 | llm, llm, llm, llm, llm, llm, llm, llm, llm, llm | 10/10 |
| sans_memoire | 220.00 [220.00–227.50] | 1.00 | 33, 33, 32, 32, 32, 32, 32, 32, 21, 33 | llm, llm, llm, llm, llm, llm, llm, llm, llm, llm | 10/10 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_memoire | A 108, B 5, C 3 | A 336, B 33, C 102 |
| sans_memoire | A 95, B 7, C 6 | A 336, B 33, C 102 |

## X6 — H6

Indicateurs déclarés : I1_consensus, I3_evacuated, I7_delay

### Par bras

| bras | n | I1 consensus | I3 évacués | I7 délai |
|---|---|---|---|---|
| visiteurs_seuls | 10 | 1.00 [1.00–1.00] | 1.00 [1.00–1.00] | 90.00 [90.00–100.00] |
| habitues_seuls | 10 | 0.94 [0.91–0.96] | 1.00 [1.00–1.00] | 100.00 [100.00–150.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| visiteurs_seuls | 0/10 | 1.00 | 190.00 |
| habitues_seuls | 1/10 | 1.00 | 200.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | visiteurs_seuls vs habitues_seuls | 0.0001 |
| I3_evacuated | visiteurs_seuls vs habitues_seuls | 0.3681 |
| I7_delay | visiteurs_seuls vs habitues_seuls | 0.0021 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| visiteurs_seuls | 90.00 [90.00–100.00] | 1.00 | 19, 20, 19, 19, 20, 20, 19, 19, 20, 19 | llm, rules, llm, llm, llm, rules, llm, llm, rules, llm | 7/10 |
| habitues_seuls | 100.00 [100.00–150.00] | 1.00 | 32, 20, 26, 25, 25, 20, 20, 20, 20, 20 | llm, llm, llm, llm, llm, llm, llm, llm, llm, rules | 9/10 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| visiteurs_seuls | A 40 | A 160 |
| habitues_seuls | A 27, B 14, C 2 | A 90, B 67, C 21 |

## X7 — H7

Indicateurs déclarés : I2_entropy, I1_consensus, I3_evacuated, I7_delay

### Par bras

| bras | n | I2 entropie | I1 consensus | I3 évacués | I7 délai |
|---|---|---|---|---|---|
| avec_rag | 10 | 0.53 [0.52–0.55] | 0.98 [0.97–0.98] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] |
| sans_rag | 10 | 0.54 [0.52–0.59] | 0.98 [0.97–0.98] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_rag | 1/10 | 1.00 | 320.00 |
| sans_rag | 1/10 | 1.00 | 320.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I2_entropy | avec_rag vs sans_rag | 0.4727 |
| I1_consensus | avec_rag vs sans_rag | 0.3447 |
| I3_evacuated | avec_rag vs sans_rag | 1.0000 |
| I7_delay | avec_rag vs sans_rag | 0.8296 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec_rag | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 21, 32, 32, 32, 32, 33, 33 | llm, llm, llm, llm, llm, llm, llm, llm, llm, llm | 10/10 |
| sans_rag | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32, 32, 32, 32, 33, 33 | llm, llm, llm, llm, llm, llm, llm, llm, llm, llm | 10/10 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_rag | A 105, B 5, C 2 | A 337, B 33, C 102 |
| sans_rag | A 105, B 7, C 2 | A 336, B 33, C 102 |

## X8 — B3

Indicateurs déclarés : I1_consensus, I2_entropy, I3_evacuated, I7_delay, messages

### Par bras

| bras | n | I1 consensus | I2 entropie | I3 évacués | I7 délai | messages |
|---|---|---|---|---|---|---|
| avec | 5 | 0.97 [0.97–0.99] | 0.53 [0.51–0.55] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] | 58.00 [57.00–59.00] |
| sans | 5 | 0.99 [0.99–0.99] | 0.83 [0.83–0.83] | 0.97 [0.97–0.97] | 220.00 [220.00–230.00] | 0.00 [0.00–0.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec | 1/5 | 1.00 | 325.00 |
| sans | 5/5 | 0.97 | — |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | avec vs sans | 0.0952 |
| I2_entropy | avec vs sans | 0.1508 |
| I3_evacuated | avec vs sans | 0.0056 |
| I7_delay | avec vs sans | 0.8174 |
| messages | avec vs sans | 0.0075 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 21, 32 | llm, llm, llm, llm, llm | 5/5 |
| sans | 220.00 [220.00–230.00] | 0.97 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec | A 52, B 1, C 2 | A 170, B 8, C 55 |
| sans | A 43, C 1 | A 169, B 8, C 56 |

## X9 — A1

Indicateurs déclarés : I1_consensus, I3_evacuated, I7_delay, llm_calls

### Par bras

| bras | n | I1 consensus | I3 évacués | I7 délai | appels LLM |
|---|---|---|---|---|---|
| sans_passe | 5 | 0.97 [0.96–0.97] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] | 45.00 [41.00–49.00] |
| avec_passe | 5 | 0.98 [0.97–0.98] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] | 46.00 [44.00–46.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| sans_passe | 1/5 | 1.00 | 325.00 |
| avec_passe | 0/5 | 1.00 | 320.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | sans_passe vs avec_passe | 0.5476 |
| I3_evacuated | sans_passe vs avec_passe | 0.4237 |
| I7_delay | sans_passe vs avec_passe | 1.0000 |
| llm_calls | sans_passe vs avec_passe | 0.8335 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| sans_passe | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| avec_passe | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| sans_passe | A 49, B 3, C 3 | A 170, B 8, C 55 |
| avec_passe | A 53, B 1, C 3 | A 169, B 8, C 55 |

## X10 — C8 + C7

Indicateurs déclarés : I1_consensus, I3_evacuated, I7_delay, lag_indicator, lag_llm

### Par bras

| bras | n | I1 consensus | I3 évacués | I7 délai | lag_indicator | lag_llm |
|---|---|---|---|---|---|---|
| petite | 5 | 0.97 [0.94–0.98] | 1.00 [0.95–1.00] | 100.00 [100.00–150.00] | 1.50 [1.00–1.50] | 0.00 [0.00–0.00] |
| petite_async | 5 | 0.98 [0.97–0.98] | 0.95 [0.95–1.00] | 130.00 [130.00–170.00] | 2.00 [2.00–2.00] | 2.00 [2.00–3.00] |
| grande | 5 | 0.97 [0.96–0.97] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] | 1.50 [1.50–1.50] | 0.00 [0.00–0.00] |
| grande_async | 5 | 0.98 [0.98–0.99] | 1.00 [0.98–1.00] | 230.00 [230.00–230.00] | 1.00 [1.00–1.50] | 2.00 [2.00–2.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| petite | 2/5 | 1.00 | 200.00 |
| petite_async | 3/5 | 0.95 | 250.00 |
| grande | 1/5 | 1.00 | 325.00 |
| grande_async | 2/5 | 1.00 | 330.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | petite vs petite_async | 0.3095 |
| I3_evacuated | petite vs petite_async | 0.7337 |
| I7_delay | petite vs petite_async | 0.2031 |
| lag_indicator | petite vs petite_async | 0.0214 |
| lag_llm | petite vs petite_async | 0.0065 |
| I1_consensus | petite vs grande | 0.6905 |
| I3_evacuated | petite vs grande | 0.4407 |
| I7_delay | petite vs grande | 0.0099 |
| lag_indicator | petite vs grande | 0.6005 |
| lag_llm | petite vs grande | constante |
| I1_consensus | petite vs grande_async | 0.2222 |
| I3_evacuated | petite vs grande_async | 0.7231 |
| I7_delay | petite vs grande_async | 0.0102 |
| lag_indicator | petite vs grande_async | 0.6312 |
| lag_llm | petite vs grande_async | 0.0056 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| petite | 100.00 [100.00–150.00] | 1.00 | 20, 20, 26, 20, 25 | rules, rules, llm, rules, llm | 2/5 |
| petite_async | 130.00 [130.00–170.00] | 0.95 | 23, 23, 28, 21, 27 | llm, llm, llm, rules, llm | 4/5 |
| grande | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| grande_async | 230.00 [230.00–230.00] | 1.00 | 28, 34, 33, 33, 33 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| petite | A 27, C 1 | A 42, C 23 |
| petite_async | A 25, C 1 | A 42, C 23 |
| grande | A 53, B 2, C 1 | A 170, B 8, C 55 |
| grande_async | A 54, B 1 | A 169, B 8, C 55 |

## X11 — C4

Indicateurs déclarés : I1_consensus, I3_evacuated, I7_delay, lag_ticks_median, lag_ticks_max

### Par bras

| bras | n | I1 consensus | I3 évacués | I7 délai | lag_ticks_median | lag_ticks_max |
|---|---|---|---|---|---|---|
| sync | 5 | 0.97 [0.96–0.97] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] | 0.00 [0.00–0.00] | 0.00 [0.00–0.00] |
| async | 5 | 0.98 [0.98–0.99] | 1.00 [0.98–1.00] | 230.00 [230.00–240.00] | 4.00 [4.00–4.00] | 6.00 [5.00–6.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| sync | 1/5 | 1.00 | 325.00 |
| async | 2/5 | 1.00 | 330.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | sync vs async | 0.3095 |
| I3_evacuated | sync vs async | 0.6005 |
| I7_delay | sync vs async | 0.0413 |
| lag_ticks_median | sync vs async | 0.0040 |
| lag_ticks_max | sync vs async | 0.0071 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| sync | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| async | 230.00 [230.00–240.00] | 1.00 | 34, 34, 33, 33, 33 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| sync | A 51, B 2, C 1 | A 170, B 8, C 55 |
| async | A 54, C 1 | A 169, B 8, C 55 |

## X12 — E5

Indicateurs déclarés : I3_evacuated, I7_delay, llm_calls, tokens_in, tokens_out

### Par bras

| bras | n | I3 évacués | I7 délai | appels LLM | tokens_in | tokens_out |
|---|---|---|---|---|---|---|
| tous_grand | 5 | 1.00 [1.00–1.00] | 100.00 [100.00–160.00] | 43.00 [41.00–45.00] | 18180.00 [16674.00–19211.00] | 1855.00 [1749.00–1893.00] |
| protocole_seul | 5 | 1.00 [1.00–1.00] | 110.00 [100.00–160.00] | 40.00 [36.00–45.00] | 12222.00 [9772.00–14027.00] | 985.00 [738.00–1087.00] |
| deux_tiers | 5 | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] | 43.00 [43.00–45.00] | 12209.00 [11944.00–12613.00] | 860.00 [818.00–885.00] |
| tiers_regles | 5 | 1.00 [1.00–1.00] | 100.00 [100.00–160.00] | 21.00 [20.00–25.00] | 9800.00 [9477.00–12188.00] | 924.00 [897.00–1069.00] |
| petit_json_ouvert | 5 | 0.93 [0.93–0.95] | 460.00 [330.00–510.00] | 88.00 [82.00–88.00] | 43870.00 [41716.00–44115.00] | 4136.00 [4089.00–4472.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| tous_grand | 1/5 | 1.00 | 230.00 |
| protocole_seul | 1/5 | 1.00 | 235.00 |
| deux_tiers | 1/5 | 1.00 | 325.00 |
| tiers_regles | 1/5 | 1.00 | 230.00 |
| petit_json_ouvert | 5/5 | 0.93 | — |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I3_evacuated | tous_grand vs protocole_seul | 1.0000 |
| I7_delay | tous_grand vs protocole_seul | 0.8225 |
| llm_calls | tous_grand vs protocole_seul | 0.4606 |
| tokens_in | tous_grand vs protocole_seul | 0.0079 |
| tokens_out | tous_grand vs protocole_seul | 0.0079 |
| I3_evacuated | tous_grand vs deux_tiers | 1.0000 |
| I7_delay | tous_grand vs deux_tiers | 0.0214 |
| llm_calls | tous_grand vs deux_tiers | 0.5165 |
| tokens_in | tous_grand vs deux_tiers | 0.0317 |
| tokens_out | tous_grand vs deux_tiers | 0.0079 |
| I3_evacuated | tous_grand vs tiers_regles | 1.0000 |
| I7_delay | tous_grand vs tiers_regles | 1.0000 |
| llm_calls | tous_grand vs tiers_regles | 0.0079 |
| tokens_in | tous_grand vs tiers_regles | 0.0079 |
| tokens_out | tous_grand vs tiers_regles | 0.0079 |
| I3_evacuated | tous_grand vs petit_json_ouvert | 0.0092 |
| I7_delay | tous_grand vs petit_json_ouvert | 0.0109 |
| llm_calls | tous_grand vs petit_json_ouvert | 0.0119 |
| tokens_in | tous_grand vs petit_json_ouvert | 0.0079 |
| tokens_out | tous_grand vs petit_json_ouvert | 0.0079 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| tous_grand | 100.00 [100.00–160.00] | 1.00 | 32, 20, 20, 20, 26 | llm, rules, rules, llm, llm | 3/5 |
| protocole_seul | 110.00 [100.00–160.00] | 1.00 | 32, 21, 20, 20, 26 | llm, llm, rules, llm, llm | 4/5 |
| deux_tiers | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| tiers_regles | 100.00 [100.00–160.00] | 1.00 | 32, 20, 20, 20, 26 | llm, rules, rules, rules, llm | 2/5 |
| petit_json_ouvert | 460.00 [330.00–510.00] | 0.93 | 61, 37, 43, 61, 56 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| tous_grand | A 50, B 2, C 5 | A 170, B 8, C 55 |
| protocole_seul | A 49, B 2, C 1 | A 169, B 8, C 55 |
| deux_tiers | A 51, B 2, C 1 | A 169, B 8, C 55 |
| tiers_regles | A 18, B 2, C 5 | A 193, B 8, C 62 |
| petit_json_ouvert | A 32, B 2, C 4 | A 169, B 8, C 55 |

## X13 — A3

Indicateurs déclarés : I1_consensus, I2_entropy, I3_evacuated, I7_delay

### Par bras

| bras | n | I1 consensus | I2 entropie | I3 évacués | I7 délai |
|---|---|---|---|---|---|
| avec_securite | 5 | 0.97 [0.97–0.98] | 0.53 [0.53–0.59] | 1.00 [1.00–1.00] | 220.00 [220.00–230.00] |
| sans_securite | 5 | 0.98 [0.97–0.99] | 0.49 [0.46–0.76] | 1.00 [0.98–1.00] | 220.00 [220.00–230.00] |
| avec_securite_piege | 5 | 0.97 [0.97–0.98] | 0.13 [0.11–0.18] | 0.90 [0.83–0.92] | 270.00 [270.00–330.00] |
| sans_securite_piege | 5 | 0.97 [0.97–0.98] | 0.19 [0.08–0.24] | 0.90 [0.88–0.92] | 250.00 [250.00–260.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_securite | 1/5 | 1.00 | 325.00 |
| sans_securite | 2/5 | 1.00 | 320.00 |
| avec_securite_piege | 5/5 | 0.90 | — |
| sans_securite_piege | 5/5 | 0.90 | — |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | avec_securite vs sans_securite | 1.0000 |
| I2_entropy | avec_securite vs sans_securite | 0.5476 |
| I3_evacuated | avec_securite vs sans_securite | 0.6005 |
| I7_delay | avec_securite vs sans_securite | 1.0000 |
| I1_consensus | avec_securite_piege vs sans_securite_piege | 1.0000 |
| I2_entropy | avec_securite_piege vs sans_securite_piege | 1.0000 |
| I3_evacuated | avec_securite_piege vs sans_securite_piege | 1.0000 |
| I7_delay | avec_securite_piege vs sans_securite_piege | 0.1376 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec_securite | 220.00 [220.00–230.00] | 1.00 | 33, 33, 32, 32, 32 | llm, llm, llm, llm, llm | 5/5 |
| sans_securite | 220.00 [220.00–230.00] | 1.00 | 33, 32, 34, 20, 32 | llm, llm, llm, rules, llm | 4/5 |
| avec_securite_piege | 270.00 [270.00–330.00] | 0.90 | 26, 80, 39, 33, 33 | llm, llm, llm, llm, llm | 5/5 |
| sans_securite_piege | 250.00 [250.00–260.00] | 0.90 | 31, 32, 31, 21, 33 | llm, llm, llm, rules, llm | 4/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_securite | A 50, B 2, C 1 | A 169, B 8, C 55 |
| sans_securite | A 60, B 1 | A 184, B 6, C 51 |
| avec_securite_piege | A 33, B 4, C 17 | A 121, B 14, C 83 |
| sans_securite_piege | A 38, B 2, C 12 | A 136, B 8, C 86 |

## X14 — A3

Indicateurs déclarés : I1_consensus, I2_entropy, I3_evacuated, I7_delay

### Par bras

| bras | n | I1 consensus | I2 entropie | I3 évacués | I7 délai |
|---|---|---|---|---|---|
| avec_familles | 10 | 0.98 [0.97–0.98] | 0.52 [0.51–0.54] | 1.00 [1.00–1.00] | 220.00 [220.00–227.50] |
| sans_familles | 10 | 0.98 [0.98–0.99] | 0.41 [0.40–0.44] | 1.00 [1.00–1.00] | 225.00 [220.00–230.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_familles | 1/10 | 1.00 | 320.00 |
| sans_familles | 2/10 | 1.00 | 320.00 |

### Tests (Mann-Whitney)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | avec_familles vs sans_familles | 0.0257 |
| I2_entropy | avec_familles vs sans_familles | 0.0173 |
| I3_evacuated | avec_familles vs sans_familles | 0.5828 |
| I7_delay | avec_familles vs sans_familles | 0.5438 |

### Délai premier signal → dernier sorti (I7)

| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|---|---|
| avec_familles | 220.00 [220.00–227.50] | 1.00 | 33, 33, 32, 21, 32, 32, 32, 32, 26, 33 | llm, llm, llm, llm, llm, llm, llm, llm, llm, llm | 10/10 |
| sans_familles | 225.00 [220.00–230.00] | 1.00 | 32, 26, 33, 33, 32, 32, 33, 21, 33, 33 | llm, llm, llm, llm, llm, llm, llm, llm, llm, llm | 10/10 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_familles | A 106, B 5, C 4 | A 337, B 33, C 102 |
| sans_familles | A 101, B 4 | A 418, B 33, C 19 |

