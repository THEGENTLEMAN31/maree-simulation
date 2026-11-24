# Pré-enregistrement des campagnes (v3, après correctifs)

_Écrit **avant** les mesures qu'il décrit. Un critère choisi après avoir vu le
résultat n'est pas un critère, c'est une rationalisation. Si une campagne
échoue à son critère, on publie l'échec, pas un critère déplacé._

---

## Campagne A — solidité statistique (P1.1)

**Question.** Les écarts entre bras mesurés sur 5 graines tiennent-ils sur 10,
et avec quel intervalle ?

**Dispositif.** `crowd_hall`, 60 agents, parole active, scénarios `split` et
`contradiction`, bras `regles`, `hybride`, `llm_grand`. Graines 1–10 appariées
par graine (même monde, même tirage de positions).

**Critères (avant mesure).**

| critère | seuil |
|---|---|
| critère principal | part des décisions dont la cible était **crue bloquée au moment de décider** (`target_believed_blocked`) |
| test | Wilcoxon signé par graine, α = 0,05, deux côtés |
| taille d'effet | différence de médianes, avec intervalle bootstrap (10 000 tirages) |
| robustesse | 60/60 sortis sur ≥ 9 graines par bras (sinon on note la censure) |

**Ce qui invaliderait la conclusion actuelle.** Si l'intervalle de la
différence `llm_grand − regles` contient 0 sur les deux scénarios, la phrase
« le grand modèle ne trie pas mieux la rumeur » devient « on ne mesure pas de
différence » — ce n'est pas la même affirmation et elle sera écrite telle
quelle.

---

## Campagne B — familles de mondes (P1.2)

**Question.** La bande de calibration tient-elle hors du monde de référence ?

**Dispositif.** 5 salles de même distribution (`verify/worlds.py`), 3 graines
chacune, bras `règles`, sans parole.

**Critère.** I5 pic ∈ **[0,8 ; 1,6]** pers/m², pic **après** le spawn
(`peak_tick ≥ 3`), 60/60 sortis. **Le critère est le même qu'ADR-015**, il a
été écrit avant la mesure.

**Résultat (2026-11-22) : tenu 5/5** (I5 1,27–1,51, pic t6–t8). Aucun
déplacement de bande n'a été nécessaire.

---

## Campagne C — démenti tardif (P2.2)

**Question (H5).** « Le démenti corrige la croyance, pas l'action engagée. »

**Dispositif.** 60 agents, règles, fumée à t1, démenti à t ∈ {2, 3, 4, 5, 6, 8}
ou jamais ; 3 graines.

**Critères, et ils sont séparés exprès.**

1. **audience** : combien d'agents sont encore dans la salle à t (mesuré par
   les instantanés physiques) ;
2. **conversion** : parmi eux, part qui change d'action (dernière décision
   vers B) ;
3. **délai** : ticks entre le démenti et la première décision vers B.

**Ce qui falsifie H5.** Une conversion ≈ 1,0 à tous les instants : l'action
suit la croyance sans inertie, donc l'engagement n'explique rien, et ce qui
limite un démenti tardif est le nombre de gens déjà dehors.

**Résultat (2026-11-22) : H5 falsifiée.** Conversion 1,00 à tous les instants,
délai 0 ; l'audience passe de 60 (t2) à 29 (t8), et I7 de 26 à 38 s.

---

## Campagne D — parole ou rumeur ? (P3.3)

**Question.** L'accord mesuré en C7 vient-il de l'**autorité** qui informe, ou
du **ouï-dire** de tout un chacun ?

**Dispositif.** Trois modes de parole sur le même monde (règles, `split`,
5 graines) : `none`, `guards` (4 agents de sécurité parlent seuls), `all`.

**Critères.** Si `guards` remonte le consensus autant que `all`, c'est
l'autorité ; sinon, c'est la rumeur — et on le dit.

**Résultat (2026-11-22).** I1 : 0,63 / 0,62 / 0,70. Décisions vers une porte
crue bloquée : 0,00 / 0,07 / 0,38. **C'est la rumeur**, et elle dégrade.

---

## Campagne E — modèle de décision (P3.1)

**Question.** Un classifieur System 1 fait-il ce qu'un générateur fait, sans
générer de texte ?

**Dispositif.** Kev-4B (3,03 Go, Apache 2.0) sur `/v1/systemone` ; options
fermées `RESTER` + `SORTIR <sortie>`. Comparé aux règles et au grand sur le
même monde et les mêmes graines.

**Dispositif.** Kev-4B sur `/v1/systemone`, port 8083, **10 graines**, deux
scénarios (`split`, `contradiction`), mêmes graines que la campagne A ; les
règles sont relancées sur les mêmes graines pour l'appariement (elles coûtent
0,3 s par run).

**Critère principal.** Part des décisions vers une porte crue bloquée
(`target_believed_blocked`), plus le coût (jetons, appels, temps).

**Critère de méthode, écrit avant.** L'état donné au modèle doit nommer la
fumée comme un **danger** (« Danger : fumée visible »), et le rapport doit
préciser la formulation : mesuré à part, « Fumée visible » laisse le modèle
sur RESTER (0,42), « Danger : » le fait sortir (0,41). Ce n'est pas du réglage
caché, c'est une propriété du modèle qu'on publie.

---

### Exception consignée : le critère de robustesse du bras classifieur

Le critère général de la campagne A exige « 60/60 sortis sur ≥ 9 graines ».
Le bras `decision_head` **ne le tient pas** : 58 à 59 agents sortis sur 60 au
plafond de 30 ticks. Ce n'est pas une censure du run (I3 vaut 1,00) mais deux
agents encore dans la salle, parce que le classifieur hésite plus longtemps
(I7 39–42 s contre 24 s pour les règles).

Décision : **on publie l'écart et on le compte comme un coût du bras**, pas
comme un critère déplacé. Conséquence pratique : un déploiement qui exige
100 % de sortie dans un temps borné doit prévoir une revue de sécurité sur ce
bras — c'est écrit dans le rapport (§5.7) et dans les limites.

## Campagne F — deux tiers et quota ε (P2.3 / P2.4)

**Question.** Que paie-t-on pour quoi ? 40 visiteurs sur le petit + 20 habitués
sur le grand, contre grand seul et petit seul. Puis ε ∈ {0 ; 0,25 ; 0,5} sur
l'hybride.

**Critères.** Coût (jetons, appels, temps) et part de décisions vers une porte
crue bloquée ; pour ε, la même qualité que l'escalade ciblée doit être
atteinte à ε = 0, sinon l'escalade ciblée ne suffit pas — et c'est un résultat
sur l'hybride, pas sur ε.
