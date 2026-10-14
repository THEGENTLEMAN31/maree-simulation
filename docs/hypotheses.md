# Hypothèses préenregistrées (C5, décision 13)

_Ce document est daté et versionné : les hypothèses existent AVANT toute
mesure. Modifier une hypothèse après coup doit se faire dans un commit daté
avec justificatif._

Date de préenregistrement : **2026-10-13**

## Hypothèses principales (issues du cadrage)

| ID | Hypothèse | Expérience |
|----|-----------|------------|
| H1 | Une annonce claire émise moins de 3 min simulées après la première fumée réduit le temps d'évacuation médian et l'écart croyance/réalité, par rapport à une annonce ambiguë émise après 6 min | X1 |
| H2 | La fermeture soudaine de la sortie la plus chargée (A) piège davantage de monde quand la foule suit surtout un meneur que quand chacun décide seul | X2 |
| H3 | En mode asynchrone, la répartition entre sorties diffère du mode synchrone, car les agents qui décident vite atteignent les sorties en premier | X3 |
| H4 | La version LLM diffère de la baseline à règles sur l'écart croyance/réalité (I2), mais pas sur le temps d'évacuation (I3). Un résultat contraire reste recevable s'il est démontré (E1) | X4 |
| H5 | Un agent qui a reçu un échange préalable (mémoire A1) choisit plus souvent la sortie recommandée, ou évite la déconseillée, que le même agent sans échange | X5 |
| H6 | Deux profils placés dans la même situation décident différemment ; échanger les profils échange les décisions (A3) | X6 |
| H7 | Désactiver le RAG augmente l'écart croyance/réalité (I2) | X7 |

## Hypothèses de seuils (à ajuster après les runs pilotes)

- Annonce « claire » : contenu explicite, diffusée à T+2 min simulées.
- Annonce « ambiguë » : contenu vague, diffusée à T+8 min simulées.
- Seuil de densité au goulot (I3) : > 4 agents dans la zone passerelle sur
  plus de 3 ticks consécutifs.

## Protocole de test de piste

- Chaque conclusion repose sur **≥ 5 runs par configuration**, sur
  **≥ 2 configurations** (E2).
- Statistiques : **médiane + écart interquartile** (pas moyenne), test
  non paramétrique Mann-Whitney (n petit).
- Chaque run est **rejouable depuis le journal seul** ; un hash des
  indicateurs vérifie l'identité du rejeu (E3).