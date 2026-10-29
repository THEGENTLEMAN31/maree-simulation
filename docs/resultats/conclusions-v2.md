# MARÉE v2 — conclusions de la campagne X1–X7

Campagne du 2026-10-29 : **115 runs**, 7 protocoles, 5 graines par bras
pour X1–X4 et **10 graines** pour X5–X7, population de référence
12 agents LLM + 48 à règles (X4 varie).
**6 906 appels LLM, 6 906 succès, aucun repli règles.**

Les tableaux, médianes, intervalles et tests sont dans
[`rapport-v2.md`](rapport-v2.md), généré par
`scripts/rapport_experiences.py` depuis les `runs/experiment_x*.json` et
les journaux. Ce document-ci est la **lecture** : il interprète, il ne
recalcule rien. Les comptes au niveau des décisions (qui reste piégé,
quelles sorties sont choisies, combien de `search`) viennent des
journaux, pas des agrégats.

---

## Ce qui a été corrigé avant de mesurer

Une campagne ne vaut que par ce qu'elle mesure. Six corrections ont
précédé celle-ci, chacune parce que l'indicateur ou le modèle ne faisait
pas ce qu'il annonçait :

| correction | ce qui n'allait pas |
|---|---|
| **I5 par noyau de 2 m** | la grille de 1 m valait 2,0 dans **tous** les runs : avec 0,4 m de séparation minimale, une cellule contient au plus 2 agents. Variance nulle. |
| **annonce lue par les règles** | `bool(percept.announcement)` : « Veuillez rester calmes » faisait sortir les 48 agents à règles. La clarté n'atteignait donc que 12 agents sur 60. |
| **X1 en plan 2×2** | l'ancien protocole confondait texte et délai ; l'annonce de t53 tombait **après la sortie** dans 2 runs sur 5. |
| **X4 sur scénario piège** | sans fermeture d'issue, I6 valait 0 dans les trois bras : H4 était intestable. |
| **I7 — délai signal → dernier sorti** | I4 est une horloge : il inclut l'attente avant le signal et se fige au plafond `max_ticks` dès qu'une partie de la foule ne sort pas. I7 part du premier signal de danger et s'arrête au dernier sorti ; il reste défini sous censure. |
| **fuite de connaissance** | une cible `go_exit` était validée contre le plan, pas contre les sorties connues du profil. Un visiteur pouvait nommer B — et y aller. |

**La fuite n'était pas marginale.** Comptée sur les journaux de la
campagne antérieure, elle touchait un tiers à la moitié des cibles
physiques des agents LLM :

| protocole | cibles LLM hors savoir (avant) | après correctif |
|---|---|---|
| X1 | 108 / 318 | **0 / 248** |
| X2 | 60 / 199 | **0 / 158** |
| X3 | 69 / 182 | **0 / 140** |
| X4 | **349 / 769** | **0 / 845** |
| X5 | 42 / 166 | **0 / 270** |
| X6 | 12 / 48 | **0 / 88** |
| X7 | 29 / 159 | **0 / 273** |

Les X1–X4 de la campagne du 2026-10-28 mesuraient donc un modèle
différent : ils sont conservés dans
`runs/experiment_x*_avant_correctif.json`, et **toute la campagne a été
rejouée** après le correctif. Ce n'est pas un détail de méthode : c'est
ce qui renverse H4 (voir plus bas).

---

## H1 — une annonce claire et précoce accélère l'évacuation

**Soutenue sur la clarté, pas sur l'heure de l'annonce.**

| bras | I7 (s) | I3 | runs non terminés |
|---|---|---|---|
| clair, tôt (t17) | **160 [160–160]** | 1,00 | 0/5 |
| ambigu, tôt (t17) | **260 [260–260]** | 0,98 | **4/5** |
| clair, tard (t30) | 280 [270–290] | 1,00 | 0/5 |
| ambigu, tard (t30) | 270 [270–270] | 0,98 | **3/5** |

Clarté à délai égal : p = 0,0185 (tôt). Délai à clarté égale :
p = 0,0107 (clair tôt contre clair tard) — mais l'écart vaut 120 s : le
dernier sorti recule de 12 ticks quand l'annonce recule de 13. **I7 n'efface pas
l'heure de l'annonce** : il compte depuis la fumée de t5, pas depuis
l'annonce. Ce qu'il retire, c'est le temps d'avant-signal et le plancher
de censure.

Ce que la clarté achète vraiment, c'est le **nombre de sortis** : 1,00
partout avec un ordre clair, 0,98 sans, et 7 runs censurés sur 10 dans
les bras ambigus contre 0 sur 10 dans les bras clairs. Une consigne vague
ne ralentit pas la foule : elle laisse une partie des agents à règles en
`STAY` jusqu'au plafond.

La mesure tient : l'annonce est délivrée dans **5 runs sur 5** dans les
quatre bras. Et I2 le confirme (0,47 clair contre 0,58 ambigu,
p = 0,0079) : l'ambiguïté se lit dans l'incertitude des croyances.

---

## H2 — les meneurs piègent davantage de monde

**Non soutenue, avec un signal faible dans le sens prévu.**

| bras | I6 | I3 | I7 (s) | I5 (pers/m²) |
|---|---|---|---|---|
| avec meneurs | 1,00 | 0,90 | **220 [220–220]** | 0,40 |
| sans meneurs | 1,00 | 0,92 | **150 [150–150]** | 0,48 |

p = 0,75 (I3), 0,74 (I5), **0,083 (I7)**. Quatre runs sur cinq sont
censurés dans les deux bras : la foule laisse 8 à 10 % de ses membres
derrière elle, avec ou sans agents de sécurité.

Le seul écart notable est le délai : 220 s contre 150 s, soit 7 ticks de
plus pour le dernier sorti quand des guides orientent. L'intervalle
n'est pas significatif à 5 graines et les deux bras sont censurés ; à
lire comme une piste, pas comme un résultat. Il faudrait 10 graines.

**I6 = 1,00 dans les deux bras** : au moment de la fermeture, tout le
monde croit en A — tautologie du scénario, pas un résultat. I6 saturé ne
discrimine rien.

---

## H3 — synchrone contre asynchrone

**Effet nul sur la dynamique, gain mural net** — exactement ce que le
protocole prévoyait.

| bras | I1 | I5 | I7 (s) | temps mural |
|---|---|---|---|---|
| synchrone (1 appel) | 0,96 | 0,48 | 100 | 34,0 s |
| asynchrone (4 appels) | 0,96 | 0,40 | 100 | **20,9 s** |

p = 0,84 (I1), 0,58 (I5), 0,54 (I7), **0,0117** (mural) — facteur
**1,63×**.

C'est la démonstration que la perception figée et l'ordre canonique
`agent_id` font leur travail : l'ordre d'arrivée des réponses ne
contamine pas la dynamique. Le parallélisme n'achète que du temps réel.

---

## H4 — LLM contre règles sur l'écart croyance/réalité

**Réfutée — et le résultat est l'inverse de celui publié hier.**

| bras | I3 | runs non terminés | I7 (s) | appels LLM | mural |
|---|---|---|---|---|---|
| hybride 12 LLM + 48 règles | 0,92 | 5/5 | 220 | 43 | 30,9 s |
| 60 règles | 0,92 | 4/5 | **150** | 0 | **9,6 s** |
| 60 LLM | **0,67** | 5/5 | **350** | **520** | **234,8 s** |

Le tout-LLM est le **pire** bras : 40 agents sortis sur 60 en médiane,
contre 55 pour les règles (p = 0,0117 sur I3 et sur I7). Il coûte 12× le
temps mural et 520 appels pour arriver à ce résultat.

Qui reste piégé ? **Des visiteurs, dans les trois bras** — c'est voulu,
ils ne connaissent que A et A ferme à t14. Mais le nombre varie
énormément :

| bras | visiteurs piégés par run (5 graines) |
|---|---|
| 60 règles | 0, 3, 5, 6, 8 |
| hybride | 1, 5, 5, 6, 16 |
| 60 LLM | **17, 19, 20, 20, 23** |

Les agents à règles visiteurs se rabattent sur ce qu'ils savent faire :
suivre quelqu'un, attendre, sortir par où la foule sort. Les agents LLM
visiteurs, eux, explorent (`search`), tournent, et ne sortent pas.

**Pourquoi le résultat d'hier était faux.** Dans la campagne
pré-correctif, `llm_60` sortait 60/60. Ce n'était pas la cognition : les
agents LLM visiteurs nommaient B et C — des sorties que leur profil ne
connaît pas — et y allaient. Le correctif de connaissance leur a retiré
cette possibilité, et 17 à 23 visiteurs sur 24 restent sur place. **Le
« 60/60 » était un artefact de la fuite.** C'est le résultat le plus
important de cette reprise : il contredit l'argument qui avait motivé
l'hybride. Ce n'est pas le LLM qui rattrape les règles, c'est l'inverse.

**Réserve** : I4 = 900 s dans tous les runs censurés est le plafond
`max_ticks` (90 ticks × 10 s), pas une durée. C'est précisément ce que I7 répare :
350 s contre 150 s reste lisible alors que 900 = 900 ne dit rien.

---

## H5 — la mémoire change le choix de sortie

**Soutenue sur les décisions, invisible dans les agrégats** — et l'effet
n'est pas celui qu'on croyait.

| bras | I1 | I2 | I7 | `search` | `stay` | LLM → C | LLM → B |
|---|---|---|---|---|---|---|---|
| avec mémoire | 0,96 | 0,44 | 100 | **5,0** | **143** | **2,0** | 2,0 |
| sans mémoire | 0,96 | 0,44 | 100 | **8,5** | **134** | **1,0** | 2,0 |

p = 0,68 (I1), 0,52 (I2), 0,54 (I7) — aucun agrégat ne bouge, à
10 graines. Au niveau des décisions : `search` p = 0,0015, `stay`
p = 0,0006, C p = 0,050. Avec mémoire, les agents LLM **cherchent moins,
restent plus, et vont davantage vers C**.

La campagne d'hier trouvait « B 42 contre 16 » : c'était encore la fuite.
B était la sortie que les visiteurs LLM pouvaient nommer à tort ; le
correctif la referme, et l'effet de la mémoire se reporte sur C, la
sortie que les habitués connaissent et que le RAG documente.

Leçon de méthode inchangée : pour H5, **l'indicateur est la distribution
des décisions**, pas la moyenne de la foule. Douze agents sur soixante
ne déplacent aucun agrégat.

---

## H6 — le profil change la décision

**Soutenue, et maintenant propre.**

| bras | I1 | I3 | I7 (s) | LLM → A * | LLM → B * | règles → B * |
|---|---|---|---|---|---|---|
| visiteurs seuls | **1,00** | 1,00 | **90** | 40 | **0** | 0 |
| habitués seuls | 0,93 | 1,00 | 100 | 31 | 13 | 66 |

\* total des décisions `go_exit` sur les 10 runs.

p = 0,0001 (I1), **0,0252** (I7), constante (I3). Un visiteur ne
connaît que A et ne choisit que A — côté LLM **comme** côté règles, ce
qui n'était pas le cas hier (12 décisions LLM vers B). Le savoir définit
l'ensemble des sorties atteignables, et il le fait **plus vite** : 90 s
contre 100 s, parce qu'il n'y a rien à arbitrer.

L'ancienne réserve (« fuite constatée ») est levée : 0 cible hors savoir
sur 88 dans ce protocole.

---

## H7 — le RAG change la croyance

**Soutenue à 10 graines, sur la cognition et sur la foule.**

| bras | I2 | I1 | I3 | I7 (s) | `search` | LLM → B | LLM → C |
|---|---|---|---|---|---|---|---|
| avec RAG | **0,44** | 0,96 | 1,00 | **100 [100–100]** | **4,0** | 1,5 | 2,0 |
| sans RAG | **0,54** | 0,96 | 1,00 (3/10 censurés) | **150 [102–160]** | **21,5** | 0,0 | 1,0 |

p = 0,0008 (I2), 0,43 (I1), 0,0776 (I3), **0,016 (I7)**. Au niveau des
décisions : `search` p = 0,0002, `stay` p = 0,0045, total des décisions
LLM 44 contre 49,5 (p = 0,0005), B p = 0,038, C p = 0,023.

Sans RAG, les agents LLM **errent cinq fois plus** (21,5 recherches par
run contre 4,0), prennent plus de décisions, et la foule met 50 s de
plus à finir — 3 runs sur 10 sont même censurés à 720 s. Le RAG ne se
contente pas de changer ce que les agents croient : il change le temps
que met la foule.

C'est l'hypothèse que la campagne d'hier laissait ouverte faute de
puissance. À 10 graines, elle est tranchée.

---

## Ce que la campagne ne mesure pas

1. **I7 mesure un délai, pas une cause.** Il part du premier signal —
   dans X1, la fumée de t5 — donc l'heure de l'annonce reste dans le
   chiffre. Un protocole qui voudrait isoler la réaction à l'annonce
   devrait compter depuis l'annonce, pas depuis le premier danger.
2. **« Dernier sorti » n'est pas « dernier piégé ».** En X4 hybride, le
   dernier sorti est un agent LLM dans 4 runs sur 5, alors que les
   piégés sont tous des visiteurs. Les deux mesures disent des choses
   différentes ; ne pas lire l'une pour l'autre.
3. **La connaissance est statique.** Un message qui dit « la sortie B
   est libre » ne fait pas entrer B dans le savoir d'un visiteur : la
   garde s'appuie sur `Profile.knows`, comme `_known_open` pour les
   règles. C'est le modèle existant, pas une conséquence du correctif —
   mais c'est une limite : un agent ne peut pas apprendre la géographie
   par ouï-dire.
4. **I5 ne dépasse jamais ~0,6 pers/m².** La foule n'est jamais dense :
   le goulot de ce scénario est le **savoir**, pas l'encombrement. Un
   noyau de 2 m suffit, mais il ne faudra pas conclure « pas de
   bouchon » d'un indicateur qui plafonne à 0,6.
5. **I6 n'est vivant que dans le piège** (X2, X4), et il sature à 1,00
   au moment de la fermeture. Il mesure l'instant, pas la récupération.
6. **Reproductibilité** : deux runs de même configuration donnent les
   mêmes comptes, pas les mêmes décisions (batching concurrent). D'où
   l'agrégation par graines — jamais de comparaison appariée.
7. **Puissance** : X1–X4 restent à 5 graines. Les p-values exactes à
   5 contre 5 valent 0,0079 au mieux ; X2 (p = 0,083) et X4 hybride
   contre règles (p = 0,12) ne sont pas tranchés.

---

## Ce qu'il faut faire ensuite

1. **X4 : comprendre l'écart visiteurs.** Pourquoi les agents LLM
   visiteurs restent-ils 20 sur 24 quand les agents à règles n'en
   laissent que 0 à 8 ? La réponse est dans les journaux (déclencheurs,
   `search`, messages reçus) et vaut plus que le chiffre de I3.
2. **X2 à 10 graines.** L'écart I7 (220 contre 150 s) va dans le sens de
   H2 et n'est pas significatif à 5 graines.
3. **Trancher la connaissance apprise.** Faut-il qu'un message puisse
   ajouter une sortie au savoir d'un agent ? Si oui, la garde doit
   interroger les croyances, pas seulement le profil.
4. **Ne pas réintroduire I4 comme mesure de durée.** Il reste utile pour
   dater, pas pour comparer. Tout protocole qui parle de « délai » doit
   déclarer I7 et publier I3 à côté.
