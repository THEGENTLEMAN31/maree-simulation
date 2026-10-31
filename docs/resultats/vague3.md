# Vague 3 — le temps, et ce qui dérive

_Trois exigences du socle (C3, C4, A4) et deux d'excellence (C7, C8).
Protocoles X10 (deux tailles de population × deux modes) et X11
(synchrone contre asynchrone), 5 graines par bras._

Fichiers bruts : `runs/experiment_x10.json`, `runs/experiment_x11.json`.

---

## A4 — un agent qui dérive n'arrête rien, et laisse une trace

Le repli sur les règles existait depuis la v1, mais il était **muet** :
`fallback: true` sans dire pourquoi. A4 demande « chaque incident est
tracé et dénombré » — un compteur unique ne suffit pas, parce que trois
causes différentes se soignent différemment :

| `kind` | ce qui s'est passé | ce qu'il faut corriger |
|---|---|---|
| `no_response` | pas de réponse (timeout, serveur éteint) | l'infrastructure |
| `unparseable` | une réponse, mais rien d'exploitable | le prompt ou le parseur |
| `unknown_action` | une action qui n'existe pas | le vocabulaire du prompt |
| `unknown_exit` / `unknown_zone` | une cible absente du plan | le modèle (il invente) |
| `out_of_role` | une cible réelle que **ce profil** ignore | le prompt du profil |
| `timeout` | (asynchrone) pas de réponse avant la clôture | la charge |

`out_of_role` est le cas qui compte pour A4 : « un agent sort de son
rôle ». Un visiteur qui nomme la sortie B ne se trompe pas de mot — il
parle d'un lieu qu'il ne connaît pas. Le confondre avec `unknown_exit`
accuserait le modèle à tort.

**Mesuré sur un run réel** (`c4_async_02`, 60 agents) : 8 incidents,
2 causes (`unknown_zone` × 4, `out_of_role` × 1, …), et le run va au
bout — 55 agents sortis. Sur `c4_sync_01` : 3 incidents, 57 sortis.

---

## C3 — deux horodatages, pas un champ recopié

`t_prod` est le moment simulé où l'événement **se produit**, `t_trait`
celui où il est **traité**. Les deux existaient déjà dans l'enveloppe,
mais `_emit` les remplissait avec la même valeur : la distinction était
décorative.

Elle ne l'est plus :

- **messages** : `run.message_delay_ticks = n` fait qu'un message dit à
  t est lu à t+n. Vérifié par un test (`t_trait − t_prod == 2` sur
  chaque `message.heard`) et par un protocole ;
- **décisions** : en mode asynchrone, la décision est produite au tick
  de la perception et traitée au tick où la réponse arrive. `lag_ticks`
  porte l'écart dans la trame.

En mode synchrone, les deux coïncident — c'est la définition du mode, pas
un oubli. Le client reçoit les deux champs sur **toutes** les trames
(`docs/protocol-ui.md` §3) et peut donc dessiner une latence sans rien
recalculer.

---

## C4 — synchrone et asynchrone, sélectionnables au lancement

```bash
uv run maree run run.mode=async bus.backend=memory
uv run maree experiment --name x11 --seeds 5 bus.backend=memory
```

| mode | qui décide quand | `t_prod` / `t_trait` |
|---|---|---|
| `sync` | tous au même pas de temps, le run attend les réponses | égaux |
| `async` | chacun à son rythme, la décision s'applique quand elle arrive | distincts, l'écart est la latence réelle |

**La latence est réelle, pas tirée d'une graine.** L'appel part au tick
de la perception ; la tâche est ramassée au premier tick où elle aboutit.
Ce qui est un choix, c'est la **cadence** : `tick_delay_s` (0,25 s par
défaut en asynchrone) fixe le rapport entre secondes réelles et ticks.
Sans cadence, la boucle tournerait plus vite que le modèle et aucune
réponse n'arriverait jamais. Ce n'est donc pas une latence inventée :
c'est la latence mesurée, convertie par une cadence déclarée.

Le plafond de concurrence (`max_concurrency = 4`) s'applique dans les
deux modes. Sans lui, l'asynchrone lancerait douze appels d'un coup et la
file serait dans le routeur llama.cpp, pas dans le moteur — on mesurerait
la charge d'un autre système que celui qu'on décrit.

À la clôture, les décisions encore en vol sont drainées (`async_drain_s`),
puis annulées et comptées en `timeout` : un agent muet ne bloque pas la
fin du run, et son silence est tracé (A4).

---

## C7 — le décalage, et ce qu'il devient sous charge

`maree lag --run-id …` (et `metrics/lag.py`) mesurent **trois**
décalages par événement du monde, parce que trois choses différentes se
produisent :

| mesure | sens |
|---|---|
| `effect_ticks` | premier descendant causal — le monde a été **perçu** |
| `llm_ticks` | première décision LLM causée — le monde a été **compris** |
| `indicator_ticks` | premier bloc d'indicateurs qui bouge — le monde a été **mesuré** |

Exemple sur `c4_async_02` : la fumée de t10 est perçue à 0 tick (un agent
à règles réagit tout de suite), comprise à 8 ticks (le premier LLM a
répondu), mesurée à 1 tick (l'agrégat a bougé avant même que le LLM ait
fini — les agents à règles sont 48 sur 60).

C'est cette dissociation qui rend C7 mesurable : « pris en compte dans les
indicateurs » n'est pas « compris par les agents », et un dispositif qui
ne mesure que le premier croit que la foule réagit en un tick.

### Mesuré (X10, 5 graines par bras)

> **Chiffres refaits le 2026-10-30 à 16 h.** Les valeurs publiées avec la
> vague 3 mesuraient un **défaut**, pas un modèle : le tier « small »
> recevait le JSON à vocabulaire ouvert, auquel un modèle de 0,6 Md ne
> répond jamais autre chose que `search` (confiance 0). Ses six agents
> cherchaient indéfiniment et redécidaient à chaque filet, ce qui gonflait
> les appels et écrasait I3. Depuis, le petit modèle reçoit une liste
> fermée (`agents/parsing.py::parse_choice`). Les anciens chiffres sont
> conservés plus bas pour mémoire ; ceux qui font foi sont ceux-ci.

| bras | `lag_effect` | `lag_llm` | `lag_indicator` | appels | mural | I3 | I7 |
|---|---:|---:|---:|---:|---:|---:|---:|
| petite, **sync** | 0,0 | **0,0** | 1,5 | 37 | 17,4 s | 0,95 | 110 s |
| petite, **async** | 2,0 | **5,5** | 3,5 | 43 | 18,7 s | 0,90 | 210 s |
| grande, **sync** | 0,0 | **0,0** | 1,5 | 48 | 12,6 s | 1,00 | 220 s |
| grande, **async** | 0,5 | **8,0** | 2,5 | 57 | 15,9 s | 1,00 | 340 s |

**1. En synchrone, le décalage est nul — et c'est la barrière qui le cache.**
`lag_llm = 0` dans les deux bras synchrones, à 20 comme à 60 agents. Ce
n'est pas que les LLM répondent instantanément : c'est que le run
**attend** la réponse avant de passer au tick suivant. La charge ne
disparaît pas, elle se paie ailleurs, en temps mural et en durée de run.

**2. En asynchrone, le décalage croît avec la population : 5,5 → 8,0
ticks.** La file derrière `max_concurrency = 4` s'allonge. C'est la
prédiction de C7, et elle tient.

**3. `lag_indicator` reste petit (1,5 → 2,5)** : le signal de fumée est
perçu par toute la place au même tick, donc l'agrégat bouge presque
aussitôt. Ce n'est pas un agrégat qui attend la foule, c'est une foule qui
réagit en bloc.

**4. I7 paie l'asynchrone dans les deux populations** : 110 → 210 s (20
agents) et 220 → 340 s (60). Une décision fondée sur la perception de t
s'applique 5 à 8 ticks plus tard ; entre-temps la foule a bougé. C'est
l'effet robuste de ce protocole, et il ne dépend pas de la taille.

**4. `lag_indicator` ne bouge pas avec la population en synchrone**
(1,5 tick dans les deux cas), alors que l'hypothèse annonçait une hausse.
Le rayon de fumée (15 m) couvre la place : les agents à règles voient le
signal au même tick et l'agrégat bouge tout de suite. Ce n'est pas un
agrégat qui attend la foule, c'est une foule qui réagit en bloc.

<details>
<summary>Chiffres de la vague 3, mesurés avant la correction du petit
modèle (conservés pour la comparaison)</summary>

| bras | `lag_llm` | `lag_indicator` | appels | mural |
|---|---:|---:|---:|---:|
| petite, sync | 0,0 | 1,5 | 60 | 23 s |
| petite, async | 8,0 | 5,0 | 47 | 19 s |
| grande, sync | 0,0 | 1,5 | 86 | 28 s |
| grande, async | 15,0 | 8,0 | 61 | 21 s |

L'écart est net : 86 appels à 60 agents contre 28 après correction. Le
« décalage qui double » était l'empreinte d'un modèle qui tournait à vide.

</details>

---

## C1 — les événements transitent par Kafka, et voici la granularité

**Mesuré, pas affirmé.** Un run à règles (`kafka_rules_01`, 60 agents,
1 023 événements au journal) écrit sur un vrai Redpanda ; un consommateur
indépendant (`scripts/kafka_check.py`, `group_id=None`, donc sans
engagement) recompte ce qu'il a vu :

```
agent.decisions            272 messages
    agent.decision               212
    agent.evacuated               60
agent.social               706 messages
    agent.belief                 212
    agent.message.heard          434
    agent.message.sent            60
metrics.indicators          20 messages
    metrics.indicators            20
world.events                 4 messages
    run.ended                      1
    run.started                    1
    world.announcement             1
    world.smoke                    1
runs distincts : 1  |  total : 1002
```

1 023 événements au journal, **1 002 sur le bus** : la différence est
exactement les 21 instantanés (`t0` + 20 ticks). C'est la granularité
choisie, et elle se justifie par une mesure :

| type | part des octets d'un run | publié ? | pourquoi |
|---|---:|---|---|
| `world.snapshot` | **61 % à 89 %** | **non** | c'est de l'**état**, pas un fait ; il se reconstruit |
| `agent.decision` | 6 % à 20 % | oui, `agent.decisions` | le client l'anime, l'analyste l'exploite |
| `agent.message.*` | 1,5 % à 9 % | oui, `agent.social` | débit différent, consommateur différent |
| `agent.belief` | 1,4 % à 6 % | oui, `agent.social` | c'est la carte mentale, pas la décision |
| `metrics.indicators` | 0,6 % à 1,1 % | oui, `metrics.indicators` | tableau de bord, 1 message par tick |
| `world.*` | < 1 % | oui, `world.events` | rare et décisif |
| `narrative.generated` | < 1 % | oui, `narrative.generated` | 4 par run |
| `agent.incident` | < 0,1 % | oui, `agent.decisions` | A4 : un incident se surveille |
| `world.tick` | — | non | bruit de boucle, aucun consommateur |

La table est **une seule déclaration** (`TOPIC_FOR` dans
`simulation.py`), documentée à côté d'elle. Un type absent de la table ne
part pas ; c'est le cas de l'instantané, qui pèse à lui seul 818 Kio sur
1 363 dans `demo_replay` et 5 428 Kio sur 6 247 dans `c4_sync_01`.

Conséquence assumée : **un consommateur Kafka ne reçoit pas les
instantanés**. Il a les faits (qui a décidé quoi, qui a entendu qui, où
en sont les indicateurs) et peut maintenir son propre état ; s'il lui
faut l'état exact, il lit le journal — c'est ce que fait `maree serve`.
Publier l'état à 10 Hz saturerait le broker pour une donnée dérivable.

Le bus reste **best-effort** : un broker mort incrémente `bus_failures`
et n'arrête jamais un run (le journal est la source de vérité). Mesuré
sur la campagne X1–X9 : 0 échec avec `bus.backend=memory`, et le run
Kafka ci-dessus a produit 1 002 messages sans erreur.

---

## C8 — deux tailles de population

| médiane (n = 5, asynchrone) | 20 agents | 60 agents | lecture |
|---|---:|---:|---|
| I1 consensus | 0,99 | 0,99 | identique |
| I3 évacués | **0,90** | **1,00** | 1 à 3 piégés sur 20, aucun sur 60 |
| I7 délai dernier sorti | 210 s | **340 s** | la densité ralentit |
| appels LLM | 43 | 57 | 7 LLM contre 12 |
| mural | 18,7 s | 15,9 s | la file, pas la foule |

**À 20 agents, I3 est plus bas — et ce n'est pas la foule qui évacue plus
mal.** Un à trois agents restent piégés sur vingt, ce qui vaut 5 à 15 % ;
à 60 agents, les mêmes profils piégés pèsent moins d'un pour cent. I3 est
une *part* : la comparer entre deux tailles sans regarder le **nombre**
d'évacués ferait croire à un effet de densité qui n'existe pas. C'est
exactement l'artefact que C8 sert à voir.

**Ce qui change vraiment, c'est le temps** : I7 passe de 210 à 340 s. Le
moteur physique (JuPedSim) paie la densité, pas la cognition — les appels
LLM n'augmentent que de 43 à 57 alors que la population triple.

**Réserve honnête** : dans les deux bras asynchrones, un à trois agents ne
sortent pas avant `max_ticks = 72`. I3 mesure donc « ce qui est sorti
avant la coupure ». Les comparaisons portent sur des runs tous censurés
de la même façon, donc restent valables entre elles ; elles ne disent pas
combien de temps il aurait fallu.

---

## X11 — synchrone contre asynchrone, et la question de MARÉE

Même scénario, même population (60 agents, 12 LLM + 48 règles), 5 graines.

| médiane (n = 5) | `sync` | `async` |
|---|---:|---:|
| I1 consensus | 0,98 | 0,99 |
| I3 évacués | **1,00** | **0,98** |
| I7 dernier sorti | 220 s | **470 s** |
| `lag_ticks` médian | **0** | **5** |
| `lag_ticks` max | **0** | **12** (≈ 120 s simulées) |
| appels LLM | 47 | 60 |
| mural | 12,7 s | 20,4 s |

**L'asynchrone dégrade l'évacuation, et c'est un résultat, pas un défaut.**
I7 double (220 → 470 s) et I3 perd deux points. La raison est mécanique :
une décision fondée sur la perception de t est appliquée jusqu'à 12 ticks
plus tard ; entre les deux, la foule a bougé et la cible choisie peut être
plus loin, ou encombrée. Le mode « réaliste » est le moins efficace —
c'est exactement ce qu'un modèle qui suppose la simultanéité ne peut pas
voir.

**L'asynchrone coûte aussi plus cher en appels** (60 contre 47) et en
temps mural (20,4 s contre 12,7 s) : les agents qui attendent une réponse
continuent de percevoir des signaux et redécident au tick suivant, et le
run dure plus longtemps. C'est le prix de ne pas figer le monde.

### La question de MARÉE : les rapides sortent-ils devant ?

Question posée avant de mesurer : « en mode asynchrone, les visiteurs qui
réfléchissent vite atteignent-ils les sorties avant les autres ? ».

Agents **LLM seulement** (les 48 agents à règles décident en 0 tick et
écraseraient la comparaison), agrégés sur les 5 graines :

| profil | modèle | `lag_ticks` médian | sorti, `sync` | sorti, `async` |
|---|---|---:|---:|---:|
| visiteur | petit | **5** | t15,5 | **t25** |
| vendeur | petit | **5** | t29,5 | t44 |
| sécurité | grand | 7 | t19 | t35 |
| habitué | grand | 6 | t20 | t37 |
| famille | grand | 8,5 | t12,5 | t29 |

**Réponse : à moitié.** Le petit modèle réagit bien plus vite — 5 ticks
contre 7 à 8,5, soit 20 à 35 s simulées, sur 162 décisions contre 144 —
mais cette avance ne décide pas de qui sort devant :

- la **famille** (grand modèle) sort la première, à t12,5 / t29 : elle est
  placée près des sorties et son proche est à côté d'elle ;
- le **visiteur** (petit modèle) suit de près, à t15,5 / t25 : il réagit
  vite, mais ne connaît qu'une sortie ;
- le **vendeur** (petit modèle) sort **dernier**, à t29,5 / t44, alors
  qu'il est le plus rapide : son profil protège son stand avant de partir.

Autrement dit, **le profil décide de l'ordre, la taille du modèle décide
de la réaction**. Les 20 ticks qui séparent un vendeur d'une famille
viennent de ce qu'ils priorisent, pas de leur vitesse de réflexion.

Sous charge, la latence est de toute façon dominée par la file
(`max_concurrency = 4`) et non par le modèle : 5 contre 8 ticks, alors
que le même petit modèle répond en ~0,4 s contre ~2,8 s pour le grand
quand il est seul. **La file mange la différence entre les modèles** —
c'est une observation gênante pour un dispositif qui prétend router par
difficulté, et elle est consignée telle quelle.

**Réserve** : 4 graines sur 5 atteignent `max_ticks = 72` en asynchrone.
I3 y est censuré, comme dans X10.
