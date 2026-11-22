# Rapport v3 — ce qui tourne, ce qui est mesuré, ce qui ne l'est pas

_22 novembre 2026 (seconde édition ; la première, du 18, est conservée sous
`rapport-v3-avant-correctif.md`). Ce document se lit seul. Chaque chiffre est
régénérable par une commande du dépôt (`make v3-…`), chaque campagne est
pré-enregistrée (`docs/v3/preregistrements.md`), et les JSON sources sont dans
`runs/v3/`._

---

## 1. La question, et ce qui a changé depuis le 18

La v2 comptait des sorties ; la v3 doit expliquer des **choix**. Depuis la
première édition, trois choses ont été mesurées qui n'existaient pas :

- **la mission n°1** (deux agents du même archétype divergent par leur
  mémoire) n'était pas mesurée après correctifs — elle l'est ;
- le **compteur de croyance** ne distinguait pas « se trompe » de « ne croit
  plus que c'est fermé » — il le distingue, et cela **change la conclusion**
  sur le modèle ;
- un **cinquième bras** existe : un classifieur de décision « System 1 »
  (Kev-4B), qui ne génère pas de texte.

---

## 2. Le modèle expérimental

Trois choses partagées (perception, physique, journal), une seule différence :
qui décide, et quand.

| bras | qui décide | quand | coût médian (10 graines, split) |
|---|---|---|---|
| `regles` | politique déterministe | fronts (fumée, annonce, message, fermeture) | 0 jeton, 0,3 s |
| `hybride` | règles, modèle si le monde est ambigu | fronts + escalade sur faits + revue | 125 k jetons, 120 s |
| `llm_grand` | Gemma 4 E2B (local, GPU) | changement pertinent de perception | 337 k jetons, 327 s |
| `llm_petit` | Qwen3 0.6B (local) | idem | 37 k jetons, 16 s |
| `decision_head` | Kev-4B, classifieur (options fermées) | idem | 100 k jetons, 233 s (16 couches GPU) |

Le calendrier est un **fait du monde**, pas une horloge (ADR-014) : on ne
redécide pas parce que le temps passe, mais parce qu'une information est
nouvelle, qu'un plan est invalidé, ou qu'un palier de contexte est franchi.

---

## 3. Le dispositif

**Monde calibré** : 22 × 16 m, deux issues de 1,2 m, 60 agents. Le bras témoin
y produit un pic de densité de **1,1–1,5 pers/m²** et une évacuation en
22–26 s. Un hall de 120 × 80 m donne **0,000 pers/m²** à 60 agents : il ne
contraint rien, donc il ne mesure rien.

**Famille de mondes** : cinq salles de même distribution (20–24 × 14–18 m),
critère pré-enregistré tenu **5/5** (I5 1,27–1,51, pic à t6–t8, 60/60 sortis).

**Deux écarts assumés** (ADR-015) : ce modèle passe ≈3,2 pers/(m·s) par mètre
de porte contre ≈1,3 en littérature — les **temps absolus** ne sont pas des
temps de terrain, les comparaisons entre bras tiennent ; et le tick du
scénario vaut 2 s, sinon une salle vidée en 25 s ne donne que deux points de
mesure.

**Mesure par décision, jamais par agent** : part des décisions dont la cible
était **crue bloquée au moment de décider** (`target_believed_blocked`),
appels tentés/réussis, jetons, temps mural, I1–I7.

---

## 4. Mission n°1 : la mémoire fait diverger

| dispositif | accord entre jumeaux | KL |
|---|---|---|
| 200 paires, mémoires opposées | **0,00** | 20,7 |
| 200 paires, mémoire **coupée** | **1,00** | 0,0 |

À gauche, 100 % des jumeaux prennent B ; à droite, 100 % prennent A. En foule
(60 agents, 5 graines) : **1,00** des agents n'utilisent pas la porte qu'ils
croient bloquée, contre **0,00** sans mémoire.

La mémoire J−3 (faits datés en ticks négatifs) est amorcée par
`Simulation(prehistory=True)` et écrit des **croyances** sourcées, pas
seulement des récits ; les proches (`famille`) sont appariés au spawn à
1,1–1,9 m, donc `CHERCHER_PROCHE` existe en run.

---

## 5. Résultats en foule (10 graines, 60 runs)

### 5.1 Décisions vers une porte crue bloquée

Métrique principale, **au moment de décider** (médiane ; test de Wilcoxon
apparié par graine, IC95 bootstrap) :

| bras | `split` | `contradiction` | écart vs `regles` |
|---|---|---|---|
| `regles` | **0,41** | **0,40** | — |
| `hybride` | **0,26** | **0,20** | −0,15 [−0,18 ; −0,12] / −0,20 [−0,22 ; −0,17], p = 0,002 (10/10) |
| `llm_grand` | **0,20** | **0,20** | −0,20 [−0,24 ; −0,16], p = 0,002 (10/10) |
| `decision_head` | **0,03** | **0,04** | −0,38 [−0,41 ; −0,35], p = 0,002 (10/10) |

**Le modèle fait bien quelque chose.** Il divise par deux la part de
décisions qui visent une porte crue bloquée — et l'effet est robuste : 10
graines sur 10 dans le même sens, intervalle qui exclut 0.

### 5.2 Ce que le modèle fait aussi : décider quatre fois plus souvent

C'est la nuance que la première édition ratait, et elle change la lecture :

| bras | décisions / run (split) | part crue bloquée | **décisions fautives / run** | jetons |
|---|---|---|---|---|
| `regles` | 126 | 0,41 | **52** | 0 |
| `hybride` | 272 | 0,26 | **71** | 125 k |
| `llm_grand` | 520 | 0,20 | **104** | 337 k |
| `decision_head` | 563 | 0,03 | **18** | 100 k |

Par décision, le générateur est deux fois meilleur que les règles. **Par run,
il se trompe deux fois plus**, parce qu'il reconsidère quatre fois plus : le
coût n'est pas seulement en jetons, il est en **exposition**.

Le classifieur, lui, décide autant (563 décisions) mais se trompe **trois fois
moins souvent que les règles et six fois moins que le générateur** — par
décision *et* par run. C'est le seul bras qui gagne sur les deux compteurs.

### 5.3 L'hybride : le meilleur rapport, pas le meilleur score

`hybride` −0,15/−0,20 (p = 0,002) pour **125 k jetons** contre **337 k** au
grand : à qualité comparable sur `contradiction` (0,20 vs 0,20, p = 0,92), il
coûte 2,7× moins. Sur `split`, le grand reste devant d'un petit écart
(−0,06 [−0,07 ; −0,04], p = 0,004, 9 graines sur 10).

### 5.4 Ce que le compteur ambigu cachait

L'ancien compteur (« porte désignée bloquée à t1 ») donne l'image inverse :

| bras | désignée t1 · split | désignée t1 · contradiction |
|---|---|---|
| `regles` | 0,24 | 0,29 |
| `hybride` | 0,38 | 0,47 |
| `llm_grand` | 0,33 | 0,38 |

Sur ce compteur, le modèle est **pire** que les règles. Il ne l'est pas : il
décide plus souvent, donc il a plus d'occasions de partir avant d'avoir
appris. Les deux chiffres sont vrais ; ils répondent à deux questions
différentes (fidélité au scénario vs qualité de la décision informée). C'est
pourquoi le rapport publie les deux, et pourquoi le second est la métrique
principale.

### 5.5 Deux tiers en foule : moins cher **et** meilleur

40 visiteurs sur le petit modèle + 20 habitués sur le grand, même monde,
2 graines (`scripts/v3_bands.py`) :

| configuration | appels | jetons | décisions vers une porte crue bloquée |
|---|---|---|---|
| `regles` | 0 | 0 | 0,41 / 0,35 |
| grand seul | 468 / 550 | 300 k / 356 k | 0,22 / 0,19 |
| petit seul | 436 / 459 | 52 k / 55 k | 0,13 / 0,12 |
| **deux tiers** | 481 / 563 | **143 k / 169 k** | **0,10 / 0,06** |

Le tiering ne coûte pas en qualité : il **en gagne**. Et le petit modèle seul
bat le grand seul (0,13 contre 0,22) pour six fois moins de jetons. Sur cette
tâche — choisir parmi des sorties connues, avec un état court — la taille du
générateur ne paie pas ; ce qui paie, c'est ce qu'on demande au modèle.

### 5.6 Le quota ε n'ajoute rien

Escalade **aléatoire** sur la routine (tirage SHA-256), bras hybride, même
monde, 2 graines :

| ε | appels | jetons | I1 | crue bloquée |
|---|---|---|---|---|
| 0 | 196 / 215 | 121 k / 135 k | 0,79 / 0,88 | 0,28 / 0,24 |
| 0,25 | 198 / 208 | 122 k / 130 k | 0,84 / 0,84 | 0,29 / 0,27 |
| 0,5 | 196 / 213 | 121 k / 134 k | 0,79 / 0,82 | 0,28 / 0,26 |

Aucun effet mesurable : l'escalade **ciblée** suffit, le quota est un
instrument sans bénéfice sur ce monde — il reste un outil de diagnostic, pas
un levier.

### 5.7 Un classifieur System 1 (Kev-4B) domine les deux autres natures

Même monde, mêmes graines, options fermées (`RESTER`, `SORTIR A`, `SORTIR B`),
état en français qui nomme le danger, la distribution journalisée :

| mesure (médiane) | `split` | `contradiction` |
|---|---|---|
| décisions vers une porte crue bloquée | **0,031** | **0,041** |
| décisions fautives par run | **18** | **24** |
| jetons | 99 681 | 111 190 |
| temps mural | 233 s | 247 s |
| évacués | 59/60 | 58/60 |

Contre les règles (52 fautes par run, 0 jeton) et le générateur (104 fautes,
337 k jetons), le classifieur divise les fautes par **3** et par **6**, à 30 %
du coût du générateur. **C'est la réponse la plus nette du projet** : la
question n'est pas « LLM ou règles », c'est **quelle nature de modèle** — un
classifieur sur un ensemble fermé bat un générateur de texte sur cette tâche.

Deux réserves, mesurées :

- **la formulation de l'état décide** : à état identique, « Fumée visible »
  laisse le modèle sur RESTER (0,42), « Danger : fumée visible » le fait sortir
  (0,41). Un System 1 classe l'étiquette, il ne raisonne pas la situation ;
- **la sortie n'est évacuée qu'à 58–59/60** sur 30 ticks : le classifieur
  hésite plus longtemps (I7 39–42 s contre 24 s pour les règles) et deux agents
  restent dans la salle au plafond. Ce n'est pas une censure du run, c'est un
  délai réel.

---

## 6. Quatre expériences de comportement

### 6.1 La rumeur, pas l'autorité

Trois modes de parole, même monde, bras `regles`, 5 graines :

| mode | I1 | décisions | messages | décisions vers une porte crue bloquée |
|---|---|---|---|---|
| `none` | 0,63 | 60 | 0 | **0,00** |
| `guards` (4 gardes parlent seuls) | 0,62 | 71 | 6 | **0,07** |
| `all` | 0,70 | 138 | 138 | **0,38** |

L'autorité présente ne construit pas l'accord ; c'est le ouï-dire qui le
construit, et qui dégrade les décisions d'un facteur 5.

### 6.2 Un démenti tardif n'est pas ignoré — il n'atteint plus personne

| démenti | présents | changent d'action | part | délai | sortie par A | I7 |
|---|---|---|---|---|---|---|
| aucun | — | — | — | — | 60 | 24 s |
| t2 | 60 | 60 | 1,00 | 0 | 0 | 26 s |
| t4 | 53 | 53 | 1,00 | 0 | 7 | 30 s |
| t6 | 42 | 42 | 1,00 | 0 | 18 | 36 s |
| t8 | 29 | 29 | 1,00 | 0 | 31 | 38 s |

Toutes les personnes atteintes changent d'action, sans délai. **H5 est
falsifiée** : ce qui limite un démenti tardif est l'audience, pas
l'engagement.

### 6.3 Une fermeture d'issue se perçoit localement

A ferme à t4 : I6 monte à **0,43** puis retombe à **0,04** ; 53 décisions se
rabattent sur B ; 60/60 sortent ; I5 1,75 (un seul goulot) ; I7 38 s. Avant
le correctif, la fermeture était lue par tous au même tick et I6 valait 0 par
construction.

### 6.4 Le null de B3 est un run

Même monde, même politique, `speaking=False` : I1 passe de 0,63 à 0,72
(règles) et de 0,63 à 0,87 (petit), soit **E_social +0,09 à +0,24** — et les
décisions vers une porte crue bloquée de 0,00 à 0,24.

---

## 7. Ce qui tient, ce qui ne tient pas, ce qu'on ne peut pas revendiquer

### Tient

- la mission n°1, mesurée à deux échelles, avec ablation ;
- le calendrier par faits du monde (0 appel pour les règles, escalade sur
  critère nommé, bornée) ;
- la fermeture perçue localement et le réacheminement ;
- le null exécuté, à code identique ;
- 418 tests, ruff et mypy propres, contrat WS de bout en bout.

### Ne tient pas (et est publié comme tel)

- « le modèle ne sert à rien » : **faux** ; par décision le générateur divise
  les fautes par deux, et le classifieur par dix — significativement, 10
  graines sur 10 ;
- « le modèle fait mieux » : **incomplet** ; le générateur, par run, commet
  deux fois plus de fautes que les règles, parce qu'il décide quatre fois
  plus ; le classifieur, lui, gagne sur les deux compteurs ;
- « l'hybride est un compromis » : vrai sur le coût (2,7× moins que le
  générateur), faux sur `split` où le générateur reste devant ;
- « la fumée suffit à faire évacuer un modèle de décision » : non — à état
  identique, « Fumée visible » le laisse sur RESTER (0,42), « Danger : fumée
  visible » le fait sortir (0,41). Un System 1 **classe** l'étiquette.

### Ne peut pas être revendiqué

- une généralisation à « un LLM » : 2 B et 4 B embarqués, pas un modèle de
  frontière ;
- des temps absolus de terrain (débit de porte 2,4× la littérature) ;
- I6 comme indicateur général : il ne bouge que si une porte ferme ;
- une reproductibilité LLM exacte : on agrège des graines, on n'apparie pas
  deux runs ;
- une calibration humaine : c'est un jugement, pas une mesure.

---

## 8. Reproduire

```bash
uv run pytest                        # 418 tests, sans GPU
make v3-twins v3-worlds v3-denial v3-speech   # aucun GPU
make v3-crowd                        # 4 bras × 2 scénarios (serveurs requis)
make v3-crowd-null                   # le null de B3
make v3-tables                       # les tableaux de ce rapport
uv run python scripts/v3_stats.py runs/v3/campaign_crowd.json   # tests appariés
```

Archives : `runs/v3/campaign_crowd.json` (campagne 10 graines),
`campaign_crowd_10seeds_from_log.json` (reconstruit après un écrasement
accidentel ; le champ « croyance au moment de décider » y est absent, ses
valeurs par bras sont dans `stats.json`), `twins.json`,
`worlds.json`, `denial.json`, `speech_modes.json`, `bands.json`.

---

## 9. Questions ouvertes

1. **Le plafond du générateur est-il sa cadence ?** Il décide mieux et plus
   souvent, et perd sur le total ; le classifieur, à cadence comparable, gagne
   largement. Reste à mesurer un générateur **contraint à la cadence des
   règles** : si l'écart se referme, le problème du générateur est le
   calendrier, pas la lecture.
2. **Un modèle plus gros change-t-il la conclusion ?** Non testé : 2 B et 4 B
   seulement. Gemma 4 E4B est téléchargé (4,97 Go) mais ne tient pas avec les
   autres sur 4 Go.
3. **La géographie reste statique** : un message ne fait pas apprendre une
   sortie inconnue.
4. **L'hybride demande un état de plan explicite**, pas un calendrier plus
   fin, pour que sa décision escaladée ne soit pas défaite par les fronts
   suivants.
