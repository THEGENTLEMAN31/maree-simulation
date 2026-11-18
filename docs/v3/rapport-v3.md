# Rapport v3 — ce qui tourne, ce qui est mesuré, ce qui ne l'est pas

_18 novembre 2026. Ce document se lit seul. Il remplace
`docs/v3/rapport-v3-avant-correctif.md`, dont les sections 3 et 4 mesuraient
un moteur qui n'existe plus (voir ADR-014 à 018 et
`docs/v3/plan-redressement.md`). Les tableaux chiffrés sont régénérables
depuis les JSON du dépôt : aucun nombre de ce rapport n'est recopié à la main
sans sa source._

---

## 1. La question, et ce qui a changé

La v2 comptait des sorties. La v3 doit expliquer des **choix** : deux agents
du même archétype doivent diverger parce que leur **mémoire personnelle**
diffère. Pour que cette phrase soit mesurable, il fallait d'abord que le
moteur ne se raconte pas d'histoires. La vague de correctifs C2 à C7 a
consisté à retirer, une par une, les mesures qui ne mesuraient pas ce
qu'elles annonçaient.

Trois exemples, pris parmi dix, qui donnent le ton du reste :

| ce qui était affirmé | ce qui se passait vraiment |
|---|---|
| « les agents perçoivent la densité, le danger, leurs voisins » | `seen_agents=()`, `exits_visible=froisé vide`, `State()` neuf à chaque tick |
| « l'hybride appelle le modèle quand les règles sont indécises » | zéro appel sur toute une campagne : le critère était circulaire |
| « le LLM coûte X jetons » | le coût était lu sur la **dernière** décision de chaque agent |

Le reste du rapport décrit ce qui tient après correction, et avec quels
chiffres.

---

## 2. Le modèle expérimental : trois bras, un calendrier

Les trois bras partagent la perception, la physique et le journal. Ils ne
diffèrent que par **qui décide** et **quand**.

| bras | qui décide | quand (calendrier) | ce qu'il répond |
|---|---|---|---|
| `regles` | la politique déterministe | fronts : fumée, annonce, message, fermeture, proche | que fait-on sans modèle ? (témoin, coût nul) |
| `llm` | le modèle, à chaque **changement pertinent** de perception | fronts + plan invalidé + palier de contexte + revue | que fait un modèle quand il pilote ? |
| `hybride` | règles en routine, modèle si le **monde** est ambigu | fronts + escalade sur critères du monde + revue | qu'apporte le modèle, à quel prix ? |

**Le calendrier est un fait du monde, pas une horloge** (ADR-014). Décider
sur « le monde a bougé » reviendrait à redécider à chaque tick : c'est le coût
de la v1 (2 160 appels par run), reconstruction comprise.

Les critères d'escalade de l'hybride sont calculés sur des faits
(`agents/schedule.py`) : `information_contradictoire`, `annonce_ambigue`,
`situation_inedite`, `regles_indecises` (l'ancien critère, conservé et
**nommé**), `revue`, et un quota ε en SHA-256 qui n'est qu'un **instrument**
de sensibilité — jamais un bras. Chaque escalade publie `agent.escalation`
avec sa cause et ses valeurs ; une escalade sans cause serait un incident.

---

## 3. Le dispositif de mesure

### 3.1 Le monde a été calibré, pas hérité

`hall_3` (120 × 80 m) donne **0,000 pers/m²** à 60 agents : il n'y a pas de
foule, donc aucun indicateur de foule ne peut y bouger. Le monde de mesure est
donc `crowd_hall` (22 × 16 m, deux issues de 1,2 m), calibré pour que le bras
témoin produise un goulot visible (ADR-015) :

| mesure (règles, 5 graines) | valeur |
|---|---|
| I5 pic (noyau 2 m) | **1,11 – 1,51 pers/m²** |
| instant du pic | **t6–t7** (en marche, jamais au spawn) |
| vidage | **60/60** |
| I7 | 22 – 24 s |

### 3.2 Deux écarts au plan, dits et non maquillés

1. **I7 = 22–24 s, pas 40–80 s.** Ce modèle laisse passer ≈3,2 pers/(m·s) par
   mètre de porte contre ≈1,3 dans la littérature (`collision_free` ne
   compresse pas les corps). Atteindre 40 s aurait exigé une porte de 0,5 m
   ou une horloge inventée. L'écart est **le même sur les trois bras**, donc
   les comparaisons tiennent ; les temps absolus ne sont pas des temps de
   terrain.
2. **Le tick du scénario vaut 2 s**, pas 10 s : une salle qui se vide en 25 s
   ne donne que deux points de mesure à 10 s/tick. La durée du tick est un
   paramètre du run (`Simulation.tick_seconds`), et I4/I7 la suivent.

### 3.3 Ce que la mesure compte, par décision

- coût : appels **tentés**, appels **réussis**, jetons prompt/sortie, temps
  mural, temps LLM (somme des latences), temps de physique ;
- escalades par cause, replis par cause ;
- décisions qui reviennent vers **la porte désignée bloquée à t1** (le
  compteur est nommé pour ce qu'il mesure : la croyance s'oublie, un ouï-dire
  peut la repasser sous le seuil) ;
- décisions dont la cible a été **résolue par le moteur** (le petit modèle dit
  « sortir » sans nommer la porte) ;
- décisions prises **faute de mieux** (toutes les portes crues bloquées) —
  séparées, parce qu'une spirale de rumeur n'est pas une faute de politique.

### 3.4 Les deux scénarios

- `split` : à t1, la moitié de la foule apprend « A est bloquée », l'autre
  « B est bloquée ». Les deux portes restent **physiquement ouvertes**. La
  bonne réponse est de contourner ce que l'on croit fermé.
- `contradiction` : mêmes croyances, plus une annonce officielle qui nomme
  **A** — donc une consigne qui contredit la croyance d'un agent sur deux.

---

## 4. Les huit corrections qui ont changé les chiffres

Chacune est un défaut mesuré, pas une préférence. L'ordre est celui du
chantier.

1. **Ranger l'intention physique** (C1) : « rester » envoyait les agents vers
   l'origine du repère. Après : déplacement maximal 0,10 m sur 10 ticks.
2. **Donner à la perception son contenu** (C2) : 8 voisins ordonnés, densité
   en noyau de 2 m, distance au foyer, sorties visibles (ligne de vue), état
   qui évolue. Conséquence mesurable : `SUIVRE` devient atteignable (il était
   structurellement impossible).
3. **Sortir le calendrier de l'agent** (C3) : `should_decide` par bras. Sur
   le banc bloqué : `regles` **0 appel**, `hybride` **4 appels à t2**
   (`information_contradictoire`), `llm` **10 appels** bornés.
4. **Ne pas prendre une notice de fermeture pour un ordre** : « la sortie A
   est bloquée » n'est pas « évacuez par A ». La géographie ne s'apprend pas
   par ouï-dire.
5. **Mesurer le coût ligne par ligne** (C4) : l'ancienne lecture comptait un
   appel par agent et attribuait les jetons du dernier appel au run entier.
6. **Consommer la perception avant de décider** (ADR-016) : au même tick,
   « A est bloquée » + fumée n'était jamais utilisé. **0,50 des décisions**
   visaient la porte qu'on venait de dire fermée ; **0,00** après.
7. **Faire tenir la réponse escaladée** (ADR-017) : sans cela, un palier de
   densité renvoyait l'agent aux règles qui refaisaient le choix que le
   modèle venait de corriger. 310 → 108 décisions pour le même nombre
   d'appels.
8. **Faire parler les agents** (C7) : le tuyau social était branché d'un seul
   côté. Voir §5.3 — c'est la correction qui a le plus changé les
   conclusions.

---

## 5. Résultats

### 5.1 Le monde muet (sans émission entre agents)

Bras `regles` et `llm_petit`, cinq graines, code final
(`runs/v3/campaign_crowd_silence.json`) :

| bras | scénario | décisions | I1 | I3 | I5 | I7 | revient vers la porte désignée bloquée |
|---|---|---|---|---|---|---|---|
| `regles` | split | 60 | 0,63 | 1,00 | 0,64 | 22 s | **0,00** |
| `regles` | contradiction | 119 | 0,60 | 1,00 | 1,27 | 24 s | **0,25** |
| `llm_petit` | split | 310 | 0,63 | 1,00 | 0,64 | 22 s | 0,00 *(100 % moteur)* |
| `llm_petit` | contradiction | 312 | 0,63 | 1,00 | 0,64 | 22 s | 0,00 *(100 % moteur)* |

Dans un monde sans échange, une croyance reçue tient : les règles ne
reviennent jamais vers la porte qu'on leur a dite fermée (`split`), et ne le
font que quand l'**annonce officielle** les y envoie (`contradiction`, 0,25).
C'est la situation où le banc micro et la foule disent la même chose.

### 5.2 Le monde parlant (quatre bras, cinq graines)

`runs/v3/campaign_crowd.json`, 40 runs, tables complètes régénérables par
`uv run python scripts/rapport_crowd.py` :

| bras | scénario | appels | jetons | mural | I1 | I5 | I7 | revient vers la porte désignée bloquée |
|---|---|---|---|---|---|---|---|---|
| `regles` | split | 0 | 0 | 0,3 s | 0,72 | 1,03 | 26 s | 0,24 *(0,14 faute de mieux)* |
| `regles` | contradiction | 0 | 0 | 0,3 s | 0,69 | 1,27 | 24 s | 0,29 |
| `hybride` | split | 207 | 127 809 | 120,7 s | 0,79 | 1,27 | 28 s | 0,38 |
| `hybride` | contradiction | 232 | 148 468 | 138,0 s | 0,88 | 1,11 | 54 s | 0,45 |
| `llm_grand` | split | 525 | 339 694 | 315,2 s | 0,78 | 1,19 | 44 s | 0,31 |
| `llm_grand` | contradiction | 517 | 341 036 | 313,3 s | 0,92 | 1,11 | 48 s | 0,40 |
| `llm_petit` | split | 447 | 53 193 | 22,5 s | 0,87 | 1,11 | 28 s | 0,44 *(100 % moteur)* |
| `llm_petit` | contradiction | 448 | 52 924 | 23,1 s | 0,87 | 1,11 | 30 s | 0,44 *(100 % moteur)* |

Dans **40 runs sur 40**, la foule sort entièrement (60/60). Aucune censure,
aucun repli (7 388 appels, 7 388 succès sur les quatre bras — chiffre de la
campagne complète).

### 5.3 Le résultat qui compte : la parole construit l'accord et dégrade la décision

Le null de B3 n'est pas un raisonnement, c'est un run : même monde, même
politique, mêmes graines, `speaking=False`, **même code** (deux runs séparés
par une version de code ne comparent rien).

| bras | scénario | I1 muet | I1 parlant | **E_social** | porte désignée bloquée : muet → parlant |
|---|---|---|---|---|---|
| `regles` | split | 0,63 | 0,72 | **+0,09** | 0,00 → 0,24 |
| `regles` | contradiction | 0,60 | 0,69 | **+0,09** | 0,25 → 0,29 |
| `llm_petit` | split | 0,63 | 0,87 | **+0,24** | 0,00 → 0,44 |
| `llm_petit` | contradiction | 0,63 | 0,87 | **+0,24** | 0,00 → 0,44 |

Deux lectures, et elles ne vont pas dans le même sens :

1. **La parole construit de l'accord** — +0,09 à +0,24 de consensus, à
   politique identique. C'est B2 mesuré, pas raconté.
2. **La parole dégrade la décision** — les règles passent de 0,00 à 0,24 de
   décisions revenant vers la porte qu'on leur a dite fermée. Le ouï-dire
   « la sortie A est praticable », dit par ceux qui croient B fermée, érode la
   croyance de fermeture. **Une foule peut s'accorder à tort.**

### 5.4 Le modèle n'a pas d'avantage qui survive à la rumeur

C'est le résultat le plus important de la vague, et il est **négatif** pour
l'hypothèse « le modèle trie mieux l'information ».

| bras | revient vers la porte désignée bloquée (`split`) | coût |
|---|---|---|
| `regles` | 0,24 | 0 jeton, 0,3 s |
| `hybride` | 0,38 | 128 k jetons, 121 s |
| `llm_grand` | 0,31 | 340 k jetons, 315 s |
| `llm_petit` | 0,44 | 53 k jetons, 22 s |

Dans un monde **muet**, le grand modèle était à 0,00 contre 0,25 pour les
règles : il refusait l'ordre officiel qui nommait une porte qu'il croyait
bloquée. Dans un monde **parlant**, il tombe à 0,31 et coûte sept fois plus
que les règles. **Il trie le prompt, pas la rumeur.**

L'hybride ne domine pas les règles sur ce critère (0,38 contre 0,24) : ses
escalades (207 appels, `information_contradictoire` en tête) corrigent les
décisions escaladées, mais la parole crée de nouveaux fronts qui repassent
par les règles. L'escalade ciblée ne suffit pas à corriger un conflit
autorité/croyance qui dure.

---

## 6. Ce qui tient, ce qui ne tient pas

### Tient (et se rejoue sans GPU)

- le journal est la source de vérité, le rejeu ne charge aucun port de chat ;
- la perception figée, l'ordre canonique, le temps entier ;
- les contrats d'événement (`maree.event/1.1`, additif, `1.0` accepté) ;
- l'incident tracé et dénombré, le repli **nommé** (`no_response`,
  `unparseable`, `unknown_exit`, `out_of_role`) ;
- 397 tests, ruff et mypy propres ;
- le banc micro (4 agents) et la foule (60 agents) **disent la même chose**
  quand le monde est muet — et c'est la première fois qu'on peut l'affirmer.

### Ne tient pas

- « le grand modèle choisit mieux » : vrai sans parole, faux avec (0,00 →
  0,31), pour 340 k jetons par run ;
- « l'hybride est le bon compromis » : il coûte 2,7× les règles et se trompe
  **plus** qu'elles sous rumeur (0,38 contre 0,24) ;
- « le petit modèle fait aussi bien que le grand » : son 0,44 est acheté par
  le moteur, qui choisit la porte à sa place (100 % de ses cibles résolues).

### Ne peut pas être revendiqué

- **I6** (part croyant en une sortie fermée) : aucune porte ne ferme dans ces
  scénarios, il vaut 0 par construction ;
- des **temps absolus** de terrain : le débit de porte de ce modèle est
  2,4× la littérature (ADR-015) ;
- une **reproductibilité LLM** exacte : deux runs identiques ne prennent pas
  les mêmes décisions (batching). On agrège des graines, on n'apparie pas ;
- une **calibration humaine** : « ça a l'air crédible » est un jugement, pas
  une mesure.

---

## 7. Reproduire

```bash
uv sync --all-extras
uv run pytest                       # 397 tests, sans GPU

# le monde calibré et ses indicateurs (aucun modèle requis)
uv run pytest tests/v3/test_scenario_crowd.py -q
uv run pytest tests/v3/test_schedule.py -q      # porte G1, coût nul

# la campagne macro (serveurs 8081 grand + 8082 petit)
MAREE_LLM_URL=http://127.0.0.1:8081/v1 \
MAREE_LLM_SMALL_URL=http://127.0.0.1:8082/v1 \
LANGCHAIN_TRACING_V2=false \
  uv run python scripts/v3_crowd_campaign.py

# le null de B3 (même code, sans émission)
  uv run python scripts/v3_crowd_campaign.py --silent --arms=regles,llm_petit

# les tables de ce rapport, depuis le JSON
uv run python scripts/rapport_crowd.py    # → docs/v3/resultats-c6.md
```

Les JSON sources : `runs/v3/campaign_crowd.json` (parole),
`runs/v3/campaign_crowd_silence.json` (null). Les ADR : `docs/v3/decisions.md`
(014 calendrier, 015 monde calibré, 016 perception avant décision,
017 la réponse escaladée tient, 018 les agents parlent).

---

## 8. Questions ouvertes

1. **Pourquoi la rumeur érode-t-elle une croyance de fermeture ?** Le message
   positif (« praticable ») et la croyance de danger se cumulent sans
   arbitrage explicite : `exit:A` monte, `hazard:A` décroît par oubli
   (0,98/décision), et le seuil 0,5 finit par être franchi. C'est une piste
   mécanique, pas mesurée isolément.
2. **Un bras « seuls les agents de sécurité parlent »** séparerait l'effet
   « parole » de l'effet « rumeur ». Non lancé (coût : ~1 h de GPU).
3. **La connaissance reste statique** : un message ne fait pas apprendre une
   sortie inconnue (garde C3). À trancher si l'on veut une géographie
   apprise par ouï-dire.
4. **L'hybride demande une autre définition**, pas un autre réglage : garder
   la décision escaladée **et** empêcher les fronts de la défaire exigerait un
   état de plan explicite, pas un calendrier plus fin.
