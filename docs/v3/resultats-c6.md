# Résultats de la campagne macro (C6)

Monde : `crowd_hall` (22 × 16 m, deux issues de 1,2 m), 60 agents, tick de 2 s. Graines : 1, 2, 3, 4, 5 — scénarios : split, contradiction.

Chaque ligne est la **médiane** des runs du bras ; `[min–max]` donne l'intervalle observé, jamais un écart-type qui masquerait un run.

| bras | scénario | décisions | appels (ok) | jetons | mural (s) | I1 | I3 | I5 [min–max] | I7 s [min–max] | décisions vers porte crue bloquée | cibles résolues par le moteur |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `hybride` | contradiction | 437 | 130 (130) | 60633 | 73.8 | 0.74 | 1.00 | 1.51 [1.27–1.75] | 30 [30–32] | 0.42 | 0 |
| `hybride` | split | 310 | 87 (87) | 39393 | 48.7 | 0.63 | 1.00 | 0.64 [0.56–0.88] | 22 [20–24] | 0.00 | 0 |
| `llm_grand` | contradiction | 312 | 312 (312) | 149554 | 180.0 | 0.63 | 1.00 | 0.64 [0.56–0.88] | 22 [20–24] | 0.00 | 0 |
| `llm_grand` | split | 310 | 310 (310) | 145998 | 176.5 | 0.63 | 1.00 | 0.64 [0.56–0.88] | 22 [20–24] | 0.00 | 0 |
| `llm_petit` | contradiction | 363 | 363 (363) | 42894 | 18.6 | 0.60 | 1.00 | 0.72 [0.64–0.88] | 22 [22–28] | 0.08 | 363 |
| `llm_petit` | split | 347 | 347 (347) | 41293 | 17.6 | 0.60 | 1.00 | 0.72 [0.64–0.88] | 22 [22–28] | 0.09 | 347 |
| `regles` | contradiction | 118 | 0 (0) | 0 | 0.2 | 0.60 | 1.00 | 1.35 [1.11–1.51] | 24 [22–24] | 0.50 | 0 |
| `regles` | split | 60 | 0 (0) | 0 | 0.2 | 0.60 | 1.00 | 1.35 [1.11–1.51] | 24 [22–24] | 0.50 | 0 |

## Escalades et replis, par cause et par bras

| bras | scénario | escalades | replis |
|---|---|---|---|
| `hybride` | contradiction | {'information_contradictoire': 446, 'situation_inedite': 205} | — |
| `hybride` | split | {'information_contradictoire': 300, 'situation_inedite': 137} | — |
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

