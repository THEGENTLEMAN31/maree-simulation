# Vague 4 — la sobriété démontrée, les données rangées

_2026-10-31. Cette vague ferme les trois dernières exigences : E5 (le
gain des deux tiers), F3 (où vivent les données) et F5 (les requêtes qui
produisent le rapport)._

---

## E5 — la répartition des modèles est-elle un levier de sobriété ?

> « Le binôme utilise la répartition entre modèles de tailles différentes
> et agents à règles comme levier de sobriété. Il démontre le gain par
> rapport à une configuration où tous les agents utilisent le plus grand
> modèle, à apport comparable. »

### Le protocole X12 — un plan 2×2, et non deux bras

Quatre bras, même population (60 agents, 12 LLM dont **six de tier
« big » et six de tier « small »** — parité exacte), même scénario,
5 graines. Seule l'attribution du modèle et la forme de la question
changent.

| bras | grand modèle | petit modèle |
|---|---|---|
| `tous_grand` | JSON ouvert | *(aucun — les 12 sur le grand)* |
| `protocole_seul` | JSON ouvert | **gemma**, politique |
| `deux_tiers` | JSON ouvert | **qwen 0,6 Md**, politique |
| `petit_json_ouvert` | JSON ouvert | qwen 0,6 Md, JSON ouvert |

Deux bras de plus que nécessaire, et ils ne sont pas décoratifs :

- `protocole_seul` sépare l'effet du **modèle** de l'effet du
  **protocole** : sans lui, « 14 700 jetons au lieu de 21 600 » ne dit pas
  si l'on a économisé parce que le modèle est petit ou parce qu'on lui
  pose une question plus courte ;
- `petit_json_ouvert` est le témoin du défaut : le petit modèle devant le
  même JSON que le grand. Il montre que la répartition, **sans** protocole
  adapté, coûte plus cher que de tout faire sur le grand modèle.

### Mesuré (X12, 5 graines par bras)

| médiane | `tous_grand` | `protocole_seul` | `deux_tiers` | `petit_json_ouvert` |
|---|---:|---:|---:|---:|
| appels LLM | 50 | **42** | 48 | 79 |
| jetons entrée | 19 572 | **11 874** | 13 684 | 35 257 |
| jetons sortie | 2 047 | 983 | 1 014 | 3 904 |
| **jetons au total** | 21 619 | **12 857 (−41 %)** | **14 698 (−32 %)** | 39 161 (+81 %) |
| jetons par appel | 433 | 314 | **306** | 480 |
| I3 évacués | 1,00 | 1,00 | 1,00 | **0,95** |
| I7 dernier sorti | 150 s | **110 s** | **220 s** | 330 s |
| mural | 21,4 s | **13,9 s** | **12,4 s** | 27,1 s |
| incidents | 2 | 0 | 0 | 4 |

**Le gain existe, et il est mesuré à apport comparable sur I3** : le bras
`deux_tiers` évacue autant (1,00) que la référence « tous sur le plus
grand modèle », pour **−32 % de jetons** et **−42 % de temps mural**.

**Mais la décomposition dit une autre histoire que celle qu'on attendait.**
Le gain ne vient pas de la taille du modèle : `protocole_seul` — mêmes
deux tiers, mais le petit tier tourne sur le **grand** modèle — fait
encore mieux (−41 % de jetons) et évacue plus vite (I7 110 s contre 150).
Ce qui économise, c'est la **forme de la question** : une politique
explicite tient en 314 jetons quand le JSON ouvert en demande 433, et
surtout elle évite la mémoire, les croyances et les messages dans le
prompt. Le petit modèle, lui, n'ajoute que du temps mural (12,4 s contre
13,9 s) et **coûte 70 s d'évacuation** : ses agents réagissent moins bien
aux annonces (2 fois sur 6, mesuré).

Autrement dit : **le levier « deux tailles » fonctionne, mais c'est le
protocole réduit qui porte le gain** ; la taille du modèle est le levier
le plus faible des trois (protocole > agents à règles > taille du
modèle).

**Le témoin justifie la politique.** `petit_json_ouvert` consomme
**+81 % de jetons** que la référence et n'évacue que 0,95 : un petit
modèle devant une question trop ouverte n'est pas une économie, c'est une
dépense qui échoue. Les 293 décisions « small » contre 123 dans
`tous_grand` sont des agents qui redécident parce qu'ils n'ont rien décidé.

### Ce que le petit modèle sait faire — quatre formats essayés

Tout ceci est mesuré sur le vrai serveur, pas supposé. `qwen3-0-6b`
(0,6 Md) **ne raisonne pas : il suit la forme du prompt**.

| format | réponse observée | verdict |
|---|---|---|
| JSON à vocabulaire ouvert | `{"action":"search","confidence":0.0}`, le gabarit recopié, 55 décisions sur 55 | inutilisable |
| liste de mots-clés (`SORTIR A`, `CHERCHER`, `RESTER`) | **toujours la première option** : `SORTIR A` en tête → les visiteurs évacuent au tick 3, avant la fumée de t10 ; `RESTER` en tête → personne ne part jamais | inutilisable |
| question binaire `OUI/NON` | instable : dépend de la formulation du prompt système, vire au OUI par défaut | non fiable |
| **règle écrite + drapeaux oui/non** | `calme` → RESTER 6/6 ; `fumée` → SORTIR 6/6 ; `annonce` → SORTIR 2/6 | **retenu** |

Le protocole retenu (`agents/parsing.py::parse_choice`,
`graph._build_choice_prompt`) dit au petit modèle : « si la fumée est
visible, tu sors ; si une annonce dit d'évacuer, tu sors ; sinon tu
restes », puis lui donne deux drapeaux (`Fumée visible : oui/non`,
`Annonce d'évacuation : oui/non`). Il répond `SORTIR` ou `RESTER`.

**Corollaire, à assumer en soutenance : le petit modèle _applique_ une
politique, le grand la _juge_.** Ce n'est pas la même tâche, et c'est
précisément pourquoi le gain vient du protocole. La limite de l'annonce
(2/6) est réelle : dans un monde où l'information passe par la parole,
elle coûterait cher.

Deux détails qui ont coûté du temps :

- le prompt système du petit modèle ne doit pas contenir le contrat JSON
  du grand (`Profile.persona` le retire) : les deux consignes mêlées, il
  répondait OUI à t1, sans fumée, et sortait au tick 3 ;
- la destination n'est pas demandée au petit modèle : elle vient de la
  première sortie connue et ouverte (`_known_exits`). Lui demander de
  choisir une sortie dans une liste, c'est revenir au biais de position.

---

## F3 — où vivent les données

Document complet : `docs/stockage.md`. Résumé du choix :

| | flux d'événements | état courant | historique des runs | base de connaissances |
|---|---|---|---|---|
| **où** | `runs/<id>/events.jsonl` | `runs/<id>/state.json` | `runs/<id>/` + `experiment_*.json` | `world_corpus/` + `data/rag/` |
| **volume** | 1,78 Mo / run (20 ticks)<br>7,1 Mo (72 ticks) | 70 Ko / run | 1,2 Go pour 451 runs | 884 Ko + 1,1 Mo |
| **fréquence** | ~50 écritures / tick | à chaque instantané | à la fin du run | à l'indexation |
| **latence** | ~0,4 s (relecture complète) | **0,40 s** | 3,4 s (451 runs) | millisecondes |
| **conservation** | indéfinie | dernière valeur | indéfinie | tant que le corpus vit |

**Le seul ajout de code est l'état courant.** Il n'avait pas de domicile :
il vivait en RAM, et après coup il fallait relire tout le journal. Or 77 %
des octets du journal sont des instantanés (1 366 222 sur 1 766 247 pour
`f3_state_01`, 21 instantanés sur 1 023 événements) : « où est tout le
monde **maintenant** » coûtait quatre fois le prix de la réponse.

`JsonStateStore` écrit donc `state.json`, **remplacé** à chaque instantané,
en écriture atomique (`tmp` + `os.replace`) — un client qui lit pendant
l'écriture ne voit jamais un JSON tronqué. 70 581 octets contre 1 777 302,
et `maree state` répond en 0,40 s.

```bash
uv run maree state --run-id f3_state_01
# {"run_id": "f3_state_01", "tick": 20,
#  "counts": {"agents": 60, "evacuated": 60, "remaining": 0}, "bytes": 70087}
```

Trois stockages sur quatre existaient déjà ; ce qui manquait, c'était de
**dire lequel sert à quoi et pourquoi**. Le journal reste la source de
vérité : `state.json` se reconstruit depuis son dernier instantané,
`data/rag/` depuis `world_corpus/` en 7 s, les agrégats d'expérience depuis
les journaux — et c'est ce qui justifie de ne pas en faire des bases.

---

## F5 — des requêtes reproductibles sur plusieurs runs

> « L'historique de plusieurs runs s'interroge par des requêtes
> reproductibles, pour comparer les scénarios et produire les résultats du
> rapport. »

Les requêtes sont du **code versionné**, dans `queries/*.sql` :

| requête | ce qu'elle sort |
|---|---|
| `runs.sql` | ticks, run terminé, I3, I7, décisions, décisions LLM, incidents, mural |
| `appels_par_modele.sql` | appels, jetons et durée **par modèle et par tier** |
| `incidents.sql` | A4 : dérives par cause, premier et dernier tick |
| `communication.sql` | A2/B3 : messages diffusés, I1 et I2 au dernier tick |
| `prehistoire.sql` | A1 : part des décisions dont le prompt porte un « J-… » |

```bash
uv run maree query runs --json | jq '.[0]'
uv run maree query appels_par_modele | head -5
uv run maree query --sql "SELECT count(*) FROM events"
```

Mesuré sur le dépôt : **449 970 événements, 451 runs, 3,4 s** pour la
requête la plus large (1,2 Go de JSONL, DuckDB en mémoire, aucun serveur).

### Deux pièges, tous les deux silencieux

1. **L'inférence de schéma.** `data` change de forme à chaque type
   d'événement. `read_json_auto(..., union_by_name = true)` sur 451
   fichiers finit par convertir `data` en structure typée JSON, et
   `json_extract` échoue (`Malformed JSON … Input: "llm"`) ou renvoie des
   valeurs entre guillemets. La vue lit donc **ligne par ligne** : chaque
   ligne est du texte JSON, les requêtes extraient ce qu'elles veulent.
2. **`max()` sur une chaîne.** « 90.0 » bat « 220.0 » en comparaison
   lexicographique : I7 affichait 90 s pour un run à 220 s. Le `CAST(… AS
   DOUBLE)` doit être **à l'intérieur** du `max`. Attrapé en comparant au
   rapport, gardé par un test.

`ignore_errors = true` est assumé : un run tué en pleine écriture laisse une
ligne tronquée dans `runs/run_x4_llm_60_s0_a5cc`. Faire échouer l'analyse
des 450 autres runs pour cette ligne serait le mauvais compromis — et le
déséquilibre se voit (colonne `termine` dans `runs.sql`).

---

## X10 et X11 refaits — les chiffres de la vague 3 mesuraient un défaut

Le tier « small » de la vague 3 recevait le JSON ouvert : ses six agents
répondaient `search` avec une confiance de 0, ne sortaient pas, et
redécidaient à chaque filet périodique. X10 et X11 ont donc été rejoués
avec le protocole retenu (5 graines par bras).

**X10 — deux tailles de population, deux modes :**

| bras | `lag_effect` | `lag_llm` | `lag_indicator` | appels | mural | I3 | I7 |
|---|---:|---:|---:|---:|---:|---:|---:|
| petite (20), sync | 0,0 | **0,0** | 1,5 | 37 | 17,4 s | 0,95 | 110 s |
| petite (20), async | 2,0 | **5,5** | 3,5 | 43 | 18,7 s | 0,90 | 210 s |
| grande (60), sync | 0,0 | **0,0** | 1,5 | 48 | 12,6 s | 1,00 | 220 s |
| grande (60), async | 0,5 | **8,0** | 2,5 | 57 | 15,9 s | 1,00 | 340 s |

La prédiction de C7 tient : sous charge, `lag_llm` passe de 5,5 à 8,0
ticks quand la population triple. En synchrone il reste nul dans les deux
cas — c'est la barrière qui cache la charge, pas le modèle qui répond
vite.

**X11 — synchrone contre asynchrone :**

| médiane (n = 5) | `sync` | `async` |
|---|---:|---:|
| I1 consensus | 0,98 | 0,99 |
| I3 évacués | **1,00** | **0,98** |
| I7 dernier sorti | 220 s | **470 s** |
| `lag_ticks` médian / max | 0 / 0 | **5 / 12** |
| appels LLM | 47 | 60 |
| mural | 12,7 s | 20,4 s |

L'asynchrone double I7 et coûte plus cher (60 appels contre 47, 20,4 s
contre 12,7 s) : les agents qui attendent une réponse continuent de
percevoir des signaux et redécident, et le run dure plus longtemps. Le
mode « réaliste » est le moins efficace — c'est ce qu'un modèle qui
suppose la simultanéité ne peut pas voir.

### La question de MARÉE : les rapides sortent-ils devant ?

Agents **LLM seulement** (les 48 agents à règles décident en 0 tick),
agrégés sur les 5 graines :

| profil | modèle | `lag_ticks` médian | sorti, `sync` | sorti, `async` |
|---|---|---:|---:|---:|
| famille | grand | 8,5 | t12,5 | t29 |
| visiteur | petit | **5** | t15,5 | t25 |
| sécurité | grand | 7 | t19 | t35 |
| habitué | grand | 6 | t20 | t37 |
| vendeur | petit | **5** | t29,5 | t44 |

**Réponse : à moitié.** Le petit modèle réagit plus vite (5 ticks contre
6 à 8,5), mais son avance ne décide pas de l'ordre : le **vendeur**, le
plus rapide, sort **dernier** (t29,5 / t44) parce que son profil protège
son stand ; la **famille**, la plus lente, sort **première** parce qu'elle
est placée près d'une sortie avec son proche. Le profil décide de
l'ordre, la taille du modèle décide de la réaction.

Les chiffres de la vague 3 (visiteurs à t40 et t65, « non, la vitesse ne
compte pas ») mesuraient des agents bloqués en `search`, pas des agents
lents.

---

## Ce que cette vague ne prouve pas

- **Le gain de E5 est mesuré à 6 agents « small » sur 12.** Avec 24 LLM
  il serait plus grand mais l'apport n'est plus comparable : les visiteurs
  LLM se font piéger et redécident (essai mesuré : 199 appels contre 101,
  0,83 contre 0,97 évacués).
- **Le petit modèle ne fait pas la même tâche que le grand** : il applique
  une politique, le grand la juge. C'est le prix de sa taille, et c'est ce
  qui explique que le gain vienne du protocole.
- **Il ignore à moitié les annonces** (2/6). Dans un monde où l'information
  passe par la parole, cette limite coûterait cher ; elle est mesurée, pas
  contournée.
- **L'énergie n'est pas re-mesurée par bras.** E4 a mesuré 0,46 Wh pour un
  run hybride ; X12 rapporte appels, jetons et temps mural. Une mesure en
  joules par bras serait plus convaincante : elle n'a pas été refaite.
- **`maree query` relit tout** à chaque appel (3,4 s sur 1,2 Go). Ce n'est
  pas un magasin temps réel ; pour une interface, c'est `maree serve`.
