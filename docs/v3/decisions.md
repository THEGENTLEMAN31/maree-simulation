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
