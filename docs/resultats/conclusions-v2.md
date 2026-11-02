# MARÉE v2 — conclusions de la campagne X1–X14

> **Lecture par hypothèse.** La synthèse demandée par le cahier des
> charges (partie technique, mini-article, bilan de sobriété, réponses
> Q1–Q6) est dans `rapport-hybride.md`. Ce document-ci reste la lecture
> détaillée des sept hypothèses préenregistrées.

Campagne du **2026-11-01** : **260 runs**, 16 protocoles, 5 graines par bras
pour X1, X3, X3K, X3M, X4, X8–X13 et **10 graines** pour X2, X5, X6, X7 et
X14 ; population de référence 12 agents LLM + 48 à règles (X4 varie).
**14 181 appels LLM, 14 181 succès, aucun repli règles.**

Les tableaux, médianes, intervalles et tests sont dans
[`rapport-v2.md`](rapport-v2.md), généré par
`scripts/rapport_experiences.py` depuis les `runs/experiment_x*.json` et
les journaux. Ce document-ci est la **lecture** : il interprète, il ne
recalcule rien. Les comptes au niveau des décisions (qui reste piégé,
quelles sorties sont choisies, combien de `search`) viennent des
journaux, pas des agrégats.

---

## Ce qui a été corrigé avant de mesurer

Une campagne ne vaut que par ce qu'elle mesure. Sept corrections ont
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
| **collections du RAG** | le plan de signalétique s'appelait `plan_signaletique` dans un corpus accentué (44 passages invisibles), et le profil `visiteur` déclarait une collection où **aucun** passage ne l'autorisait : zéro récupération à vie. |

**La fuite n'était pas marginale.** Comptée sur les journaux de la
campagne antérieure, elle touchait un tiers à la moitié des cibles
physiques des agents LLM (X4 : 349 décisions sur 769). Depuis le
correctif, toute cible est validée contre `Profile.knows` et un échec
replie sur les règles en le journalisant (`unknown_exit`, `out_of_role`) :
aucune cible hors savoir n'est appliquée.

**La campagne entière a été rejouée deux fois** — après le correctif de
connaissance, puis après celui des collections RAG (2026-11-01). Les
résultats d'avant sont conservés (`runs/experiment_x*_avant_correctif.json`,
`runs/avant_correctif_rag/`) et **ne sont pas publiés** : deux runs
séparés par une version de code ne comparent rien. C'est ce qui renverse
H7 (voir plus bas) et affaiblit H1.

---

## H1 — une annonce claire et précoce accélère l'évacuation

**Soutenue sur la clarté (le nombre de sortis), non soutenue sur l'heure.**

| bras | I7 (s) | I3 | I2 | runs non terminés |
|---|---|---|---|---|
| clair, tôt (t17) | 380 [380–390] | **1,00** | 0,57 | 1/5 |
| ambigu, tôt (t17) | 370 [260–440] | 0,95 | 0,56 | **5/5** |
| clair, tard (t30) | 280 [280–290] | **1,00** | 0,51 | 1/5 |
| ambigu, tard (t30) | 440 [270–560] | 0,95 | 0,54 | **5/5** |

Clarté à délai égal : le **délai** ne bouge pas (380 contre 370 s,
p = 0,67) et l'**entropie** non plus (0,57 contre 0,56, p = 0,55). Ce que
la clarté achète, c'est le **nombre de sortis** : I3 1,00 contre 0,95
(p = 0,0095), et **10 runs censurés sur 10** dans les bras ambigus contre
2 sur 10 dans les bras clairs. Une consigne vague ne ralentit pas la
foule : elle laisse une partie des agents en `STAY` jusqu'au plafond.

Sur l'heure, l'effet va dans le sens **inverse** : l'annonce claire et
tardive sort en 280 s, l'annonce claire et précoce en 380 s (p = 0,0097).
Ce n'est pas la foule, c'est **un agent** : dans les cinq runs
`clair_tot`, le dernier sorti est A57 (vendeur, petit modèle), qui répond
`RESTER` à la fumée de t5, à l'annonce de t17 et à chaque rappel, puis
obéit au rappel de t41. Dans `clair_tard`, la même annonce tombe à t30 et
il obéit aussitôt (dernière sortie t33, dernier sorti à règles dans 4
runs sur 5). C'est la limite déjà consignée du petit modèle sur les
annonces (2/6), pas un effet de l'heure.

L'ancien chiffre (160 s contre 260 s) mesurait un autre protocole de
modèles : il n'était pas faux, il ne parlait pas de la même chose.

---

## H2 — les meneurs piègent davantage de monde

**Non soutenue : l'écart de délai a disparu à 10 graines.**

| bras | I6 | I3 | I7 (s) | I5 (pers/m²) |
|---|---|---|---|---|
| avec meneurs | 1,00 | 0,90 | **265 [250–270]** | 0,48 |
| sans meneurs | 1,00 | 0,89 | **265 [250–270]** | 0,56 |

p = 0,62 (I3), **0,91 (I7)**, **0,058 (I5)**. Les 20 runs sont censurés :
la foule laisse 10 à 11 % de ses membres derrière elle, avec ou sans
guides. L'écart de 70 s observé à 5 graines (220 contre 150 s) n'existe
plus. La densité est plus haute **sans** meneurs — l'inverse du mécanisme
attendu — et frôle le seuil sans l'atteindre : à lire comme une piste
négative, pas comme un résultat.

**I6 = 1,00 dans les deux bras** : au moment de la fermeture, tout le
monde croit en A — tautologie du scénario, pas un résultat.

---

## H3 — synchrone contre asynchrone

**Effet nul sur la dynamique ; le gain mural est là, mais 5 graines ne
suffisent pas à le trancher.**

| bras | I1 | I5 | I7 (s) | temps mural |
|---|---|---|---|---|
| synchrone | 0,98 | 0,40 | 220 | 18,1 s |
| asynchrone | 0,97 | 0,40 | 220 | **14,1 s** |

p = 0,84 (I1), 0,82 (I5), 0,82 (I7). C'est la démonstration que la
perception figée et l'ordre canonique `agent_id` font leur travail :
l'ordre d'arrivée des réponses ne contamine pas la dynamique.

Le temps mural baisse sur **les cinq paires de graines** (17,8→14,9 ;
18,1→13,0 ; 21,1→14,1 ; 27,4→25,3 ; 16,6→14,0), médiane 18,1 → 14,1 s
(×1,28). À cinq paires, un test apparié ne peut pas descendre sous
p = 0,0625 : on constate l'effet 5 fois sur 5 sans pouvoir le trancher.

En mode réellement asynchrone (X11), la latence devient un fait du monde
mais reste petite : I7 220 → 230 s (p = 0,041), `lag_ticks_median` 0 → 4,
6 au maximum.

---

## H4 — LLM contre règles sur l'écart croyance/réalité

**Réfutée — et le résultat est l'inverse de celui publié avant le
correctif de connaissance.**

| bras | I3 | runs non terminés | I7 (s) | appels LLM | mural |
|---|---|---|---|---|---|
| hybride 12 LLM + 48 règles | 0,88 | 5/5 | 270 | 78 | 24,7 s |
| 60 règles | 0,92 | 4/5 | **150** | 0 | **11,1 s** |
| 60 LLM | **0,70** | 5/5 | **440** | **477** | **89,5 s** |

Le tout-LLM est le **pire** bras : 42 agents sortis sur 60 en médiane,
contre 55 pour les règles (p = 0,008 sur I3, 0,011 sur I7). Il coûte 8×
le temps mural et 477 appels pour arriver à ce résultat.

Qui reste piégé ? Des **visiteurs** — c'est voulu, ils ne connaissent que
A et A ferme à t14 — mais le nombre varie énormément, et le correctif RAG
a changé la composition :

| bras | visiteurs piégés par run (5 graines) | habitués piégés |
|---|---|---|
| 60 règles | 6, 5, 0, 8, 3 | 0, 0, 0, 0, 0 |
| hybride | 11, 7, 2, 8, 5 | 0, 0, 0, 1, 0 |
| 60 LLM | **14, 16, 9, 19, 12** | 7, 2, 1, 3, 5 |

Les agents à règles visiteurs se rabattent sur ce qu'ils savent faire :
suivre quelqu'un, attendre, sortir par où la foule sort. Les agents LLM
visiteurs, eux, explorent (`search`), tournent, et ne sortent pas.

**Pourquoi le résultat d'avant le correctif était faux.** Dans la
campagne pré-correctif, `llm_60` sortait 60/60. Ce n'était pas la
cognition : les agents LLM visiteurs nommaient B et C — des sorties que
leur profil ne connaît pas — et y allaient. Le correctif de connaissance
leur a retiré cette possibilité, et 9 à 19 visiteurs sur 24 restent sur
place. **Le « 60/60 » était un artefact de la fuite.** C'est le résultat
le plus important de cette reprise : il contredit l'argument qui avait
motivé l'hybride. Ce n'est pas le LLM qui rattrape les règles, c'est
l'inverse.

**Réserve** : I4 = 900 s dans tous les runs censurés est le plafond
`max_ticks` (90 ticks × 10 s), pas une durée. C'est précisément ce que I7
répare : 440 s contre 150 s reste lisible alors que 900 = 900 ne dit rien.

---

## H5 — la mémoire change le choix de sortie

**Soutenue sur les décisions et sur l'incertitude, pas sur l'errance.**

| bras | I1 | I2 | I7 | `search` | `stay` | `guide` |
|---|---|---|---|---|---|---|
| avec mémoire | 0,98 | **0,52** | 220 | 5,0 | **29,0** | **1,0** |
| sans mémoire | 0,98 | **0,50** | 220 | 5,5 | **24,5** | **2,0** |

I2 diffère (p = 0,0073), et au niveau des décisions `stay` (p = 0,0087) et
`guide` (p = 0,0050) aussi. `search` (p = 0,56) et le choix de sortie
(C : p = 0,33) ne bougent pas. Avec mémoire, les agents LLM **restent
davantage et guident moins** — la préhistoire de J−3 donne de quoi
hésiter, pas de quoi mieux se diriger.

La campagne d'hier trouvait « B 42 contre 16 » — c'était encore la fuite :
B était la sortie que les visiteurs LLM pouvaient nommer à tort. Après le
correctif de connaissance, l'effet s'était reporté sur C ; après celui des
collections RAG, **ni B ni C ne diffèrent** (5 contre 7 et 3 contre 6 sur
les 10 runs, p ≥ 0,33). Ce qui reste de la mémoire, c'est le fait de
rester.

Leçon de méthode inchangée : pour H5, **l'indicateur est la distribution
des décisions**, pas la moyenne de la foule. Douze agents sur soixante ne
déplacent qu'un agrégat, et de peu.

---

## H6 — le profil change la décision

**Soutenue, et propre.**

| bras | I1 | I3 | I7 (s) | LLM → A * | LLM → B * | règles → B * |
|---|---|---|---|---|---|---|
| visiteurs seuls | **1,00** | 1,00 | **90** | 40 | **0** | 0 |
| habitués seuls | 0,94 | 1,00 | 100 | 27 | 14 | 67 |

\* total des décisions `go_exit` sur les 10 runs.

p = 0,0001 (I1), **0,0021** (I7), constante (I3). Un visiteur ne connaît
que A et ne choisit que A — côté LLM **comme** côté règles, ce qui
n'était pas le cas avant le correctif (12 décisions LLM vers B). Le
savoir définit l'ensemble des sorties atteignables, et il le fait **plus
vite** : 90 s contre 100 s, parce qu'il n'y a rien à arbitrer.

L'ancienne réserve (« fuite constatée ») est levée : la garde est dans le
code et aucun repli hors savoir n'est appliqué dans la campagne rejouée.

---

## H7 — le RAG change la croyance

**Soutenue sur la cognition, non soutenue sur les agrégats.**

| bras | I2 | I1 | I3 | I7 (s) | `search` | décisions LLM |
|---|---|---|---|---|---|---|
| avec RAG | 0,53 | 0,98 | 1,00 | 220 | **5,0** | 46,0 |
| sans RAG | 0,54 | 0,98 | 1,00 | 220 | **9,5** | 49,5 |

`search` divise par deux (p = 0,0002) et le total des décisions baisse
(46,0 contre 49,5, p = 0,062 — direction nette, seuil non atteint) : sans
RAG, les agents LLM errent deux fois plus. Mais ni
l'entropie (p = 0,47) ni le délai (p = 0,83) ni l'évacuation (I3 1,00 des
deux côtés, 1 run censuré de chaque côté) ne bougent.

C'était l'inverse avant le correctif des collections (I2 0,44 contre
0,54, I7 100 contre 150 s). Depuis que le visiteur lit les annonces et
que les habitués lisent le plan, le RAG nourrit des sources qui se
contredisent (Q5), et l'écart d'entropie entre les deux bras disparaît.
Le RAG change **ce que font** les agents ; il ne change plus **ce que met
la foule à sortir**.

---

## Ce que la campagne ne mesure pas

1. **I7 mesure un délai, pas une cause.** Il part du premier signal —
   dans X1, la fumée de t5 — donc l'heure de l'annonce reste dans le
   chiffre. Un protocole qui voudrait isoler la réaction à l'annonce
   devrait compter depuis l'annonce, pas depuis le premier danger.
2. **« Dernier sorti » n'est pas « dernier piégé ».** En X4 hybride, le
   dernier sorti est un agent LLM dans 5 runs sur 5, alors que les piégés
   sont des visiteurs (moins un habitué dans un run sur cinq).
3. **La connaissance est statique.** Un message qui dit « la sortie B
   est libre » ne fait pas entrer B dans le savoir d'un visiteur : la
   garde s'appuie sur `Profile.knows`, comme `_known_open` pour les
   règles. Un agent ne peut pas apprendre la géographie par ouï-dire.
4. **I5 reste bas dans la population de référence** (0,32 à 0,56 pers/m²),
   et ne monte qu'à **1,51** dans le seul bras où une foule piégée
   s'accumule (60 LLM en X4). Le goulot de ce scénario est le **savoir**,
   pas l'encombrement : il ne faudra pas conclure « pas de bouchon » d'un
   indicateur qui plafonne à 1,5.
5. **I6 n'est vivant que dans le piège** (X2, X4), et il sature à 1,00
   au moment de la fermeture. Il mesure l'instant, pas la récupération.
6. **Reproductibilité** : deux runs de même configuration donnent les
   mêmes comptes, pas les mêmes décisions (batching concurrent). D'où
   l'agrégation par graines — jamais de comparaison appariée, sauf pour
   un coût mesuré sur le même monde (X3K/X3M, où l'appariement est
   explicite).
7. **Puissance** : X1 et X3–X4 restent à 5 graines. Les p-values exactes
   à 5 contre 5 valent 0,0079 au mieux ; le temps mural de X3 (p = 0,095)
   et I3 de X4 hybride contre règles (p = 0,35) ne sont pas tranchés.

---

## Ce qu'il faut faire ensuite

1. **X4 : comprendre l'écart visiteurs.** Pourquoi les agents LLM
   visiteurs restent 9 à 19 sur 24 quand les agents à règles n'en
   laissent que 0 à 8 ? La réponse est dans les journaux (déclencheurs,
   `search`, messages reçus) et vaut plus que le chiffre de I3.
2. **Les habitués piégés en tout-LLM** (1 à 7 par run) n'existaient pas
   dans la campagne précédente : à expliquer, pas à ignorer.
3. **Trancher la connaissance apprise.** Faut-il qu'un message puisse
   ajouter une sortie au savoir d'un agent ? Si oui, la garde doit
   interroger les croyances, pas seulement le profil.
4. **Ne pas réintroduire I4 comme mesure de durée.** Il reste utile pour
   dater, pas pour comparer. Tout protocole qui parle de « délai » doit
   déclarer I7 et publier I3 à côté.
