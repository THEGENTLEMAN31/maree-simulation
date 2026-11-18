# Résultats de la campagne macro (C6)

Monde : `crowd_hall` (22 × 16 m, deux issues de 1,2 m), 60 agents, tick de 2 s. Graines : 1, 2, 3, 4, 5 — scénarios : split, contradiction.

Chaque ligne est la **médiane** des runs du bras ; `[min–max]` donne l'intervalle observé, jamais un écart-type qui masquerait un run.

| bras | scénario | décisions | appels (ok) | jetons | mural (s) | I1 | I3 | I5 [min–max] | I7 s [min–max] | décisions vers porte crue bloquée | cibles résolues par le moteur |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `hybride` | contradiction | 374 | 120 (120) | 59898 | 68.6 | 0.84 | 1.00 | 0.95 [0.88–1.11] | 50 [42–52] | 0.38 | 0 |
| `hybride` | split | 108 | 87 (87) | 43495 | 49.7 | 0.63 | 1.00 | 0.64 [0.56–0.88] | 22 [20–24] | 0.00 | 0 |
| `llm_grand` | contradiction | 312 | 312 (312) | 153694 | 178.8 | 0.63 | 1.00 | 0.64 [0.56–0.88] | 22 [20–24] | 0.00 | 0 |
| `llm_grand` | split | 310 | 310 (310) | 150138 | 176.1 | 0.63 | 1.00 | 0.64 [0.56–0.88] | 22 [20–24] | 0.00 | 0 |
| `llm_petit` | contradiction | 312 | 312 (312) | 36876 | 15.7 | 0.63 | 1.00 | 0.64 [0.56–0.88] | 22 [20–24] | 0.00 | 312 |
| `llm_petit` | split | 310 | 310 (310) | 36890 | 15.6 | 0.63 | 1.00 | 0.64 [0.56–0.88] | 22 [20–24] | 0.00 | 310 |
| `regles` | contradiction | 119 | 0 (0) | 0 | 0.2 | 0.60 | 1.00 | 1.27 [1.19–1.59] | 24 [22–26] | 0.25 | 0 |
| `regles` | split | 60 | 0 (0) | 0 | 0.2 | 0.63 | 1.00 | 0.64 [0.56–0.88] | 22 [20–24] | 0.00 | 0 |

## Escalades et replis, par cause et par bras

| bras | scénario | escalades | replis |
|---|---|---|---|
| `hybride` | contradiction | {'information_contradictoire': 446, 'situation_inedite': 161} | — |
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

