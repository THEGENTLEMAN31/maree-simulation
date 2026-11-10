# Passation — état du projet au 2026-11-04

_Ce document sert à reprendre le travail dans une nouvelle session, sans
reconstruire le contexte. Il est volontairement factuel._

---

## 1. Où est le dépôt

```text
/home/jose/school/mondes_vivants/maree-simulation
branche : main
```

Le dépôt est la source de vérité. Les fichiers sont sur disque : fermer une
fenêtre de conversation ne perd rien. En revanche, **l'arbre de travail n'est
pas commité** (voir §3).

---

## 2. Ce qui a été décidé (ne pas rediscuter sans raison)

La v3 change de mission :

> **Mission 1 : le comportement humain.** Deux agents du même archétype doivent
> diverger à cause de leur mémoire personnelle.
> **Mission 2 : l'aide à la conception** (sorties, feux, variantes), secondaire.

Décisions structurantes (détail dans `docs/v3/decisions.md`) :

| # | Décision |
|---|---|
| ADR-001 | comportement d'abord |
| ADR-002 | Godot est le front de référence, glTF est le contrat |
| ADR-003 | aucune rétrocompatibilité v2 |
| ADR-004 | mono-étage en v3.0, multi-étages en v3.1 |
| ADR-005 | aucun moteur de foule maison : JuPedSim + `jupedsim-network` + coordinateur |
| ADR-006 | fumée grossière, pas de propagation de flammes |
| ADR-007 | OpenJev = tête de décision optionnelle, évaluée avant adoption |
| ADR-008 | matrice de stockage, pas de base unique |
| ADR-009 | assets importés, pas générés |
| ADR-010 | Graphify = outil de développement, pas runtime |
| ADR-011 | dossier agent configurable, 3 étiquettes (`measured`, `derived`, `generated`) |
| ADR-012 | validation ISO 20414 + protocole comportemental |

---

## 3. État Git exact

Arbre de travail **non commité** :

```text
M .gitignore
M AGENTS.md
M Makefile
M README.md
M src/maree/agents/graph.py
M src/maree/engine/replay.py
M src/maree/engine/trace.py
M tests/test_replay.py
M tests/test_trace.py
?? .graphifyrc
?? .graphifyignore
?? docs/schemas.md
?? docs/v3/
```

Deux choses distinctes sont mélangées :

1. **Correctifs v2 validés** (`replay.py`, `trace.py`, `graph.py`, tests) :
   rejeu du tier `small`, `known_exits`, `mismatch_count`, `trace` sans
   `KeyError`. Tests : `214 passed`.
2. **Plan v3 + Graphify** (`docs/v3/`, `.graphifyrc`, `.graphifyignore`,
   Makefile, README, AGENTS).

### Première action recommandée

Faire deux commits séparés :

```bash
git add src/maree/agents/graph.py src/maree/engine/replay.py \
        src/maree/engine/trace.py tests/test_replay.py tests/test_trace.py \
        AGENTS.md
git commit -m "fix(replay): re-parser le tier small, tracer les chaînes causales"

git add docs/v3 docs/schemas.md .graphifyrc .graphifyignore \
        Makefile README.md .gitignore AGENTS.md
git commit -m "docs(v3): plan de conception et intégration Graphify"
```

Vérifier avant : `uv run pytest` (attendu : 214 passed).

---

## 4. Ce qui tourne déjà

- `graphify 0.9.90` installé ;
- `make graph` construit `graphify-out/` (1 227 nœuds, 2 941 arêtes,
  58 communautés, 86 % EXTRACTED / 14 % INFERRED) ;
- `make graph-report`, `make graph-query Q="..."` disponibles ;
- `graphify-out/` est ignoré par Git.

---

## 5. Par où reprendre

Lire, dans cet ordre :

1. `docs/v3/README.md` — mission, objectifs, non-objectifs, index ;
2. `docs/v3/decisions.md` — les 12 ADR ;
3. `docs/v3/comportement.md` — le cœur (mémoire, individualité, phénomènes) ;
4. `docs/v3/architecture.md` — les 4 artefacts et les contrats ;
5. `docs/v3/roadmap.md` — la semaine 1.

Puis exécuter la **semaine 1** :

- squelette `src/maree/v3/` (dossiers + `__init__`) ;
- CI minimale (lint, type, tests, build) ;
- `bootstrap.py` : point d'assemblage unique ;
- vérifier que `make graph` et `uv run pytest` passent ;
- ne pas encore implémenter le comportement (semaine 2).

---

## 6. Règles à ne pas enfreindre

- **Ne pas réintroduire de configuration morte.** Un paramètre déclaré est lu,
  ou supprimé.
- **Ne pas écrire de moteur de foule, de base de données, d'index vectoriel,
  de serveur HTTP, d'auth ou de moteur de rendu.**
- **Ne pas utiliser le LLM à chaque tick.** Politique `hybrid` par défaut.
- **Ne pas confondre Graphify et la connaissance des agents.** Graphify lit le
  code ; les agents lisent le `KnowledgeStore`.
- **Ne pas promettre du photoréalisme.** Low-poly stylisé assumé.
- **Ne pas réintroduire la compatibilité v2.**
- **Toute décision structurante va dans `docs/v3/decisions.md`.**
- **Toute affirmation doit être mesurée** (test, run, ablation).

---

## 7. Pièges connus de la v2 (à ne pas répéter)

- deux tables de croyances, dont une jamais écrite → le prompt voit
  « aucune croyance » ;
- `config_hash` sans monde, sans modèle, sans corpus ;
- `recall_k`, `rag.k`, `temperature`, `max_tokens`, `api_key` déclarés mais
  jamais lus ;
- 83 % des octets du journal sont des snapshots ; `state.json` les duplique ;
- WebSocket qui relit tout le journal à chaque boucle ;
- `hello.plan` vient de la config courante, pas du journal ;
- pas de CI, packaging non autonome, Docker cassé.

---

## 8. Ce qu'il faut demander à l'utilisateur

- confirmer les deux commits ci-dessus ;
- confirmer le périmètre de la semaine 1 ;
- dire si le style low-poly importé est validé (sinon, choisir les packs
  d'assets et les licences).
