# MARÉE — résultats X1–X7 (campagne v2)

Rapport généré par `scripts/rapport_experiences.py` à partir des
`runs/experiment_x*.json` et des journaux JSONL. Aucun chiffre n'est
écrit à la main.

- **85 runs** mesurés, 7 protocoles.
- **4216 / 4216** appels LLM aboutis.
- Population de référence : 12 agents LLM + 48 à règles (X4 varie).
- Chaque bras : 5 graines (0–4). Médiane [Q1–Q3], test de
  Mann-Whitney bilatéral entre le premier bras et chacun des autres.
- **Censure** : un run qui atteint `max_ticks` avant que tout le
  monde soit sorti produit un I4 égal au plafond (720 s en scénario
  `demo`, 900 s en `e2e`). Ce n'est pas une durée d'évacuation :
  c'est un run interrompu. Dans ce cas, lire I3 (part sortie).
  La table « runs non terminés » donne le compte par bras.

## Ce que mesure chaque indicateur

| indicateur | définition |
|---|---|
| I1 consensus | part des agents qui partagent la croyance majoritaire |
| I2 entropie | incertitude moyenne des croyances (0 = tous sûrs) |
| I3 évacués | part des agents sortis |
| I4 durée | durée d'évacuation observée (s) |
| I5 densité max | densité locale max, noyau de 2 m (pers/m²) |
| I6 écart | part des agents croyant en une sortie fermée |
| appels LLM | tentatives d'appel |
| temps mural | durée réelle du run (s) |

## X1 — H1

Indicateurs déclarés : I4_seconds, I1_consensus, I2_entropy

### Par bras

| bras | n | I4 durée | I1 consensus | I2 entropie |
|---|---|---|---|---|
| clair_tot | 5 | 200.00 [200.00–210.00] | 0.95 [0.92–0.96] | 0.50 [0.45–0.55] |
| ambigu_tot | 5 | 720.00 [380.00–720.00] | 0.97 [0.97–0.98] | 0.58 [0.55–0.58] |
| clair_tard | 5 | 320.00 [320.00–330.00] | 0.95 [0.95–0.98] | 0.50 [0.47–0.56] |
| ambigu_tard | 5 | 430.00 [390.00–720.00] | 0.97 [0.97–0.98] | 0.52 [0.51–0.58] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| clair_tot | 0/5 | 1.00 | 200.00 |
| ambigu_tot | 3/5 | 0.98 | 375.00 |
| clair_tard | 0/5 | 1.00 | 320.00 |
| ambigu_tard | 2/5 | 1.00 | 390.00 |

### Tests (Mann-Whitney, premier bras contre les autres)

| indicateur | comparaison | p |
|---|---|---|
| I4_seconds | clair_tot vs ambigu_tot | 0.0099 |
| I1_consensus | clair_tot vs ambigu_tot | 0.0556 |
| I2_entropy | clair_tot vs ambigu_tot | 0.0952 |
| I4_seconds | clair_tot vs clair_tard | 0.0107 |
| I1_consensus | clair_tot vs clair_tard | 0.4206 |
| I2_entropy | clair_tot vs clair_tard | 0.8413 |
| I4_seconds | clair_tot vs ambigu_tard | 0.0107 |
| I1_consensus | clair_tot vs ambigu_tard | 0.0952 |
| I2_entropy | clair_tot vs ambigu_tard | 0.3095 |

### Qui sort en dernier (I4)

| bras | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|
| clair_tot | 20, 21, 21, 20, 20 | rules, rules, rules, llm, rules | 1/5 |
| ambigu_tot | 37, 30, 19, 38, 31 | rules, rules, rules, rules, rules | 0/5 |
| clair_tard | 32, 31, 34, 32, 33 | rules, rules, rules, rules, rules | 0/5 |
| ambigu_tard | 38, 43, 21, 39, 32 | rules, rules, rules, rules, rules | 0/5 |

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
| clair_tot | A 39, B 31, C 9 | A 194, B 8, C 30 |
| ambigu_tot | A 36, B 27, C 15 | A 169, B 8, C 39 |
| clair_tard | A 40, B 26, C 12 | A 172, B 8, C 52 |
| ambigu_tard | A 38, B 28, C 9 | A 169, B 8, C 54 |

## X2 — H2

Indicateurs déclarés : I6_belief_gap, I3_evacuated, I5_max_density

### Par bras

| bras | n | I6 écart | I3 évacués | I5 densité max |
|---|---|---|---|---|
| avec_meneurs | 5 | 1.00 [1.00–1.00] | 0.92 [0.83–0.92] | 0.40 [0.32–0.56] |
| sans_meneurs | 5 | 1.00 [1.00–1.00] | 0.93 [0.93–0.98] | 0.48 [0.40–0.56] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_meneurs | 4/5 | 0.92 | 210.00 |
| sans_meneurs | 4/5 | 0.93 | 240.00 |

### Tests (Mann-Whitney, premier bras contre les autres)

| indicateur | comparaison | p |
|---|---|---|
| I6_belief_gap | avec_meneurs vs sans_meneurs | 0.4237 |
| I3_evacuated | avec_meneurs vs sans_meneurs | 0.1105 |
| I5_max_density | avec_meneurs vs sans_meneurs | 0.7424 |

### Qui sort en dernier (I4)

| bras | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|
| avec_meneurs | 34, 27, 21, 28, 21 | llm, llm, llm, llm, rules | 4/5 |
| sans_meneurs | 23, 28, 24, 21, 28 | llm, llm, llm, rules, llm | 4/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_meneurs | A 46, B 34, C 22 | A 107, B 14, C 87 |
| sans_meneurs | A 44, B 35, C 15 | A 167, B 12, C 85 |

## X3 — H3

Indicateurs déclarés : I1_consensus, I5_max_density, wall_s

### Par bras

| bras | n | I1 consensus | I5 densité max | temps mural |
|---|---|---|---|---|
| synchrone | 5 | 0.94 [0.92–0.96] | 0.48 [0.40–0.48] | 35.50 [35.30–36.00] |
| asynchrone | 5 | 0.94 [0.92–0.97] | 0.48 [0.40–0.48] | 23.10 [22.30–23.30] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| synchrone | 0/5 | 1.00 | 200.00 |
| asynchrone | 0/5 | 1.00 | 200.00 |

### Tests (Mann-Whitney, premier bras contre les autres)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | synchrone vs asynchrone | 0.6905 |
| I5_max_density | synchrone vs asynchrone | 0.8225 |
| wall_s | synchrone vs asynchrone | 0.0079 |

### Qui sort en dernier (I4)

| bras | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|
| synchrone | 21, 20, 20, 20, 20 | llm, rules, rules, rules, llm | 2/5 |
| asynchrone | 21, 20, 20, 22, 20 | llm, rules, rules, llm, rules | 2/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| synchrone | A 38, B 44, C 9 | A 169, B 8, C 55 |
| asynchrone | A 43, B 35, C 9 | A 169, B 8, C 55 |

## X4 — H4

Indicateurs déclarés : I6_belief_gap, I4_seconds, llm_calls, wall_s

### Par bras

| bras | n | I6 écart | I4 durée | appels LLM | temps mural |
|---|---|---|---|---|---|
| hybride_12 | 5 | 1.00 [1.00–1.00] | 900.00 [900.00–900.00] | 50.00 [44.00–53.00] | 32.70 [32.30–33.70] |
| regles_60 | 5 | 1.00 [1.00–1.00] | 900.00 [900.00–900.00] | 0.00 [0.00–0.00] | 9.70 [9.40–9.90] |
| llm_60 | 5 | 0.79 [0.50–0.79] | 290.00 [280.00–390.00] | 240.00 [232.00–281.00] | 111.20 [110.30–131.90] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| hybride_12 | 4/5 | 0.92 | 280.00 |
| regles_60 | 4/5 | 0.92 | 210.00 |
| llm_60 | 0/5 | 1.00 | 290.00 |

### Tests (Mann-Whitney, premier bras contre les autres)

| indicateur | comparaison | p |
|---|---|---|
| I6_belief_gap | hybride_12 vs regles_60 | constante |
| I4_seconds | hybride_12 vs regles_60 | 1.0000 |
| llm_calls | hybride_12 vs regles_60 | 0.0075 |
| wall_s | hybride_12 vs regles_60 | 0.0079 |
| I6_belief_gap | hybride_12 vs llm_60 | 0.0254 |
| I4_seconds | hybride_12 vs llm_60 | 0.0661 |
| llm_calls | hybride_12 vs llm_60 | 0.0079 |
| wall_s | hybride_12 vs llm_60 | 0.0079 |

### Qui sort en dernier (I4)

| bras | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|
| hybride_12 | 27, 28, 28, 28, 21 | llm, llm, llm, llm, llm | 5/5 |
| regles_60 | 21, 20, 21, 27, 21 | rules, rules, rules, rules, rules | 0/5 |
| llm_60 | 39, 46, 28, 29, 27 | llm, llm, llm, llm, llm | 5/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| hybride_12 | A 53, B 51, C 17 | A 125, B 14, C 83 |
| regles_60 | — | A 156, B 14, C 103 |
| llm_60 | A 218, B 316, C 98 | — |

## X5 — H5

Indicateurs déclarés : I1_consensus, I2_entropy, I4_seconds

### Par bras

| bras | n | I1 consensus | I2 entropie | I4 durée |
|---|---|---|---|---|
| avec_memoire | 5 | 0.94 [0.94–0.96] | 0.47 [0.47–0.48] | 200.00 [200.00–210.00] |
| sans_memoire | 5 | 0.95 [0.95–0.97] | 0.44 [0.41–0.46] | 200.00 [200.00–200.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_memoire | 0/5 | 1.00 | 200.00 |
| sans_memoire | 0/5 | 1.00 | 200.00 |

### Tests (Mann-Whitney, premier bras contre les autres)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | avec_memoire vs sans_memoire | 0.3095 |
| I2_entropy | avec_memoire vs sans_memoire | 0.0556 |
| I4_seconds | avec_memoire vs sans_memoire | 0.1797 |

### Qui sort en dernier (I4)

| bras | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|
| avec_memoire | 21, 20, 20, 22, 20 | llm, rules, rules, llm, llm | 3/5 |
| sans_memoire | 20, 20, 20, 20, 20 | rules, rules, rules, rules, rules | 0/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_memoire | A 43, B 42, C 6 | A 169, B 8, C 55 |
| sans_memoire | A 51, B 16, C 6 | A 169, B 8, C 55 |

## X6 — H6

Indicateurs déclarés : I1_consensus, I4_seconds

### Par bras

| bras | n | I1 consensus | I4 durée |
|---|---|---|---|
| visiteurs_seuls | 5 | 0.99 [0.98–0.99] | 200.00 [200.00–210.00] |
| habitues_seuls | 5 | 0.96 [0.94–0.96] | 200.00 [200.00–200.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| visiteurs_seuls | 0/5 | 1.00 | 200.00 |
| habitues_seuls | 0/5 | 1.00 | 200.00 |

### Tests (Mann-Whitney, premier bras contre les autres)

| indicateur | comparaison | p |
|---|---|---|
| I1_consensus | visiteurs_seuls vs habitues_seuls | 0.0317 |
| I4_seconds | visiteurs_seuls vs habitues_seuls | 0.4065 |

### Qui sort en dernier (I4)

| bras | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|
| visiteurs_seuls | 21, 20, 19, 21, 20 | llm, rules, rules, llm, rules | 2/5 |
| habitues_seuls | 20, 20, 20, 19, 20 | rules, rules, rules, rules, rules | 0/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| visiteurs_seuls | A 15, B 12 | A 80 |
| habitues_seuls | A 17, B 3, C 1 | A 51, B 22, C 12 |

## X7 — H7

Indicateurs déclarés : I2_entropy, I1_consensus, I4_seconds

### Par bras

| bras | n | I2 entropie | I1 consensus | I4 durée |
|---|---|---|---|---|
| avec_rag | 5 | 0.47 [0.43–0.47] | 0.93 [0.93–0.94] | 200.00 [200.00–210.00] |
| sans_rag | 5 | 0.53 [0.46–0.65] | 0.96 [0.95–0.97] | 320.00 [210.00–370.00] |

### Runs non terminés (censure)

| bras | runs non terminés | I3 médian | I4 des runs terminés |
|---|---|---|---|
| avec_rag | 0/5 | 1.00 | 200.00 |
| sans_rag | 1/5 | 1.00 | 265.00 |

### Tests (Mann-Whitney, premier bras contre les autres)

| indicateur | comparaison | p |
|---|---|---|
| I2_entropy | avec_rag vs sans_rag | 0.2222 |
| I1_consensus | avec_rag vs sans_rag | 0.0079 |
| I4_seconds | avec_rag vs sans_rag | 0.1015 |

### Qui sort en dernier (I4)

| bras | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |
|---|---|---|---|
| avec_rag | 21, 20, 20, 21, 20 | llm, rules, rules, llm, rules | 2/5 |
| sans_rag | 32, 37, 21, 21, 20 | llm, llm, llm, llm, rules | 4/5 |

### Sorties choisies (décisions `go_exit`)

| bras | agents LLM | agents à règles |
|---|---|---|
| avec_rag | A 44, B 33, C 11 | A 169, B 8, C 55 |
| sans_rag | A 56, B 3, C 6 | A 169, B 8, C 55 |

