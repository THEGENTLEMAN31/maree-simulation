# MARÉE v2 — conclusions de la campagne X1–X7

Campagne du 2026-10-28 : **85 runs**, 7 protocoles, 5 graines par bras,
population de référence 12 agents LLM + 48 à règles (X4 varie).
**4 216 appels LLM, 4 216 succès, aucun repli règles.**

Les tableaux, médianes, intervalles et tests sont dans
[`rapport-v2.md`](rapport-v2.md), généré par
`scripts/rapport_experiences.py` depuis les `runs/experiment_x*.json` et
les journaux. Ce document-ci est la **lecture** : il interprète, il ne
recalcule rien.

---

## Ce qui a été corrigé avant de mesurer

Une campagne ne vaut que par ce qu'elle mesure. Quatre corrections ont
précédé celle-ci, chacune parce que l'indicateur ne mesurait pas ce
qu'il annonçait :

| correction | ce qui n'allait pas |
|---|---|
| **I5 par noyau de 2 m** | la grille de 1 m valait 2,0 dans **tous** les runs : avec 0,4 m de séparation minimale, une cellule contient au plus 2 agents. Variance nulle. |
| **annonce lue par les règles** | `bool(percept.announcement)` : « Veuillez rester calmes » faisait sortir les 48 agents à règles. La clarté n'atteignait donc que 12 agents sur 60. |
| **X1 en plan 2×2** | l'ancien protocole confondait texte et délai ; l'annonce de t53 tombait **après la sortie** dans 2 runs sur 5. |
| **X4 sur scénario piège** | sans fermeture d'issue, I6 valait 0 dans les trois bras : H4 était intestable. |

Les résultats ci-dessous sont ceux du modèle corrigé. L'ancien X1
(10 runs, deux bras confondus) est conservé dans
`runs/experiment_x1_avant_recalibrage.json` : il montrait 190 s dans les
deux bras, c'est-à-dire rien.

---

## H1 — une annonce claire et précoce accélère l'évacuation

**Soutenue**, avec une réserve de mesure.

| bras | I4 (s) | runs non terminés |
|---|---|---|
| clair, tôt (t17) | 200 [200–210] | 0/5 |
| ambigu, tôt (t17) | 720 [380–720] | 3/5 |
| clair, tard (t30) | 320 [320–330] | 0/5 |
| ambigu, tard (t30) | 430 [390–720] | 2/5 |

Clarté : p = 0,0099 (tôt), p = 0,0107 (tard). Délai : p = 0,0107.
L'annonce est délivrée dans **5 runs sur 5** dans les quatre bras : le
protocole mesure bien ce qu'il croit mesurer.

Le mécanisme est lisible dans les journaux : le déclencheur `annonce`
tire 87 fois dans les deux bras, mais une consigne vague laisse les
agents à règles en `STAY` (742 décisions contre 515). **Ce n'est pas une
évacuation plus lente, c'est une évacuation qui n'a pas lieu pour une
partie de la foule** — d'où la censure à 720 s.

Deux réserves, à écrire noir sur blanc :

1. **I4 est censuré** dans les bras ambigus. La mesure honnête est I3 :
   1,00 partout avec un ordre clair, 0,73 à 1,00 sans.
2. **I4 mesure surtout l'heure du signal.** clair_tôt = annonce à t17,
   dernier sorti à t20. clair_tard = annonce à t30, dernier sorti à t32.
   L'évacuation elle-même dure 2 à 3 ticks. Comparer 200 s et 320 s,
   c'est comparer deux heures d'annonce, pas deux dynamiques de foule.
   La mesure correcte est **délai entre le signal et le dernier sorti**.

---

## H2 — les meneurs piègent davantage de monde

**Non soutenue.**

| bras | I6 | I3 | I5 (pers/m²) |
|---|---|---|---|
| avec meneurs | 1,00 | 0,92 | 0,40 |
| sans meneurs | 1,00 | 0,93 | 0,48 |

p = 0,11 (I3), 0,74 (I5). Quatre runs sur cinq sont censurés dans les
deux bras : la foule laisse 7 à 8 % de ses membres derrière elle, avec
ou sans agents de sécurité.

**I6 = 1,00 dans les deux bras** : au moment de la fermeture, tout le
monde croit en A — c'est une tautologie du scénario, pas un résultat.
I6 saturé ne discrimine rien ; la vraie mesure est I3, et elle est
plate.

---

## H3 — synchrone contre asynchrone

**Effet nul sur la dynamique, gain mural net** — exactement ce que le
protocole prévoyait.

| bras | I1 | I5 | temps mural |
|---|---|---|---|
| synchrone (1 appel) | 0,94 | 0,48 | 35,5 s |
| asynchrone (4 appels) | 0,94 | 0,48 | 23,1 s |

p = 0,69 (I1), 0,82 (I5), **0,0079** (mural) — facteur **1,54×**.

C'est la démonstration que la perception figée et l'ordre canonique
`agent_id` font leur travail : l'ordre d'arrivée des réponses ne
contamine pas la dynamique. Le parallélisme n'achète que du temps réel.

---

## H4 — LLM contre règles sur l'écart croyance/réalité

**Soutenue, et plus fort que prévu.**

| bras | I3 | runs non terminés | appels LLM | mural |
|---|---|---|---|---|
| hybride 12 LLM + 48 règles | 0,92 | **4/5** | 50 | 32,7 s |
| 60 règles | 0,92 | **4/5** | 0 | 9,7 s |
| 60 LLM | **1,00** | **0/5** | 240 | 111,2 s |

Le résultat central de la campagne : **tous les agents restés piégés
sont des agents à règles.** 30 dans l'hybride, 22 dans le tout-règles,
**0** dans le tout-LLM (vérifié agent par agent dans les journaux).

Après la fermeture de A à t14, les agents LLM cherchent (`search` 258
fois, `go_zone` 85) et se rabattent sur B (316 décisions) ; les agents
à règles restent sur le couple A/C de leur fonction de coût. I6 le
confirme : 0,79 en tout-LLM contre 1,00 ailleurs (p = 0,0254).

Le prix est mesuré, pas supposé : **×4,8 d'appels et ×3,4 de temps
mural** pour 60 agents LLM. C'est ce qui justifie l'hybride — mais
l'hybride hérite du défaut des règles, puisqu'il en compte 48.

**Réserve** : I4 = 900 s dans les deux premiers bras est le plafond
`max_ticks` (90 ticks × 10 s), pas une durée. Ces runs sont censurés ;
la seule mesure valide est I3.

---

## H5 — la mémoire change le choix de sortie

**Soutenue sur les décisions, invisible dans les agrégats.**

| bras | I1 | I2 | I4 | choix des LLM |
|---|---|---|---|---|
| avec mémoire | 0,94 | 0,47 | 200 | A 43, **B 42**, C 6 |
| sans mémoire | 0,95 | 0,44 | 200 | A 51, **B 16**, C 6 |

Aucun agrégat ne bouge (p = 0,31 ; 0,056 ; 0,18), mais les agents LLM
doublent presque leurs départs vers B quand la mémoire est active
(42 contre 16). L'effet est réel et localisé : il porte sur 12 agents
sur 60, donc il se noie dans I1 et I4.

Leçon de méthode : pour H5, **l'indicateur est la distribution des
décisions**, pas la moyenne de la foule.

---

## H6 — le profil change la décision

**Soutenue sur le choix de sortie.**

| bras | I1 | choix des agents à règles |
|---|---|---|
| visiteurs seuls | 0,99 | A 80 — rien d'autre |
| habitués seuls | 0,96 | A 51, B 22, C 12 |

p = 0,0317 sur I1, mais c'est le tableau de droite qui porte la
conclusion : **un visiteur ne connaît que A, et ne choisit que A**. Le
savoir définit l'ensemble des sorties atteignables, pas la vitesse
(I4 = 200 s dans les deux bras).

**Fuite constatée** : les agents LLM visiteurs ont choisi B 12 fois.
La cible d'une intention est validée contre le plan, pas contre la
connaissance de l'agent. Un visiteur peut donc nommer une sortie qu'il
ignore. Les agents à règles, eux, passent par `_known_open` et ne le
peuvent pas. À corriger : valider la cible contre les sorties connues du
profil.

---

## H7 — le RAG change la croyance

**Le mécanisme est net, l'effet de foule n'est pas établi.**

| bras | I4 | I1 | I2 | `search` des LLM | B choisi |
|---|---|---|---|---|---|
| avec RAG | 200 [200–210] | 0,93 | 0,47 | 37 | 33 |
| sans RAG | 320 [210–370] | 0,96 | 0,53 | **106** | 3 |

p = 0,10 (I4), 0,22 (I2), **0,0079** (I1) — mais l'écart de I1 est de
0,03, une taille d'effet minuscule.

Sans RAG, les agents LLM **errent trois fois plus** (106 recherches
contre 37) et se rabattent presque uniquement sur A. Avec RAG, ils
retrouvent la consigne et diversifient. Un run sans RAG sur cinq est
même censuré à 720 s.

Verdict : le RAG agit sur la cognition des agents LLM, pas encore de
façon démontrable sur la durée de la foule à 5 graines. **À refaire à
10 graines** avant de conclure.

---

## Ce que la campagne ne mesure pas

1. **I4 n'est pas une durée d'évacuation.** Il est dominé par l'heure du
   signal (X1) et censuré à `max_ticks` dès qu'une partie de la foule ne
   sort pas (X1 ambigu, X2, X4). Il faut soit une mesure « signal →
   dernier sorti », soit un modèle de survie avec censure.
2. **« Dernier sorti » n'est pas « dernier piégé ».** En X1, le dernier
   sorti est un agent à règles dans **19 runs sur 20**. En X4 hybride,
   c'est au contraire un agent LLM dans 5 runs sur 5 — parce que les 12
   agents LLM explorent avant de sortir — alors que **ce sont les 48
   agents à règles qui ne sortent jamais**. Les deux mesures disent des
   choses différentes ; ne pas lire l'une pour l'autre.
3. **I5 ne dépasse jamais ~0,6 pers/m².** La foule n'est jamais dense :
   le goulot de ce scénario est le **savoir**, pas l'encombrement. Un
   noyau de 2 m suffit, mais il ne faudra pas conclure « pas de
   bouchon » d'un indicateur qui plafonne à 0,6.
4. **I6 n'est vivant que dans le piège** (X2, X4), et il sature à 1,00
   au moment de la fermeture. Il mesure l'instant, pas la récupération.
5. **Reproductibilité** : deux runs de même configuration donnent les
   mêmes comptes, pas les mêmes décisions (batching concurrent). D'où
   l'agrégation par graines — jamais de comparaison appariée.
6. **n = 5.** Les effets de taille modeste (X7, X5) ne sont pas
   tranchés. Les p-values exactes à 5 contre 5 valent 0,0079 au mieux :
   un p = 0,10 n'est pas une absence d'effet, c'est une absence de
   puissance.

---

## Ce qu'il faut faire ensuite

1. **Remplacer I4** par « délai entre le signal et le dernier sorti »,
   et publier I3 à côté de chaque I4.
2. **Corriger la fuite de connaissance** : une cible `go_exit` doit être
   une sortie connue du profil, pas seulement une sortie du plan.
3. **Refaire X5, X6 et X7 à 10 graines** : ce sont les trois protocoles
   dont l'effet passe par les décisions de 12 agents sur 60.
4. **X4 : garder le résultat tel quel.** « Le tout-LLM est le seul bras
   qui évacue 60/60 » est le résultat le plus fort de la campagne, et il
   est contraire à l'intuition de coût qui a motivé l'hybride.
5. **Documenter le coût** : 240 appels et 111 s pour 60 agents LLM
   contre 50 appels et 33 s pour l'hybride — c'est le chiffre qui rend
   l'hybride défendable, pas l'inverse.
