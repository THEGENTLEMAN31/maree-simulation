# Protocole d'affichage — ce que le moteur envoie au client

_Contrat entre le moteur et l'interface. Le client est un **consommateur
pur** : il ne calcule rien, il dessine ce que le journal lui envoie.
Tout ce qui est décrit ici existe dans le journal, donc un run terminé se
rejoue à l'identique._

Date : 2026-10-28

---

## 1. Lancer

```bash
uv run maree serve                                  # dernier run, 5 ticks/s
uv run maree serve --run-id run_hybrid_08 --speed 3 # run précis
uv run maree serve --speed 0                        # aussi vite que possible
uv run maree serve --prompts                        # ajoute le prompt LLM
```

Le serveur écoute sur `ws://0.0.0.0:8765`. Il **relit le journal** : il
fonctionne sur un run terminé comme sur un run en cours (le fichier
grandit), sans dépendance au moteur ni au LLM. Un client qui se connecte
en cours de route reçoit l'historique depuis le début.

Chaque trame est un objet JSON, un par message WebSocket.

## 2. Espace

Les coordonnées sont en **mètres**, origine en **bas à gauche**, `y` vers
le haut. Le plan fait `width × height` (60 × 40 pour Port-Aubel).

Pour dessiner dans un repère écran (y vers le bas) :

```gdscript
screen = Vector2(p.x * px_per_m, (plan.height - p.y) * px_per_m)
```

## 3. Ordre des trames

Pour un tick donné, l'ordre est celui du journal :

```
world (fumée / annonce / fermeture)
decision × n
belief × n
message × n
heard × n
evacuated × n
event (tout ce qui n'a pas de trame typée)
snapshot
indicators
narrative (tous les N ticks)
```

Un client peut donc animer « X décide » puis « voilà le nouvel état »,
sans deviner. Le premier tick (`snapshot` de `tick: 0`) arrive juste
après `hello`.

**Rien n'est filtré.** Les événements qui n'ont pas de trame dédiée
(`run.started`, `control.injection`, un futur type) passent en `event`,
enveloppe comprise. Un client peut donc tout exploiter.

---

## 4. Les trames

_Les `…` dans les exemples marquent des listes tronquées, pas du JSON
valide à copier tel quel._

### `hello` — une fois, à la connexion

```json
{
  "type": "hello",
  "run_id": "run_20261028-204217_0_50cb",
  "run": {
    "config_hash": "33cc92cafd6784c3",
    "seed": 0,
    "plan": "port_aubel",
    "population": [
      {"profile": "securite", "count": 4, "kind": "rules"},
      {"profile": "famille", "count": 16, "kind": "rules"},
      {"profile": "visiteur", "count": 28, "kind": "rules"}
    ]
  },
  "plan": {
    "name": "Port-Aubel",
    "width": 60.0,
    "height": 40.0,
    "walkable": [[5.0, 5.0], [55.0, 5.0], "…"],
    "exits": [
      {"id": "A", "label": "Grand Quai", "a": [26.0, 35.0], "b": [32.0, 35.0]},
      {"id": "B", "label": "Ruelle des Cordiers", "a": [55.0, 16.0], "b": [55.0, 17.5]},
      {"id": "C", "label": "Passage des Halles", "a": [14.0, 5.0], "b": [17.0, 5.0]}
    ],
    "zones": [
      {"id": "Z1", "label": "Place nord", "polygon": [[18.0, 24.0], "…"]}
    ],
    "obstacles": [
      {"id": "tour", "kind": "tour", "polygon": [[26.0, 18.0], "…"]}
    ],
    "smoke": {"position": [44.0, 15.0], "radius": 15.0, "start_tick": 10}
  }
}
```

`run` donne la graine, le hash de configuration et la population réelle :
de quoi afficher un en-tête honnête (« graine 7, 60 agents, 12 LLM /
48 règles ») et vérifier qu'un run correspond à la config qu'on croit.

`walkable` est le domaine marchable, `obstacles` en sont les **trous**.
Une zone peut porter `"hidden": true` (la Ruelle Z8) : elle existe pour la
physique mais n'est pas une destination annoncée.

`smoke` donne le disque de fumée **prévu** ; c'est `smoke_active` dans
l'instantané qui dit s'il est déjà là.

> Le plan vient de la configuration courante (`configs/world/`), pas du
> journal. Un run et sa diffusion doivent donc utiliser le même fichier
> de monde.

### `world` — un événement du monde

```json
{"type": "world", "tick": 10, "kind": "smoke", "position": [44.0, 15.0], "radius": 15.0}
{"type": "world", "tick": 18, "kind": "announcement", "text": "Évacuation. Rejoignez la sortie nord."}
{"type": "world", "tick": 14, "kind": "exit_closed", "exit": "A"}
```

Trois `kind` : `smoke`, `announcement`, `exit_closed`. Ce sont des
**fronts** : ils arrivent une fois. Pour l'état persistant, voir
`smoke_active` et `exits_open` dans l'instantané.

### `decision` — une cognition

```json
{
  "type": "decision",
  "tick": 10,
  "agent_id": "A01",
  "kind": "rules",
  "trigger": "fumee_visible",
  "reason": "orienter vers A, la sortie la mieux dégagée",
  "intention": {
    "kind": "guide",
    "target": "A",
    "reason": "orienter vers A, la sortie la mieux dégagée",
    "tick": 10,
    "confidence": 0.85
  },
  "beliefs": {
    "A": {"confidence": 0.85, "source": "decision:t10", "tick": 10},
    "B": {"confidence": 0.322, "source": "connu", "tick": 0},
    "C": {"confidence": 0.322, "source": "connu", "tick": 0}
  },
  "position": [31.64, 18.21],
  "density": 0.283
}
```

| champ | sens |
|---|---|
| `kind` | `"llm"` ou `"rules"` — qui a décidé |
| `trigger` | **pourquoi** on a décidé (`fumee_visible`, `annonce`, `sortie_fermee`, `proche_disparu`, `premiere_decision`, `periodique`) |
| `reason` | **pourquoi cette intention** (phrase du modèle ou de la règle) |
| `intention.kind` | `stay`, `go_exit`, `guide`, `follow`, `search` |
| `intention.target` | sortie (`A`), agent (`A14`), ou `null` |
| `beliefs` | table complète, pas seulement l'argmax |
| `density` | densité locale perçue (pers/m²) |

Avec `--prompts`, la trame porte en plus `llm.prompt` et `llm.response`
(~3 Ko par décision). Sans l'option, le prompt n'est pas transmis.

`trigger` et `reason` ne sont **pas** la même chose : le premier dit ce
qui a réveillé l'agent, le second ce qu'il a conclu. Les confondre rend
le panneau « pourquoi » inutilisable.

### `message` — une parole

```json
{
  "type": "message",
  "tick": 10,
  "from": "A01",
  "to": ["A02", "A03", "A07", "A33", "A37", "A38", "A44", "A52"],
  "content": "il faut sortir par la sortie A"
}
```

Un agent ne parle **qu'une fois**, et seulement s'il a perçu quelque
chose. `to` est la liste des voisins qui entendent : de quoi dessiner des
arcs émetteur → récepteurs.

### `heard` — une écoute

```json
{"type": "heard", "tick": 10, "agent_id": "A02", "from": "A01", "content": "il faut sortir par la sortie A"}
```

Un `heard` par destinataire. Redondant avec `message.to` si tu dessines
des arcs, indispensable si tu veux montrer **ce que chaque agent a
entendu** (une timeline par agent, un halo de propagation).

### `belief` — une croyance mise à jour

```json
{
  "type": "belief",
  "tick": 10,
  "agent_id": "A01",
  "beliefs": {
    "A": {"confidence": 0.85, "source": "decision:t10", "tick": 10},
    "B": {"confidence": 0.322, "source": "connu", "tick": 0},
    "C": {"confidence": 0.322, "source": "connu", "tick": 0}
  }
}
```

Émis juste après chaque décision. La même table est déjà dans
`decision.beliefs` et dans `snapshot.agents[].beliefs` : c'est une
commodité pour tracer une courbe de croyance sans relire les instantanés.

### `event` — tout le reste, sans filtre

```json
{
  "type": "event",
  "event": "run.started",
  "tick": 0,
  "seq": 1,
  "data": {"config_hash": "33cc92cafd6784c3", "seed": 0, "plan": "port_aubel", "population": ["…"]}
}
```

Tout événement du journal qui n'a pas de trame dédiée arrive ici, avec son
`seq` et son `data` d'origine : `run.started`, `control.injection`,
`dlq.invalid`, ou un type ajouté plus tard au moteur. Rien n'est perdu,
donc rien n'est impossible à dessiner.

### `evacuated` — une sortie physique

```json
{"type": "evacuated", "tick": 12, "agent_id": "A01", "kind": "exit"}
```

C'est un **fait physique**, pas une décision. Un agent peut décider
`go_exit` et mettre 8 ticks à sortir ; il peut aussi décider `stay` et
être porté par la foule. Ne pas confondre les deux compteurs.

### `snapshot` — l'état du monde

```json
{
  "type": "snapshot",
  "tick": 10,
  "sim_time": "1:40",
  "exits_open": ["A", "B", "C"],
  "smoke_active": true,
  "density_grid": [
    {"x": 8.0, "y": 33.0, "n": 1},
    {"x": 31.0, "y": 18.0, "n": 3}
  ],
  "agents": [
    {
      "id": "A13",
      "profile": "famille",
      "label": "Parent accompagné",
      "kind": "rules",
      "pos": [12.59, 7.91],
      "belief": "A",
      "confidence": 0.35,
      "beliefs": {
        "A": {"confidence": 0.35, "source": "connu", "tick": 0},
        "C": {"confidence": 0.35, "source": "connu", "tick": 0}
      },
      "entropy": 0.693,
      "intention": "stay",
      "intention_target": null,
      "evacuated": false,
      "kin": "A14",
      "decided_at": 7,
      "perceived": []
    }
  ]
}
```

| champ | sens |
|---|---|
| `exits_open` | sorties **réellement** ouvertes (fait physique) |
| `smoke_active` | la fumée est là (état, pas seulement l'événement t10) |
| `density_grid` | cellules **occupées** : origine en mètres + effectif `n` ; densité = `n / cell²` (cellule de 1 m) |
| `belief` | sortie crue la plus sûre (argmax) |
| `beliefs` | table complète ; un agent peut n'en connaître que deux (profil) |
| `entropy` | incertitude de l'agent (0 = sûr, ~1,1 = perdu) |
| `intention` / `intention_target` | ce qu'il fait maintenant |
| `kin` | proche apparié (`famille`), pour dessiner le lien |
| `decided_at` | dernier tick où il a décidé |
| `perceived` | ce qu'il a perçu : `smoke`, `announcement`, `closed:A`, `missing_kin` |

`pos` est un point par tick. Pour une animation fluide, **interpoler**
entre deux instantanés ; ne pas sauter.

### `indicators` — les six mesures

```json
{
  "type": "indicators",
  "tick": 10,
  "I1_consensus": 0.95,
  "I2_entropy": 0.4007,
  "I3_evacuated": 0.0,
  "I4_seconds": 100.0,
  "I5_max_density": 2.0,
  "I6_belief_gap": 0.0,
  "counts": {
    "agents": 60,
    "evacuated": 0,
    "remaining": 60,
    "by_belief": {"A": 57, "B": 1, "C": 2, "aucune": 0}
  }
}
```

| indicateur | sens | lecture |
|---|---|---|
| `I1_consensus` | part de la croyance majoritaire | 1 = la foule est d'accord |
| `I2_entropy` | incertitude moyenne normalisée | 0 = tous sûrs, 1 = tous perdus |
| `I3_evacuated` | part des agents sortis | avancement |
| `I4_seconds` | temps simulé écoulé | durée |
| `I5_max_density` | densité locale max (pers/m²) | le goulot |
| `I6_belief_gap` | part des agents croyant à une sortie **fermée** | le piège |

`by_belief` compte les agents **actifs** par sortie crue ; `aucune` est
explicite (un agent qui ne sait rien n'est pas un agent de plus sur A).

### `narrative` — le récit du chroniqueur

```json
{"type": "narrative", "tick": 10, "text": "La densité maximale atteint 2.0 personnes par mètre carré…"}
```

Le chroniqueur est **omniscient** : il lit tout, il n'écrit rien chez les
agents. Quatre récits par run en moyenne.

### `end` — fin de diffusion

```json
{"type": "end", "ticks": 20, "llm_calls": 0, "llm_ok": 0, "evacuated": 60, "total": 60}
```

Le serveur laisse **0,3 s** après cette trame avant de fermer la socket.
Lire les paquets en attente même quand la connexion est déjà fermée :
sinon `end` est perdu et l'UI affiche « déconnecté » sur une diffusion
pourtant terminée.

---

## 5. Ce qu'on peut dessiner (suggestions)

| donnée | rendu |
|---|---|
| `plan.walkable` / `obstacles` / `zones` | fond, trous, étiquettes de zone |
| `plan.exits` + `exits_open` | traits verts / rouges |
| `agents[].pos` | points, interpolation entre ticks |
| `agents[].belief` + `beliefs` | couleur par sortie crue, saturation = confiance |
| `agents[].entropy` | halo ou contour : qui hésite |
| `agents[].kind` | distinguer les 12 LLM des 48 règles |
| `agents[].kin` | lien fin entre proches |
| `agents[].intention` | flèche vers `intention_target` |
| `agents[].perceived` | pictogramme « a vu la fumée » |
| `density_grid` | carte de chaleur (`n` par cellule de 1 m) |
| `world kind=smoke` + `smoke_active` | disque de fumée |
| `message` | arc émetteur → `to`, qui s'efface |
| `decision` | panneau « pourquoi » : `trigger`, `reason`, `kind` |
| `indicators` | 6 jauges + barres empilées `by_belief` |
| `I6_belief_gap` | alerte : des agents croient en une sortie fermée |
| `narrative` | bandeau de récit |

Un piège à montrer plutôt qu'à cacher : à t10 la fumée pousse la foule
vers A ; si A ferme à t14, `I6_belief_gap` monte et ces agents se
dirigent vers une sortie morte. C'est **le** phénomène du sujet.

---

## 6. Pièges

1. **Le dernier tick est dégénéré.** Tout le monde est sorti, donc
   `I1`, `I2`, `I5`, `I6` valent 0. Ne pas afficher « effondrement du
   consensus » à la fin : c'est un artefact. Pour un résumé, prendre le
   pic de I5/I6 et la moyenne de I1/I2.
2. **`belief` ≠ `exits_open`.** `belief` est ce que l'agent *croit* ;
   `exits_open` est la réalité. L'écart entre les deux est le sujet.
3. **`decision` ≠ `evacuated`.** Le premier est une cognition, le second
   un franchissement. Un agent peut décider `stay` et sortir quand même.
4. **Les positions sont discrètes** (une par tick, 10 s simulées).
   Interpoler, sinon ça saccade.
5. **Un agent peut ne pas connaître toutes les sorties** : `beliefs` ne
   contient que celles de son profil. Ne pas colorer « inconnu » comme
   « indécis ».
6. **`exits_open` vide ne veut pas dire « tout ouvert »** : c'est un
   tableau vide, donc aucune sortie. (Le client actuel fait l'inverse,
   c'est un défaut connu.)
7. **`--speed` ne change que le rythme**, jamais les données.

---

## 7. Rejouer sans le moteur

Le journal est la source de vérité : `maree serve` sur un run terminé
produit exactement les mêmes trames, sans GPU, sans LLM, sans JuPedSim.
C'est ce qui rend une démonstration rejouable devant un jury.

---

## 8. Ce qui est à toi

`godot/project` est un **client de référence** : une scène, un script,
~250 lignes, juste de quoi vérifier que le flux arrive. Le moteur n'en
dépend pas — `maree serve` ne fait qu'écrire du JSON sur une socket.
Tu peux le supprimer, le réécrire, changer de renderer, passer en C#,
ajouter des shaders, faire du 2.5D : rien côté moteur ne le remarque.

Deux contrats seulement, et ils sont dans ce document :

1. **les trames** (§4) ;
2. **le journal JSONL**, si tu veux lire un run hors ligne.

Le reste — disposition, couleurs, panneaux, interactions, timeline — est
une décision d'interface, pas une décision de moteur.

### La timeline t'appartient

- `maree serve --speed 0` envoie tout le run en moins d'une seconde :
  bufferise, et tu as la main sur lecture, pause, retour arrière, ralenti.
- `maree serve --speed N` cadence le flux (N ticks/s) pour une démo en
  direct ou un run encore en cours.

### Si une donnée manque

Elle est probablement déjà là : `snapshot.agents[]` porte la croyance
complète, `event` porte tout le journal, `--prompts` porte le prompt LLM.
Si vraiment il manque quelque chose, c'est un **ajout au moteur** (un
champ dans l'instantané ou une trame), pas un bricolage côté client : le
client ne calcule pas, il dessine.
