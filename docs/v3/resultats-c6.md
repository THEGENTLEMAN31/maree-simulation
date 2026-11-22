# Résultats de la campagne macro (C6/C7)

Monde : `crowd_hall` (22 × 16 m, deux issues de 1,2 m), 60 agents, tick de 2 s. Graines : 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 — scénarios : contradiction, split — **parole active (C7)**.

Chaque ligne est la **médiane** des runs du bras ; `[min–max]` donne l'intervalle observé, jamais un écart-type qui masquerait un run.

| bras | scénario | décisions | appels (ok) | jetons | mural (s) | I1 | I3 | I5 [min–max] | I7 s [min–max] | crue bloquée (désignée t1) | crue bloquée **au moment de décider** (dont faute de mieux) | paroles | cibles résolues par le moteur |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `decision_head` | contradiction | 583 | 583 (583) | 111190 | 247.1 | 0.91 | 1.00 | 0.99 [0.88–1.19] | 39 [34–46] | 0.45 | 0.04 (0.00) | 579 | 0 |
| `decision_head` | split | 563 | 563 (563) | 99681 | 232.5 | 0.83 | 1.00 | 0.80 [0.72–1.27] | 42 [30–50] | 0.43 | 0.03 (0.00) | 561 | 0 |
| `hybride` | contradiction | 460 | 232 (232) | 147966 | 159.8 | — | — | 1.03 [0.88–1.35] | 53 [50–58] | 0.47 | — *(non journalisée sur ces runs)* | 460 | 0 |
| `hybride` | split | 272 | 202 (202) | 125216 | 119.9 | — | — | 1.11 [1.03–1.67] | 33 [22–48] | 0.38 | — *(non journalisée sur ces runs)* | 272 | 0 |
| `llm_grand` | contradiction | 560 | 560 (560) | 368223 | 332.6 | — | — | 1.03 [0.88–1.67] | 47 [30–58] | 0.38 | — *(non journalisée sur ces runs)* | 560 | 0 |
| `llm_grand` | split | 520 | 520 (520) | 337258 | 326.9 | — | — | 1.23 [0.64–1.59] | 49 [46–58] | 0.33 | — *(non journalisée sur ces runs)* | 520 | 0 |
| `regles` | contradiction | 143 | 0 (0) | 0 | 0.3 | 0.70 | 1.00 | 1.27 [1.11–1.59] | 24 [22–26] | 0.29 | 0.40 (0.00) | 143 | 0 |
| `regles` | split | 126 | 0 (0) | 0 | 0.3 | 0.70 | 1.00 | 1.03 [0.80–1.51] | 25 [22–26] | 0.24 | 0.41 (0.14) | 126 | 0 |

## Escalades et replis, par cause et par bras

| bras | scénario | escalades | replis |
|---|---|---|---|
| `decision_head` | contradiction | — | — |
| `decision_head` | split | — | — |
| `hybride` | contradiction | — | — |
| `hybride` | split | — | — |
| `llm_grand` | contradiction | — | — |
| `llm_grand` | split | — | — |
| `regles` | contradiction | — | — |
| `regles` | split | — | — |

## Ce que ces tables ne disent pas

- I6 n'apparaît pas : aucune porte ne ferme dans ce scénario, donc I6 vaut 0 **par construction**.
- Les temps absolus ne sont pas des temps de terrain : ce modèle passe ≈3,2 pers/(m·s) par mètre de porte contre ≈1,3 en littérature (ADR-015). Les comparaisons entre bras, elles, tiennent.
- Une « cible résolue par le moteur » n'est pas une réussite du modèle : le tier petit dit « sortir » sans nommer la porte, et le moteur choisit parmi les sorties connues et non crues bloquées.

