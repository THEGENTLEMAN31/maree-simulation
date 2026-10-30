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

| bras | `lag_effect` | `lag_llm` | `lag_indicator` | appels | mural |
|---|---:|---:|---:|---:|---:|
| petite, **sync** | 0,0 | **0,0** | 1,5 | 60 | 23 s |
| petite, **async** | 0,5 | **8,0** | 5,0 | 47 | 19 s |
| grande, **sync** | 0,0 | **0,0** | 1,5 | 86 | 28 s |
| grande, **async** | 1,0 | **15,0** | 8,0 | 61 | 21 s |

Trois lectures, dont une qui contredit l'hypothèse de départ.

**1. En synchrone, le décalage est nul — et c'est la barrière qui le cache.**
`lag_llm = 0` dans les deux bras synchrones, à 20 comme à 60 agents. Ce
n'est pas que les LLM répondent instantanément : c'est que le run
**attend** la réponse avant de passer au tick suivant. La charge ne
disparaît pas, elle se paie ailleurs — en temps mural (28 s contre 23 s)
et en appels (86 contre 60).

**2. En asynchrone, le décalage double quand la population triple.**
`lag_llm` passe de 8,0 à 15,0 ticks et `lag_indicator` de 5,0 à 8,0. La
file derrière `max_concurrency = 4` s'allonge : le douzième agent attend
trois fois plus que le premier. **C7 est vérifié** : le décalage évolue
sous charge, et il évolue dans le sens prévu.

**3. `lag_indicator` ne bouge pas avec la population en synchrone**
(1,5 tick dans les deux cas), alors que l'hypothèse annonçait une hausse.
La raison est mesurable : le rayon de fumée (15 m) couvre la place, donc
48 agents à règles voient le signal au même tick et l'agrégat bouge
tout de suite. Ce n'est pas un agrégat qui attend la foule, c'est une
foule qui réagit en bloc. L'hypothèse était fausse, et elle est
consignée telle quelle.

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

| médiane (n = 5) | 20 agents | 60 agents | lecture |
|---|---:|---:|---|
| I1 consensus | 0,99 | 0,99 | identique |
| I3 évacués | **0,85** | **0,95** | 3 piégés dans les deux cas |
| I7 délai dernier sorti | 210 s | **390 s** | la densité ralentit |
| appels LLM | 60 | 86 | 7 LLM contre 12 |
| mural | 23 s | 28 s | |

**Le nombre de piégés ne dépend pas de la taille.** Médiane de 3 dans les
deux populations, avec des profils mélangés (visiteurs et habitués) :
c'est une propriété du **savoir** des agents et du scénario, pas de la
densité. I3, qui est une *part*, baisse donc mécaniquement à 20 agents
(3/20 = 15 %) sans que rien d'autre n'ait changé. Afficher I3 seul
laisserait croire que la petite foule évacue moins bien ; c'est faux, et
c'est le genre d'artefact que C8 sert à voir.

**Ce qui change vraiment, c'est le temps** : I7 passe de 210 à 390 s
presque triplement de la population. Le moteur physique (JuPedSim) paie
la densité, pas la cognition.

**Réserve honnête** : 19 des 20 runs X10 atteignent `max_ticks = 72`.
I3 est donc censuré — les agents restants ne sortiront jamais, et le
chiffre mesure « ce qui est sorti avant la coupure ». Les comparaisons
ci-dessus portent sur des runs tous censurés, donc restent valables
entre elles ; elles ne disent pas combien de temps il aurait fallu.

---

## X11 — synchrone contre asynchrone, et la question de MARÉE

Même scénario, même population (60 agents, 12 LLM + 48 règles), 5 graines.

| médiane (n = 5) | `sync` | `async` |
|---|---:|---:|
| I1 consensus | 0,99 | 0,99 |
| I3 évacués | **0,95** | **0,92** |
| I7 dernier sorti | 460 s | **580 s** |
| `lag_ticks` médian | **0** | **9** |
| `lag_ticks` max | **0** | **19** (≈ 190 s simulées) |
| appels LLM | 91 | 61 |
| mural | 30 s | 21 s |

**L'asynchrone dégrade l'évacuation, et c'est un résultat, pas un défaut.**
I3 baisse de 3 points, I7 monte de 120 s. La raison est mécanique : une
décision fondée sur la perception de t est appliquée à t+19 ; entre les
deux, la foule a bougé et la cible choisie peut être plus loin, ou
encombrée. Le mode « réaliste » est le moins efficace — c'est exactement
ce qu'un modèle qui suppose la simultanéité ne peut pas voir.

**L'asynchrone coûte moins d'appels** (61 contre 91) : un agent qui attend
sa réponse ne redemande rien, et les agents déjà sortis ne décident plus.
Le run est aussi plus rapide en mural (21 s contre 30 s) : on n'attend
plus le plus lent à chaque tick, on attend le prochain tick.

### La question de MARÉE : les rapides sortent-ils devant ?

Question posée avant de mesurer : « en mode asynchrone, les visiteurs qui
réfléchissent vite atteignent-ils les sorties avant les autres ? ».

Agents **LLM seulement** (les 48 agents à règles décident en 0 tick et
écraseraient la comparaison), agrégés sur les 5 graines :

| profil | modèle | `lag_ticks` médian | sorti, `sync` | sorti, `async` |
|---|---|---:|---:|---:|
| visiteur | petit | **11** | t40 | **t65,5** |
| vendeur | petit | 12 | t31 | t68 |
| sécurité | grand | 12 | t17 | t39 |
| habitué | grand | 12 | t20 | t52 |
| famille | grand | 12 | t15 | t39,5 |

**Réponse : non.** Le petit modèle est bien plus rapide — 11 ticks contre
12, soit ~10 s simulées, et la différence est stable (192 décisions
contre 124) — mais cette avance de **un tick** ne pèse rien devant les
**25 ticks** qui séparent la sortie d'un visiteur de celle d'un habitué.
Ce qui fait sortir tôt, ce n'est pas la vitesse de réflexion, c'est le
**savoir** : les visiteurs ne connaissent que la sortie A, et ils la
cherchent.

Sous charge, la latence est de toute façon dominée par la file
(`max_concurrency = 4`) et non par le modèle : 11 contre 12 ticks, alors
que le même petit modèle répond en ~1 s contre ~2,8 s pour le grand quand
il est seul. **La file mange la différence entre les modèles** — c'est
une observation gênante pour un dispositif qui prétend router par
difficulté, et elle est consignée telle quelle.

**Réserve** : 4 graines sur 5 atteignent `max_ticks = 72` en asynchrone.
I3 y est censuré, comme dans X10.
