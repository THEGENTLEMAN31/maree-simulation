# Résultats de la campagne macro (C6)

Monde : `crowd_hall` (22 × 16 m, deux issues de 1,2 m), 60 agents, tick de 2 s. Graines : 1, 2, 3, 4, 5 — scénarios : split, contradiction.

Chaque ligne est la **médiane** des runs du bras ; `[min–max]` donne l'intervalle observé, jamais un écart-type qui masquerait un run.

| bras | scénario | décisions | appels (ok) | jetons | mural (s) | I1 | I3 | I5 [min–max] | I7 s [min–max] | décisions vers porte crue bloquée (dont faute de mieux) | paroles | cibles résolues par le moteur |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `hybride` | contradiction | 446 | 232 (232) | 148468 | 138.0 | 0.88 | 1.00 | 1.11 [0.88–1.35] | 54 [50–58] | 0.45 (0.00) | 446 | 0 |
| `hybride` | split | 280 | 207 (207) | 127809 | 120.7 | 0.79 | 1.00 | 1.27 [1.03–1.75] | 28 [22–54] | 0.38 (0.00) | 280 | 0 |
| `llm_grand` | contradiction | 517 | 517 (517) | 341036 | 313.3 | 0.92 | 1.00 | 1.11 [0.88–1.35] | 48 [34–50] | 0.40 (0.00) | 517 | 0 |
| `llm_grand` | split | 525 | 525 (525) | 339694 | 315.2 | 0.78 | 1.00 | 1.19 [0.88–1.67] | 44 [44–52] | 0.31 (0.00) | 525 | 0 |
| `llm_petit` | contradiction | 448 | 448 (448) | 52924 | 23.1 | 0.87 | 1.00 | 1.11 [0.95–1.67] | 30 [26–34] | 0.44 (0.00) | 448 | 448 |
| `llm_petit` | split | 447 | 447 (447) | 53193 | 22.5 | 0.87 | 1.00 | 1.11 [0.80–1.67] | 28 [26–34] | 0.44 (0.00) | 447 | 447 |
| `regles` | contradiction | 149 | 0 (0) | 0 | 0.3 | 0.69 | 1.00 | 1.27 [1.19–1.59] | 24 [22–26] | 0.29 (0.00) | 149 | 0 |
| `regles` | split | 136 | 0 (0) | 0 | 0.3 | 0.72 | 1.00 | 1.03 [0.80–1.51] | 26 [22–26] | 0.24 (0.14) | 136 | 0 |

## Escalades et replis, par cause et par bras

| bras | scénario | escalades | replis |
|---|---|---|---|
| `hybride` | contradiction | {'information_contradictoire': 1002, 'situation_inedite': 152} | — |
| `hybride` | split | {'information_contradictoire': 854, 'situation_inedite': 177} | — |
| `llm_grand` | contradiction | — | — |
| `llm_grand` | split | — | — |
| `llm_petit` | contradiction | — | — |
| `llm_petit` | split | — | — |
| `regles` | contradiction | — | — |
| `regles` | split | — | — |

## Ce que ces tables ne disent pas

- I6 n'apparaît pas : aucune porte ne ferme dans ce scénario, donc I6 vaut 0 **par construction**.
- Les temps absolus ne sont pas des temps de terrain : ce modèle passe ≈3,2 pers/(m·s) par mètre de porte contre ≈1,3 en littérature (ADR-015). Les comparaisons entre bras, elles, tiennent.
- Une « cible résolue par le moteur » n'est pas une réussite du modèle : le tier petit dit « sortir » sans nommer la porte, et le moteur choisit parmi les sorties connues et non crues bloquées.

