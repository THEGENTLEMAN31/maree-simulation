# Ce qu'un modèle de langage apporte à une décision de foule — et ce qu'il coûte

_Brouillon d'article, non publié. 2026-11-22. Toutes les valeurs sont
rejouables par une commande du dépôt (`make v3-…`) ; les campagnes sont
pré-enregistrées dans `docs/v3/preregistrements.md`._

---

## Résumé

Nous mesurons ce qu'un modèle de langage apporte à la décision d'un agent
dans une simulation d'évacuation de foule (60 agents, physique JuPedSim,
monde calibré). Trois familles de décideurs sont comparées à perception,
physique et journal identiques : une politique déterministe, un générateur de
texte (2 B, local) et un classifieur de décision « System 1 » (4 B, local).
Quatre résultats :

1. **La mémoire personnelle suffit à faire diverger** deux agents de même
   archétype (accord 0,00 contre 1,00 sans mémoire), et la divergence survit
   à la foule ;
2. **l'accord d'une foule se construit par rumeur, pas par autorité** : quatre
   agents de sécurité qui parlent ne changent presque rien, le ouï-dire de
   tout un chacun remonte le consensus — et dégrade les décisions ;
3. **la nature du modèle compte plus que sa taille** : sur le même monde, un
   générateur de texte divise par deux les décisions vers une porte crue
   bloquée (0,41 → 0,20) pour 337 k jetons, un classifieur de décision les
   divise par dix (0,41 → 0,03) pour 100 k ;
4. **un démenti tardif n'est pas ignoré, il n'atteint plus personne** : toutes
   les personnes encore présentes changent d'action sans délai ; ce qui limite
   l'effet, c'est l'audience, pas l'engagement.

---

## 1. Question et cadre

Deux questions distinctes, souvent confondues :

- **Q1 (comportement)** : deux agents du même archétype, même traits, même
  plan connu, divergent-ils parce que leur **mémoire** diffère ?
- **Q2 (outil)** : un modèle de langage améliore-t-il la **décision** d'un
  agent, et à quel coût ?

Le cadre impose trois choses : perception **figée** (tous perçoivent le même
instant), temps **entier** (aucune horloge système dans la logique du monde),
et **journal** comme source de vérité (rien n'existe s'il n'est pas écrit).

---

## 2. Dispositif

**Monde.** Une salle de 22 × 16 m, deux issues de 1,2 m, 60 agents. Ce monde
est **calibré** : le bras témoin y produit un pic de densité de 1,1–1,5
personne/m² et une évacuation complète en 22–26 s de temps simulé. Un grand
hall (120 × 80 m) donne 0,000 pers/m² à 60 agents : il ne contraint rien, donc
il ne mesure rien.

**Bras.** `regles` (déterministe, zéro appel), `llm_grand` (Gemma 4 E2B,
local, GPU), `llm_petit` (Qwen3 0.6B, local), `hybride` (règles + escalade sur
critères du monde), `decision_head` (Kev-4B, classifieur System 1, options
fermées).

**Scénarios.** `split` : la moitié apprend « A est bloquée », l'autre « B est
bloquée », les deux portes restent **physiquement ouvertes**. `contradiction`
: mêmes croyances, plus une annonce officielle qui nomme A.

**Mesure.** Par **décision**, pas par agent : part des décisions dont la cible
était **crue bloquée au moment de décider**, appels tentés/réussis, jetons,
temps mural, I1–I7 (densité en noyau de 2 m, délai depuis le premier danger du
monde). Les nulls sont **exécutés**, pas postulés.

---

## 3. Résultats

### 3.1 La mémoire fait diverger, et la foule ne l'efface pas

Jumeaux appariés, mémoires opposées (« A bloquée » / « B bloquée »), 200
paires : accord **0,00**, KL 20,7 (100 % B contre 100 % A). Mémoire coupée :
accord **1,00**, KL 0. En foule (60 agents, 5 graines), **1,00** des agents
n'utilisent pas la porte qu'ils croient bloquée, contre **0,00** sans mémoire.
La mémoire J−3 (faits datés en ticks négatifs) est amorcée et écrit des
croyances sourcées, pas seulement des récits.

### 3.2 Un démenti tardif n'est pas ignoré — il n'atteint plus personne

60 agents, fumée à t1, démenti (« la sortie A est bloquée ») à t ou jamais :

| démenti | présents | changent d'action | part | délai | sortie par A | I7 |
|---|---|---|---|---|---|---|
| aucun | — | — | — | — | 60 | 24 s |
| t2 | 60 | 60 | 1,00 | 0 | 0 | 26 s |
| t4 | 53 | 53 | 1,00 | 0 | 7 | 30 s |
| t6 | 42 | 42 | 1,00 | 0 | 18 | 36 s |
| t8 | 29 | 29 | 1,00 | 0 | 31 | 38 s |

**Toutes** les personnes atteintes changent d'action, sans délai. Ce qui limite
un démenti tardif est le nombre de gens déjà sortis. L'hypothèse « le démenti
corrige la croyance, pas l'action engagée » est **falsifiée** dans ce modèle.

### 3.3 Une fermeture d'issue se perçoit localement, et se mesure

Fermeture de A à t4 : I6 (part des agents préférant encore une porte
réellement fermée) monte à **0,43** puis retombe à **0,04** quand la foule
s'approche ; 53 décisions se rabattent sur B ; 60/60 sortent ; le goulot se
resserre (I5 1,75) et I7 passe à 38 s. Sans borne de perception (8 m + ligne
de vue), I6 valait 0 par construction : la fermeture était lue par tous au
même tick.

### 3.4 C'est la rumeur qui fait le consensus, et c'est elle qui le fait mal

Trois modes de parole, même monde, bras `regles`, 5 graines :

| mode | I1 | décisions | messages | décisions vers une porte crue bloquée |
|---|---|---|---|---|
| `none` | 0,63 | 60 | 0 | **0,00** |
| `guards` (4 gardes parlent seuls) | 0,62 | 71 | 6 | **0,07** |
| `all` | 0,70 | 138 | 138 | **0,38** |

L'autorité présente ne construit pas l'accord ; c'est le ouï-dire de tout un
chacun qui le fait — et qui, simultanément, dégrade les décisions d'un facteur
5.

### 3.5 Un classifieur de décision fait le travail sans bavarder

Banc bloqué (4 agents, mémoire opposée), Kev-4B, options fermées
`RESTER`/`SORTIR <sortie>` : **1,00 sur 3 graines**, 0 décision vers une porte
crue bloquée — la performance du grand modèle, sans générer de texte, à 179
jetons d'entrée et zéro de sortie. À état identique, « Fumée visible » le
laisse sur RESTER (0,42) et « Danger : fumée visible » le fait sortir (0,41) :
un System 1 **classe** l'étiquette, il ne raisonne pas la situation.

### 3.6 En foule : la nature du modèle, pas sa taille

60 agents, 10 graines, scénario `split` (la moitié croit A bloquée, l'autre B,
les deux portes ouvertes), métrique principale = part des décisions dont la
cible était **crue bloquée au moment de décider** (test de Wilcoxon apparié
par graine) :

| bras | part | fautes / run | jetons | mural |
|---|---|---|---|---|
| `regles` | 0,41 | 52 | 0 | 0,3 s |
| `hybride` (règles + escalade) | 0,26 [−0,18 ; −0,12] | 71 | 125 k | 120 s |
| `llm_grand` (Gemma 4 E2B) | 0,20 [−0,24 ; −0,16] | 104 | 337 k | 327 s |
| `decision_head` (Kev-4B) | **0,03 [−0,41 ; −0,35]** | **18** | 100 k | 233 s |

p = 0,002 pour les trois écarts, 10 graines sur 10 dans le même sens.
Les deux lignes intermédiaires (`hybride`, `llm_grand`) viennent de la
campagne P1.1 ; leur fichier par run a été écrasé depuis, donc elles ne se
régénèrent qu'en relançant ces deux bras (note † du rapport).

Le **tiering** (40 visiteurs sur le petit, 20 habitués sur le grand) est encore
meilleur et moins cher que le grand seul : 0,10 et 0,06 sur deux graines, pour
143–169 k jetons contre 300–356 k. Le petit seul bat le grand seul (0,13 contre
0,22) : la taille du générateur ne paie pas sur cette tâche.

Trois lectures. **Le générateur aide** (deux fois moins de fautes par
décision) **mais perd sur le run** : il reconsidère quatre fois plus souvent,
donc s'expose quatre fois plus — 104 fautes contre 52. **Le classifieur
gagne sur les deux compteurs** : trois fois moins de fautes que les règles,
six fois moins que le générateur, pour 30 % de son coût. Et **la formulation
de l'état décide** : à état identique, « Fumée visible » laisse le classifieur
sur RESTER (0,42), « Danger : fumée visible » le fait sortir (0,41).

---

## 4. Discussion

Trois choses que ces résultats changent dans la façon de déployer un modèle
dans un système multi-agents :

1. **Le coût n'est pas la latence, c'est la cadence.** À perception inchangée,
   redécider ne change pas la réponse : la dépense utile suit les **faits du
   monde** (information nouvelle, plan invalidé, palier de contexte), pas
   l'horloge. La même règle fait passer un bras de 310 à 108 décisions pour le
   même nombre d'appels.
2. **Un modèle qui lit la rumeur doit être jugé sur la rumeur.** Toutes les
   comparaisons faites dans un monde muet surestiment le modèle : dès que les
   agents se parlent, l'écart avec les règles se referme et le coût est multiplié.
3. **La nature du modèle domine sa taille.** Le petit modèle seul fait mieux
   que le grand seul (0,13 contre 0,22) pour six fois moins de jetons ; Un classifieur de 4 B formé pour
   choisir dans un ensemble fermé bat un générateur de 2 B et coûte moins :
   ce qui compte n'est pas « plus de paramètres », c'est **la forme de la
   tâche**. Un modèle de 30 B placé dans un contrat JSON n'est pas
   nécessairement meilleur qu'un classifieur de 4 B placé devant les mêmes
   options.
4. **La formulation de l'état est une décision de conception, pas un détail.**
   La même situation, décrite comme un fait ou comme un danger, change la
   décision d'un classifieur. Toute évaluation qui ne publie pas l'état donné
   au modèle ne dit rien de reproductible.

---

## 5. Limites

- Un modèle de 2 B et un classifieur de 4 B : la conclusion vaut pour les
  **petits modèles embarqués**, pas pour « un LLM » en général.
- Ce modèle physique passe ≈3,2 pers/(m·s) par mètre de porte contre ≈1,3 en
  littérature : les temps absolus ne sont pas des temps de terrain, les
  comparaisons entre bras tiennent.
- I6 ne peut bouger que si une porte ferme : ce n'est pas un indicateur
  général, c'est un indicateur conditionnel.
- La calibration humaine (« est-ce crédible ? ») reste un jugement.

---

## 6. Reproductibilité

Une commande par affirmation (`make v3-twins`, `v3-worlds`, `v3-denial`,
`v3-speech`, `v3-crowd`, `v3-crowd-null`, `v3-tables`), JSON archivés dans
`runs/v3/`, tests 418+ sans GPU, et un journal qui rend chaque décision
rejouable sans modèle.
