# Intégration de Graphify

_Graphify est un outil de **développement**. Il n'est pas une dépendance du
moteur, et il ne nourrit pas les agents._

---

## 1. Ce que c'est

[Graphify](https://github.com/Graphify-Labs/graphify) transforme un dépôt
(code, docs, PDF, images) en **graphe de connaissances** :

- parsing AST local avec tree-sitter (aucun LLM pour le code) ;
- `graph.json` persistant, `graph.html` interactif, `GRAPH_REPORT.md` ;
- commandes `query`, `path`, `explain` ;
- export Mermaid (`graphify export callflow-html`) ;
- serveur MCP optionnel ;
- tags `EXTRACTED` / `INFERRED` sur chaque arête.

Licence : Apache-2.0 / MIT. Version vérifiée : `0.9.90`.

---

## 2. Ce que ce n'est pas

- **pas** un modèle de connaissance du monde pour les agents ;
- **pas** une base vectorielle ;
- **pas** une dépendance runtime ;
- **pas** un substitut aux ADR ou à la documentation.

La connaissance partagée des agents est le `KnowledgeStore` (Postgres +
pgvector). Graphify ne lit que le **code du projet**.

---

## 3. Installation

Déjà installé sur la machine de développement :

```bash
graphify --version   # 0.9.90
```

Pour une nouvelle machine :

```bash
uv tool install graphifyy
graphify install --project --platform opencode
```

`graphify install --project` écrit la configuration dans le dépôt, ce qui
permet de la versionner.

---

## 4. Configuration du projet

### `.graphifyrc`

```ini
# Budget et profondeur des requêtes
query_budget=4000
query_depth=3

# Limite de nœuds pour la visualisation
viz_node_limit=5000
```

### `.graphifyignore`

```gitignore
# Données de run : trop volumineuses, aucune valeur structurelle
runs/
data/
models/
world_corpus/

# Environnements et caches
.venv/
.pytest_cache/
.hypothesis/
__pycache__/
node_modules/

# Sorties Graphify
graphify-out/
```

### `.gitignore`

Ajouter :

```gitignore
graphify-out/
```

Le graphe est un artefact local, pas un fichier versionné. En revanche,
`GRAPH_REPORT.md` peut être publié dans la documentation si on le souhaite.

---

## 5. Commandes

| Commande | Usage |
|---|---|
| `make graph` | construit le graphe code-only |
| `make graph-update` | met à jour après modifications |
| `make graph-report` | régénère `GRAPH_REPORT.md` |
| `make graph-html` | exporte le call-flow Mermaid |
| `graphify query "..."` | question sur le code |
| `graphify path "A" "B"` | chemin entre deux symboles |
| `graphify explain "X"` | explique un symbole |

### Exemples utiles

```bash
graphify query "où est écrite la mémoire sémantique ?"
graphify path "Simulation" "EventSourcedMemory"
graphify explain "LevelCoordinator"
graphify export callflow-html
```

---

## 6. Règles d'usage

1. **Query-first.** Avant de grep un symbole, interroger le graphe.
2. **ADR traçables.** Les commentaires `# NOTE:` et `# WHY:` deviennent des
   nœuds : on s'en sert pour relier une décision à son code.
3. **Pas de graphe dans le runtime.** Aucun agent ne lit `graphify-out/`.
4. **Pas de graphe dans le journal.** Ce n'est pas un fait du run.
5. **Mise à jour après les grosses refactos.** `make graph-update`.

---

## 7. CI

Le graphe code-only est **local et déterministe** : il peut tourner en CI
sans clé API.

```yaml
# extrait de CI
- name: Graphify (code only)
  run: |
    uv tool install graphifyy
    graphify extract . --code-only
    test -f graphify-out/graph.json
```

On ne publie pas `graphify-out/` ; on vérifie seulement que le graphe se
construit.

---

## 8. Confidentialité

- le code est parsé **localement**, sans LLM ;
- les docs/PDF/images nécessitent un backend sémantique, optionnel ;
- en CI, on utilise `--code-only` ;
- aucun secret ne doit se trouver dans les fichiers indexés.

---

## 9. Limites

- le graphe code-only ne comprend pas les docs ni les diagrammes ;
- les arêtes `INFERRED` peuvent être fausses : elles sont étiquetées ;
- le graphe n'est pas une vérité métier, seulement une carte du code ;
- il ne remplace pas les tests ;
- le nommage des communautés (`GRAPH_REPORT.md`) utilise un backend LLM.
  Sans backend, Graphify retombe sur `Community N` : le graphe reste
  utilisable, seuls les libellés sont génériques ;
- les fichiers `.sql` nécessitent l'extra `graphifyy[sql]` pour contribuer
  au graphe.

---

## 10. Pourquoi l'intégrer dès le début

- le dépôt va changer de structure (v3), et une carte du code aide à garder
  la cohérence ;
- les ADR et les commentaires `WHY` deviennent navigables ;
- les revues d'impact (quel module dépend de la mémoire ?) sont plus rapides ;
- l'onboarding d'un nouveau développeur (ou d'un front) est accéléré.

C'est un multiplicateur de développement, pas une fonctionnalité du produit.
