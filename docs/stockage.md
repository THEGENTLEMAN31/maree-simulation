# Où vivent les données — F3, et comment on les interroge — F5

_Écrit le 2026-10-30, chiffres refaits le 2026-10-31. Ils sont mesurés
sur le dépôt de travail (451 runs, 1,2 Go) et se reproduisent avec les
commandes citées._

---

## 1. Le problème, tel que F3 le pose

> « Le binôme distingue et justifie où vivent le flux d'événements, l'état
> courant du monde, l'historique des runs et la base de connaissances,
> chacun selon ses besoins d'accès : volume, fréquence, latence, durée de
> conservation. »

Quatre objets, quatre régimes d'accès différents. Les mettre dans le même
endroit oblige à choisir un compromis qui n'est bon pour aucun : une base
relationnelle qui absorbe 1 000 écritures par seconde et répond en
millisecondes coûte cher à opérer ; un fichier append-only qui répond en
millisecondes ne sait pas répondre à « donne-moi la dernière valeur ».

Le choix retenu est donc **quatre stockages, quatre contrats**, et un seul
principe : le journal est la source de vérité, tout le reste en dérive et
peut être reconstruit.

| | flux d'événements | état courant | historique des runs | base de connaissances |
|---|---|---|---|---|
| **quoi** | ce qui est arrivé, dans l'ordre | où est le monde **maintenant** | les runs terminés, comparables | ce que les agents peuvent retrouver |
| **où** | `runs/<id>/events.jsonl` | `runs/<id>/state.json` | `runs/<id>/` + `runs/experiment_*.json` | `world_corpus/` + `data/rag/` |
| **format** | JSONL append-only | un objet JSON, remplacé | JSONL + JSON d'agrégats | Markdown → passages + vecteurs |
| **volume mesuré** | 1,78 Mo / run (60 agents, 20 ticks)<br>7,1 Mo (60 agents, 72 ticks) | 70 Ko / run | 1,2 Go pour 451 runs | 884 Ko de corpus<br>215 passages, 1,1 Mo d'index |
| **fréquence d'écriture** | ~50 événements / tick, jamais modifiés | 1 fois tous les 10 % de ticks | à la fin du run | à l'indexation, hors ligne |
| **latence de lecture** | `maree replay` : tout relire, ~0,4 s | `maree state` : **0,40 s**, un seul fichier | `maree query` : 3,4 s sur 451 runs | recherche FAISS : millisecondes, 215 vecteurs |
| **conservation** | indéfinie (preuve, rejeu) | la dernière valeur seulement | indéfinie (résultats publiés) | tant que le corpus ne change pas |

### Pourquoi le flux d'événements est un fichier, pas une base

Le journal est **append-only et immuable** : on n'y écrit que des faits
validés (`adapters/journal/jsonl.py` met en quarantaine un événement
malformé au lieu de l'écrire). Aucune requête ad hoc n'est nécessaire
pendant le run ; l'écriture doit être séquentielle et pas chère. Un JSONL
donne les deux, et reste lisible par `head`, `jq` ou DuckDB (§3) sans
serveur. Le bus (Redpanda) transporte les **mêmes** faits, mais il est un
canal de diffusion, pas un stockage : il n'est pas dans le chemin de
mesure (`bus.backend=memory` dans les campagnes).

### Pourquoi l'état courant est un fichier séparé (le seul ajout de F3)

Avant ce document, l'état courant n'avait pas de domicile : il vivait en
RAM pendant le run, et pour le retrouver après coup il fallait relire le
journal entier. Or **77 % des octets du journal sont des instantanés**
(1 366 222 octets sur 1 766 247 pour `f3_state_01`, 21 instantanés sur
1 023 événements) : chercher « où est tout le monde maintenant » dans ce
fichier coûte 4 fois le prix de l'information cherchée.

`JsonStateStore` (`adapters/state.py`) écrit donc `state.json`, remplacé à
chaque instantané :

- **écriture atomique** (`tmp` + `os.replace`) : un client qui lit pendant
  que le run écrit ne voit jamais un JSON tronqué ;
- **rétention = dernière valeur** : l'histoire est déjà dans le journal, la
  dupliquer créerait deux vérités possibles ;
- **lecture 0,40 s contre plusieurs secondes** pour rescanner le journal,
  pour 70 Ko au lieu de 1,78 Mo.

```bash
uv run maree state                      # le dernier run écrit (tri par mtime)
uv run maree state --run-id f3_state_01 # counts + taille
uv run maree state --full               # l'état complet, agents compris
```

Un état absent n'est pas une erreur fatale : `maree state` le dit et
renvoie vers le journal (les runs antérieurs à F3 n'ont pas de `state.json`).

### Pourquoi l'historique des runs est un répertoire, pas une table

Un run est un **dossier** : son journal, son état, sa quarantaine. Le
supprimer est un `rm -rf`, l'archiver un `tar`. Les agrégats d'expérience
(`runs/experiment_x*.json`, ~8 Ko par protocole) portent une ligne par
run — c'est ce que lit `maree report`.

Passer à une base imposerait un schéma à des champs qui bougent d'une
vague à l'autre (`lag_ticks`, `models`, `incident_kinds` sont apparus en
vagues 3 et 4). Le schéma vit dans les **requêtes** (§3), qui sont du code
versionné et relu, pas dans un `ALTER TABLE` oublié.

### Pourquoi la base de connaissances est du Markdown indexé, pas une table

Le corpus est écrit à la main (`world_corpus/`, 215 fichiers Markdown :
annonces, souvenirs d'éditions, consignes, plans, fiches de profil). Il
doit rester **relisible par un humain** : une annonce est un texte, pas une
ligne. `maree index` le découpe en passages, calcule les vecteurs bge-m3 et
écrit `data/rag/` (`vectors.npy` 880 Ko, `passages.json` 158 Ko,
`mean.npy`). C'est un **produit dérivé** : on peut supprimer `data/rag/` et
le reconstruire en 7 s. Aucun run ne dépend de sa présence — sans index, la
décision se fait sans RAG et le journal le dit.

### Ce qu'on n'a pas fait, et pourquoi

- **Pas de Parquet.** DuckDB lit les JSONL nativement (§3) ; convertir
  ajouterait une étape à maintenir pour un gain nul à cette échelle
  (1,2 Go, 3,4 s de requête). Si le corpus atteignait des dizaines de Go, la
  question se poserait.
- **Pas de rétention automatique.** 1,2 Go pour 451 runs, dont la plupart
  sont des runs de campagne déjà publiés. Une politique de purge
  supprimerait des preuves ; c'est un choix de dépôt, pas un oubli.
- **Pas de serveur de requête.** `maree query` ouvre DuckDB en mémoire,
  lit, affiche, ferme. Pas de processus à surveiller.

---

## 2. Le journal reste la source de vérité

Corollaire des choix ci-dessus, et la raison pour laquelle ils tiennent :
**tout le reste est reconstructible**.

| stockage | reconstructible depuis |
|---|---|
| `state.json` | le dernier `world.snapshot` du journal |
| `runs/experiment_*.json` | les journaux, par `maree query` |
| `data/rag/` | `world_corpus/` par `maree index` |
| indicateurs, incidents, croyances | les événements, tick par tick |

Le seul stockage non reconstructible est le journal lui-même : c'est
pourquoi il est append-only, séquencé (`seq`), et pourquoi `maree replay`
(E3) vérifie qu'on peut rejouer ses décisions.

---

## 3. F5 — interroger plusieurs runs par des requêtes reproductibles

> « L'historique de plusieurs runs s'interroge par des requêtes
> reproductibles, pour comparer les scénarios et produire les résultats du
> rapport. »

Les requêtes vivent dans `queries/*.sql`, **versionnées avec le code**. Le
rapport et les chiffres de soutenance sortent de la même commande : ils ne
peuvent pas diverger.

```bash
uv run maree query                      # la liste
uv run maree query runs                 # une ligne par run
uv run maree query runs --json | jq .   # sortie machine
uv run maree query --sql "SELECT ..."   # exploration ad hoc
```

| requête | ce qu'elle répond |
|---|---|
| `runs.sql` | ticks, run terminé, I3, I7, décisions, décisions LLM, incidents, mural — par run |
| `appels_par_modele.sql` | E5/A5 : appels, jetons et durée **par modèle et par tier** |
| `incidents.sql` | A4 : les dérives par cause, premier et dernier tick |
| `communication.sql` | A2/B3 : messages diffusés, I1 et I2 au dernier tick |
| `prehistoire.sql` | A1 : part des décisions dont le prompt porte un repère « J-… » |

### Le piège que `queries/_base.sql` évite

`data` change de forme à chaque type d'événement : une décision porte
`llm`, un instantané porte 60 agents, un incident porte `kind`. Laisser
DuckDB inférer un schéma commun (`read_json_auto(..., union_by_name=true)`)
sur 451 fichiers produit des **conversions silencieuses** : selon le run,
`data` devient une structure dont les champs sont typés JSON, et
`json_extract(data, '$.kind')` échoue ou renvoie des valeurs entre
guillemets. Le symptôme, constaté ici : une erreur `Malformed JSON … Input:
"llm"`, puis des comptes faux sans erreur.

La vue lit donc **ligne par ligne** — chaque ligne est du texte JSON, les
requêtes extraient ce qu'elles veulent :

```sql
FROM read_csv('runs/*/events.jsonl',
              columns = {'line': 'VARCHAR'},
              delim = '', quote = '', escape = '',
              header = false, ignore_errors = true)
```

Deuxième piège, plus vicieux parce qu'il ne lève rien : `max()` sur une
chaîne compare **lexicographiquement** — « 90.0 » gagne contre « 220.0 ».
Le `CAST(... AS DOUBLE)` doit être **à l'intérieur** du `max`, sinon I7
affiche 90 s pour un run à 220 s. C'est arrivé, et c'est ce qui a fait
écrire `tests/test_storage.py::test_f5_…`.

`ignore_errors = true` n'est pas de la complaisance : un run tué en pleine
écriture laisse une ligne tronquée dans `runs/run_x4_llm_60_s0_a5cc`. Faire
échouer l'analyse des 450 autres runs pour cette ligne serait le mauvais
compromis ; le déséquilibre se voit (une ligne sans `run.ended` dans
`queries/runs.sql`, colonne `termine`).

### Ce que F5 ne fait pas

L'historique n'est pas une base temps réel : `maree query` relit tous les
journaux à chaque appel (3,4 s pour 451 runs, 1,2 Go). Pour une interface
qui interroge en continu, c'est `maree serve` qu'il faut, pas `query`.

---

## 4. Reproduire les chiffres de ce document

```bash
uv run maree run run_id=f3_state_01 population=rules_only \
    bus.backend=memory narrative.enabled=false
ls -l runs/f3_state_01/            # 1 777 302 octets de journal, 70 581 d'état
uv run maree state --run-id f3_state_01
uv run maree query runs | head -5
uv run maree query incidents | head -5
```
