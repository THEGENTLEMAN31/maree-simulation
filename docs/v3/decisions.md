# Journal des décisions d'architecture (ADR)

_Chaque décision est datée, motivée, et accompagnée de ses conséquences.
Une décision peut être remplacée ; elle n'est jamais effacée._

---

## ADR-001 — Le comportement humain est la mission 1

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

La v2 a été construite comme un outil d'étude de la croyance en évacuation.
Les retours du porteur de projet sont clairs : ce qui compte, c'est que les
agents se comportent comme des humains, et que deux agents du même archétype
divergent par leur mémoire. L'architecture est une application secondaire.

### Décision

La v3 est ordonnée autour du **comportement** : traits, état, appraisal,
mémoire, individualité. L'aide à la conception (variantes, sorties, feux) est
une application de cette base.

### Conséquences

- les semaines 1–4 sont consacrées au comportement ;
- la validation porte sur des phénomènes comportementaux, pas seulement sur
  des indicateurs globaux ;
- le procédural et l'IFC passent en dernier.

---

## ADR-002 — Godot est le front de référence, glTF est le contrat

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

Le front doit être un observatoire 3D avec des personnages importés, une
caméra 3/4 ou orthographique, et des étiquettes. L'équipe ne veut pas
développer un moteur de rendu.

### Décision

- Godot 4 est le front de référence ;
- le noyau produit un **RenderArtifact glTF 2.0 + manifeste** ;
- le flux dynamique passe par WebSocket ;
- aucun autre front n'est requis, mais le contrat le permet.

### Conséquences

- Godot ne génère pas le monde ;
- le glTF doit porter des IDs stables (`extras`) ;
- un front web reste possible plus tard sans changer le noyau.

---

## ADR-003 — Pas de rétrocompatibilité v2

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

La v2 a servi à définir ce qu'on veut et ce qu'on ne veut pas. Elle n'est pas
un format à préserver.

### Décision

- les runs v2 ne sont pas rejoués par la v3 ;
- le schéma d'événement est versionné, mais il n'y a pas d'adaptateur v2 ;
- le code v2 peut être archivé, pas maintenu.

### Conséquences

- liberté de schéma ;
- pas de dette de migration ;
- les chiffres v2 restent dans les rapports, pas dans le runtime.

---

## ADR-004 — Mono-étage en v3.0, multi-étages en v3.1

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

Le multi-étages est un besoin réel (mall), mais il n'est pas la priorité
comportementale et il coûte cher (coordinateur, transferts, capacité).

### Décision

- le **WorldSpec supporte les étages dès la v3.0** ;
- la **simulation v3.0 tourne sur un seul niveau** ;
- la v3.1 ajoute le `LevelCoordinator` et les transferts.

### Conséquences

- pas de réécriture du schéma en v3.1 ;
- le rendu peut montrer plusieurs étages avant la simulation ;
- les escaliers sont visibles mais non simulés en v3.0.

---

## ADR-005 — Aucun moteur de foule maison

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

JuPedSim est un moteur 2D validé (LGPLv3+). `jupedsim-network` est un modèle
réseau multi-niveaux officiel, mais récent et prototype. Écrire un moteur
serait un projet à part entière, et le résultat serait moins fiable.

### Décision

- **JuPedSim** pour la physique micro, par étage ;
- **jupedsim-network** pour l'écrantage grossier multi-niveaux, derrière un
  port, version épinglée, avec repli ;
- **LevelCoordinator** écrit par nous : orchestration, pas physique.

### Conséquences

- on hérite de la validation de JuPedSim ;
- on accepte la limite 2D par étage ;
- le coordinateur est le seul composant « moteur » custom, et il est borné.

---

## ADR-006 — Fumée grossière, pas de propagation de flammes

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

Le réalisme du feu n'est pas la priorité. Ce qui compte, c'est que la fumée
change le comportement (visibilité, demis-tours, évitement).

### Décision

- sources de feu + champ de fumée par étage (grille 1–2 m) ;
- visibilité, CO, température simples ;
- pas de propagation de flammes, pas de radiation, pas de sprinklers ;
- FDS importé en v3.1 seulement.

### Conséquences

- coût négligeable ;
- validation possible (source isolée, transport vertical, visibilité) ;
- on ne prétend pas à un usage réglementaire.

---

## ADR-007 — OpenJev est une tête de décision optionnelle

**Date** : 2026-11-04
**Statut** : accepté, sous évaluation

### Contexte

OpenJev est une famille de modèles « System-One » qui renvoient des
probabilités calibrées sur un ensemble fini d'options, en un passage. C'est
rapide et sans parsing. Mais ce n'est pas un modèle de comportement, et il a
des limites documentées (pas de raisonnement multi-étapes, interférence
d'état, résumé périmé).

### Décision

- l'intégrer derrière un port `DecisionHeadPort` ;
- l'utiliser pour **scorer** des actions candidates, pas pour décider seul ;
- l'évaluer sur 300–500 situations avant adoption ;
- vérifier la licence (Apache vs non commercial).

### Conséquences

- si l'évaluation est mauvaise, on garde les règles ;
- le modèle ne devient jamais une dépendance obligatoire ;
- les probabilités sont journalisées.

---

## ADR-008 — Matrice de stockage, pas de base unique

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

La v2 stocke tout en JSONL : 83 % des octets sont des snapshots, `state.json`
duplique le dernier snapshot, et les requêtes analytiques relisent tout.

### Décision

- **PostgreSQL** pour le métier ;
- **pgvector** pour le corpus ;
- **Parquet + DuckDB** pour les faits et métriques ;
- **S3/MinIO** pour les snapshots, trajectoires, GLB ;
- **Redpanda** pour la diffusion ;
- **Redis** pour l'état courant (optionnel).

### Conséquences

- plusieurs systèmes à opérer ;
- mais chaque accès est adapté à son profil ;
- le journal reste la source de vérité.

---

## ADR-009 — Assets importés, pas générés

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

La qualité des personnages importés est supérieure à ce qu'on produirait.
Générer des personnages est un métier.

### Décision

- importer des personnages et animations (Mixamo, Quaternius, Kenney, VRM) ;
- style low-poly stylisé, lisible ;
- manifeste de licences par asset ;
- pas de photoréalisme.

### Conséquences

- le front doit gérer le retargeting et les LOD ;
- les licences doivent être vérifiées avant publication ;
- on ne bloque pas sur l'art.

---

## ADR-010 — Graphify est un outil de développement

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

Graphify transforme un dépôt en graphe de connaissances (AST local,
`graph.json`, `graph.html`, MCP, query/path/explain). C'est utile pour
naviguer le code, pas pour nourrir les agents.

### Décision

- Graphify est installé comme outil de développement ;
- `.graphifyrc`, `.graphifyignore`, cible `make graph` ;
- usage : onboarding, revue d'architecture, impact analysis, traçabilité ADR ;
- **pas** une dépendance runtime ;
- la connaissance partagée des agents est le `KnowledgeStore`, pas Graphify.

### Conséquences

- le graphe de code est un artefact de dev, pas un artefact de run ;
- les agents ne lisent jamais `graphify-out/`.

---

## ADR-011 — Le dossier agent est configurable, avec trois étiquettes

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

Le front doit pouvoir afficher la bio, les pensées, les reçus, les
communications, et configurer ses panneaux.

### Décision

- API `GET /runs/{id}/agents/{agent}?include=...` ;
- sections additives et versionnées ;
- template `dossier.yaml` côté front ;
- trois étiquettes obligatoires : `measured`, `derived`, `generated`.

### Conséquences

- le serveur expose un superset, le front choisit ;
- le monologue interne n'est jamais présenté comme une vérité ;
- les performances restent bonnes (calcul à la demande).

---

## ADR-012 — Validation ISO 20414 + protocole comportemental

**Date** : 2026-11-04
**Statut** : accepté

### Contexte

« Les agents se comportent comme des humains » est une affirmation forte.
Sans protocole, elle n'est pas défendable.

### Décision

- vérification des composants selon **ISO 20414:2020** ;
- validation comportementale sur quatre phénomènes (pré-mouvement, choix de
  sortie, influence sociale, cohésion) ;
- calibration puis validation sur des scénarios tenus à l'écart ;
- ablations obligatoires (mémoire, social, fumée).

### Conséquences

- les résultats sont datés, chiffrés, limités ;
- on ne dira jamais « validé » sans les quatre étapes ;
- le rapport de validation est un livrable de la semaine 9.

---

## ADR-013 — Passerelle LLM fine (pas LiteLLM) + registre de politiques natif

**Date** : 2026-11-10
**Statut** : accepté

### Contexte

La semaine 4 doit rendre *deux providers interchangeables* et un registre de
politiques. La v2 empruntait le SDK `openai` derrière une URL llama.cpp et a
toujours été légère. LiteLLM (la brique listée en semaine 4 du roadmap) est
un super-client multi-providers commode, mais lourd et peu utilisé ici : on
ne parle à *quatre* providers max, tous OpenAI-compatibles. Le LLM du projet
tourne en natif sur l'hôte (port `8081`), sur ses propres modèles, jamais sur
le serveur personnel (`8080`).

### Décision

- **passerelle fine** : `ChatModelPort` (contrat) + `OpenAICompatibleChat`
  (adaptateur via le SDK `openai`) + `StubChat` (tests, ablation) — deux
  fournisseurs interchangeables derrière un même port ;
- **pas de LiteLLM** en v3.0 : le catalogue (`ModelSpec`) et le registre de
  fournisseurs suffisent, et la matrice de traçabilité (provider, modèle,
  seed, tokens) est déjà dans `LLMTrace` ;
- **politique par défaut = `hybrid`** (règles, essor LLM seulement en
  ambiguïté) : c'est ce qui garantit la reproductibilité de la mission 1 ;
- **l'axe « la taille du modèle compte-t-elle »** est un objectif : les
  modèles du projet vont de 0,6 Md à ~8 Md, avec offload CPU — la taille et
  la latence sont **journalisées** (elles se confondent sinon).

### Conséquences

- aucun client HTTP maison, aucune dépendance lourde ;
- les tests prouvent l'interchangeabilité sans GPU ;
- OpenJev reste derrière un port (ADR-007) et n'est pas adopté tant que le
  banc (semaine 4 : `verify/bench`) n'est pas concluant ;
- le banc actuel met un **stub** en fournisseur : la colonne `llm` mesure le
  mécanisme, pas un modèle réel — l'évaluation sur modèle natif suit (S4 b).

---

## ADR-014 — Le calendrier de décision est un fait du monde, pas une horloge

**Date** : 2026-11-17
**Statut** : accepté (remplace la clause « politique par défaut = `hybrid` »
de l'ADR-013)
**Motif** : audit du 2026-11-17, `docs/v3/plan-redressement.md`

### Contexte

L'audit a établi, mesures en main :

- le bras `hybride` n'appelait **jamais** le modèle (0 appel sur le scénario
  bloqué, décision identique aux règles) parce que son critère était
  circulaire : « les règles ne savent pas quoi faire » ;
- même le bras `llm` ne reconsidérait que sur **quatre fronts** (fumée,
  annonce, proche, message) : le calendrier était une liste déterministe
  **partagée par les trois bras**, donc « quand penser » ne variait pas ;
- la perception ne portait ni voisins, ni densité, ni distance au danger :
  aucun déclencheur plus fin **ne pouvait** se lever.

Trois définitions de l'hybride étaient sur la table : escalade sur ambiguïté
du monde, quota aléatoire ε, modèle arbitre d'options produites par les
règles. Le porteur de projet retient la **première**.

### Décision

1. **Le calendrier de décision est un fait du monde, pas une horloge.** Un
   agent ne reconsidère que si un *changement pertinent* peut invalider sa
   décision courante. Entre deux décisions, il **agit** : le corps continue
   sur la dernière intention, la décision est un engagement révisable.

2. **Trois familles de déclencheurs**, journalisées avec leur cause :
   - *information nouvelle* : fumée, annonce, message, sortie qui ferme ou
     rouvre, proche qui réapparaît ;
   - *plan invalidé* : la cible de l'intention est crue bloquée, n'est plus
     visible ou est saturée ; pas de progression (moins de 2 m en 5 ticks) ;
     séparation du groupe ;
   - *contexte changé, lent et borné* : palier de densité (0,5 / 1 / 2
     pers/m²), ≥ k agents partant vers une autre sortie, menace franchissant
     0,4 ou 0,6, revue périodique sous menace.

3. **Marche de référence** (elle fait foi pour les tests et le rapport) —
   un agent, 30 ticks, monde bloqué macro :

   | tick | ce qui change dans le monde | ce que fait l'agent | appel ? |
   |---|---|---|---|
   | 0 | spawn | immobile, pas d'intention | non |
   | 2 | message « A est bloquée » | décide : **B** | oui (1) |
   | 3–9 | rien | garde B, avance | non |
   | 10 | fumée | reconsidère : B tient | oui (2) |
   | 11–18 | la densité franchit 1,0 pers/m² près de B | B se sature ? | oui (3) |
   | 19 | il voit 6 agents faire demi-tour | changer pour A ? | oui (4) |
   | 20–30 | rien | garde sa cible | non |

   Quatre appels pour trente ticks. « Chaque tick » en demanderait 1 800 pour
   60 agents, dont la plupart rendraient la **même réponse** (température 0,
   prompt inchangé) : c'est le même raisonnement facturé huit fois, pas une
   autre architecture.

4. **`hybride` = règles + escalade sur les critères de `agents-et-llm.md` §3,
   calculés côté monde** : `annonce_ambigue`, `information_contradictoire`,
   `situation_inedite`, `revue`, plus l'ancien `regles_indecises` **nommé**
   (il n'est plus le seul). Chaque escalade publie `agent.escalation` avec sa
   cause et ses valeurs ; une escalade sans cause est un incident.

5. **`llm` = le modèle décide à chaque changement pertinent**, pas à chaque
   tick. Le prompt contient la perception : à perception inchangée, la
   réponse ne peut pas légitimement changer.

6. **ε (quota) est un instrument de sensibilité, jamais un bras ni un
   comportement.** Tirage déterministe par SHA-256(run, tick, agent) ; il sert
   à dire si la valeur du modèle est **concentrée** (escalade ciblée suffit)
   ou **diffuse** (il faut ε plus haut). Il se lit toujours contre l'escalade
   ciblée, jamais seul : à ε faible on escalade surtout la routine, donc on
   fabrique un faux négatif.

7. **La mesure se fait par décision, pas par dernière décision d'agent.**
   Une politique qui se corrige à t10 n'est pas une politique qui a bien
   choisi à t2 (cas mesuré : les règles envoient d'abord vers la porte qu'on
   vient de leur dire bloquée).

### Conséquences

- `Agent.react` ne décide plus sur `_novel_events` codé en dur : le
  calendrier devient `should_decide(agent, perception, tick) -> (bool,
  raison)`, propre à chaque bras.
- **La politique par défaut des runs d'ingénierie et des campagnes est
  `rules`** ; `hybride` ne redevient un défaut qu'une fois son taux
  d'escalade mesuré non nul (porte G1).
- Un agent dont l'intention est périmée (porte fermée, pas de progression)
  **doit** reconsidérer : c'est une exigence, pas une conséquence.
- Le schéma d'événement passe à `maree.event/1.1` (additif : `arm`,
  `escalation_cause` sur `agent.decision` ; type `agent.escalation`).
  `1.0` reste accepté.
- La perception doit précéder le calendrier (chantier C2 avant C3) : un
  déclencheur ne peut réagir qu'à ce que la perception contient.
- Les chiffres publiés avant cette date restent dans
  `runs/v3/avant_correctif/` et ne se comparent plus à ceux d'après.

---

## ADR-015 — Mesurer la foule demande un monde calibré, une horloge déclarée et une porte qui ne s'invente pas

_2026-11-18. Statut : accepté (chantier C5, porte G2)._

### Contexte

C2 → C4 ont rendu la perception, le calendrier et la mesure honnêtes. Reste
un problème de monde : la campagne macro doit montrer une **évacuation**, pas
une marche. Trois faits mesurés ont forcé trois décisions.

1. `hall_3` (120 × 80 m, 9 600 m²) avec 60 agents donne une densité locale
   maximale de **0,000 pers/m²**. Il n'y a pas de foule, donc pas de goulot :
   aucun indicateur de foule ne peut y bouger.
2. Le polygone d'issue de l'adaptateur faisait **1,5 m de profondeur**, posé
   devant la porte. Une zone aussi profonde se traverse à la marche : la porte
   laisse passer ≈2× plus que sa largeur ne le permet (6,8 pers/s sur 1,2 m
   à 1,5 m de profondeur, 3,8 pers/s à 0,5 m).
3. Avec la convention v2 de **10 s par tick**, une salle qui se vide en 25 s
   ne produit que deux points de mesure. I4 et I7 étaient donc quantifiés à
   10 s près sur un phénomène de 20 s.

### Décision

1. **Un monde dédié, `crowd_hall`** (22 × 16 m = 352 m², deux issues de
   1,2 m), calibré pour que le bras `règles` produise un pic de densité
   **0,8–1,6 pers/m²** et un vidage de **20–30 s**. Les paramètres sont
   gelés : ce monde sert à toutes les comparaisons C6.
2. **La profondeur du polygone d'issue est un paramètre de l'adaptateur**
   (`exit_depth = 0,5 m` par défaut), plus une constante cachée. Changer
   cette profondeur change le débit : elle est donc nommée.
3. **La durée du tick est un paramètre du run** (`Simulation.tick_seconds`,
   10 s par défaut pour rester compatible), et I4/I7 la suivent. Le scénario
   de foule déclare **2 s**.

### Ce que nous assumons comme écart

- La porte de ce modèle laisse passer **≈3,2 pers/(m·s)** contre ≈1,3 dans la
  littérature. Ce n'est pas corrigé par un réglage caché : le modèle
  `collision_free` ne compresse pas les corps. L'écart est du **même ordre sur
  les trois bras**, donc les comparaisons entre bras tiennent ; les valeurs
  absolues de temps ne sont pas des valeurs de terrain.
- La cible « I7 40–80 s » du plan n'est donc **pas atteignable** avec 60
  agents et des portes crédibles. La valeur mesurée (22–26 s) est publiée
  telle quelle, avec cette explication, plutôt que d'être forcée par une
  porte de 0,5 m ou une horloge inventée.
- Le modèle `social_force` de JuPedSim 1.4 sort de la géométrie
  (`RuntimeError: Point ... is outside of accessible area`) sur ce domaine :
  il n'est pas utilisable ici, et le choix du `collision_free` est consigné.

### Conséquences

- `I6` reste **0 par construction** sur ce scénario (aucune porte ne ferme) :
  ne pas le déclarer comme un résultat.
- Les comparaisons C6 se font sur ce monde, à population et horloge fixes.
  Un run sur `hall_3` ne se compare pas à un run sur `crowd_hall`.

---

## ADR-016 — La perception est consommée avant de décider

_2026-11-18. Statut : accepté (constat de campagne C6)._

### Contexte

`Agent.react` décidait d'abord, puis écrivait les croyances tirées de la
perception (`_consume`). Conséquence mesurée sur le scénario macro à
croyances clivées (60 agents) : **0,50 des décisions visaient une porte que
l'agent venait d'apprendre bloquée**. Un message de t1 (« la sortie A est
bloquée ») et une fumée de t1 ne pesaient donc jamais sur la décision de t1,
puisque le calendrier par fronts ne redécidait plus ensuite.

Ce n'est pas un détail d'implémentation : c'est la moitié des décisions
d'évacuation qui partaient vers la mauvaise porte.

### Décision

1. `Agent._learn(perception)` écrit les croyances **avant** l'appréciation et
   la décision. `Agent._record(...)` garde l'épisode, les marques de plan
   invalidé et l'oubli, après.
2. Le **calendrier ne change pas** : ce sont les fronts qui déclenchent une
   reconsidération, pas l'écriture d'une croyance. Sinon on retomberait sur
   la décision à chaque tick (le coût de la v1).
3. Les critères d'escalade distinguent « **déjà vu avant ce tick** » de « vu
   à l'instant » : `Memory.signal_ticks` + `is_new_signal(genre, valeur, tick)`.
   Sans cette distinction, écrire la croyance en tête de tick rendait toute
   information « déjà vue » et l'hybride ne faisait plus aucune escalade
   (mesuré : 4 → 0 sur le banc bloqué).

### Ce que cela ne tranche pas

Un ordre officiel qui nomme une porte que l'agent croit bloquée reste suivi
par les règles (mesuré : 0,25 des décisions du scénario `contradiction`).
C'est un choix de modèle — l'autorité prime sur la croyance personnelle —
et c'est précisément le cas où l'hybride escalade vers le modèle. Tranché en
C7, avec les chiffres des trois bras sous les yeux, pas avant.

---

## ADR-017 — La réponse du modèle tient jusqu'au prochain fait du monde

_2026-11-18. Statut : accepté (correctif de la campagne C6)._

### Contexte

Mesuré sur le scénario `contradiction` : le bras `hybride` envoyait **0,42**
de ses décisions vers une porte qu'il croyait bloquée, contre **0,00** pour le
modèle seul. Cause : après l'escalade, un simple palier de densité
(`contexte_change`) renvoyait l'agent aux règles, qui refaisaient le choix que
le modèle venait de corriger.

### Décision

Une décision **escaladée** qui bouge (`EVACUER`) tient jusqu'à un front
nouveau, un plan invalidé ou une revue. Une décision escaladée qui ne bouge
pas ne tient pas : garder un « rester » sous fumée ne sort plus (mesuré : 45 à
55 sortis sur 60 avant cette condition).

### Effet mesuré

- décisions du bras hybride : **310 → 108** sur `split`, pour le **même**
  nombre d'appels (87). Une partie du coût de l'hybride n'était pas le modèle,
  c'était la re-décision ;
- sur `contradiction`, la part visant une porte crue bloquée tombe de 0,42 à
  **0,38** — mieux, mais **toujours au-dessus des règles (0,25)**. L'escalade
  ciblée ne corrige donc pas un conflit autorité/croyance qui dure. C'est un
  résultat, pas un chantier à rouvrir sans données nouvelles.

### Corollaire

`scenario_crowd.MAX_TICKS` passe de 20 à 30 (60 s) : à 20 ticks, le scénario
`contradiction` était **censuré** (55/60) et I4 se figeait au plafond. Un zéro
qui ne mesure que la durée du run n'est pas une mesure.
