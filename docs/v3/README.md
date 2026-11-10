# MARÉE v3 — plan de conception

_Statut : proposition de conception, à valider avant implémentation._
_Date : 2026-11-04._
_Périmètre : 12 semaines, puis v3.1._

---

## 1. Pourquoi une v3

La v2 a prouvé quatre choses, et c'est ce qu'on garde :

1. un journal append-only suffit à rejouer un run ;
2. la causalité (`causation_id`) permet de répondre à « pourquoi » ;
3. les décisions événementielles tiennent 60 agents sans saturer le LLM ;
4. les profils, le RAG et la mémoire sont les bons leviers.

Elle a aussi montré ses limites, et c'est ce qu'on jette :

| Limite v2 | Conséquence |
|---|---|
| Un seul plan 60 × 40, trois sorties `A/B/C` codées en dur | impossible de modéliser un mall, un étage, une porte |
| `Point = (x, y)`, un seul `walkable` | aucun multi-étages possible |
| La mémoire sémantique n'atteint jamais le prompt (deux tables) | la mission « comportement humain » n'est pas démontrée |
| `config_hash` sans monde, sans modèle, sans corpus | un run n'est pas identifiable par son contenu |
| 83 % des octets sont des snapshots, `state.json` duplique | stockage non tenable à l'échelle |
| Paramètres déclarés mais jamais lus (`recall_k`, `rag.k`, `temperature`, `api_key`) | « hyper paramétrable » est faux |
| Protocole WebSocket non versionné, sans auth, sans reprise | un front sérieux ne peut pas s'y brancher |
| Pas de CI, packaging non autonome, Docker cassé | pas publiable |

La v3 n'est pas une réécriture pour le plaisir : c'est un **changement de mission**.

---

## 2. Mission

### Mission 1 — le comportement humain (prioritaire)

> Simuler des individus qui se comportent comme des êtres humains en évacuation,
> et montrer que **deux agents du même archétype divergent à cause de leur
> mémoire personnelle**.

C'est le cœur scientifique du projet. Tout le reste le sert.

### Mission 2 — l'aide à la conception (secondaire)

> Permettre à un architecte d'importer ou de générer un bâtiment, de placer
> des sorties et des départs de feu, et de comparer des variantes sur des
> indicateurs de sécurité et de comportement.

C'est une application de la mission 1, pas l'inverse.

---

## 3. Objectifs mesurables

| # | Objectif | Critère d'acceptation |
|---|---|---|
| O1 | Individualité par la mémoire | deux cohortes mêmes traits, histoires différentes → divergence mesurable des sorties et des délais |
| O2 | Temps de pré-mouvement | distribution calibrée sur la littérature (SFPE), test KS |
| O3 | Choix de sortie | les effets distance / congestion / information sociale sont reproduits et ablatables |
| O4 | Influence sociale | un message change la distribution des sorties de façon mesurable |
| O5 | Cohésion du groupe | taux de réunion des proches > seuil, délai borné |
| O6 | Réponse à la fumée | demi-tour / évitement quand la visibilité chute |
| O7 | Rendu Godot | 60 agents, 3D, 60 FPS sur la machine cible |
| O8 | Déterminisme | même graine + même configuration → même hash d'indicateurs |
| O9 | Fiche agent | dossier complet servi en < 50 ms à la demande |
| O10 | Démo | scénario de 3 minutes, rejouable, avec divergence visible |

---

## 4. Non-objectifs

- pas de photoréalisme : des personnages stylisés et lisibles suffisent ;
- pas de certification réglementaire : on cite ISO 20414, on ne la vend pas ;
- pas de CFD temps réel : la fumée est grossière en v3.0 ;
- pas de multi-étages simulé en v3.0 : le schéma le supporte, le moteur le fera en v3.1 ;
- pas de rétrocompatibilité v2 : les runs v2 ne sont pas rejoués par la v3 ;
- pas de base de données, de moteur de foule, de moteur de rendu ou d'auth maison.

---

## 5. Décisions structurantes

| # | Décision | Justification |
|---|---|---|
| D1 | **Comportement d'abord** | la mission 1 est le comportement, pas l'architecture |
| D2 | **Godot est le front de référence** | desktop, 3D, import glTF, MultiMesh |
| D3 | **glTF 2.0 est le contrat de rendu** | Godot, Three.js, Babylon, Blender le lisent |
| D4 | **Assets importés, pas générés** | la qualité est déjà garantie ; on ne devient pas un studio d'art |
| D5 | **Mono-étage en v3.0, multi-étages en v3.1** | le multi-étages n'est pas la priorité |
| D6 | **Fumée grossière, pas de propagation de flammes** | efficace, suffisant pour le comportement |
| D7 | **OpenJev en tête de décision optionnelle** | rapide et calibré, mais évalué avant adoption |
| D8 | **Pas de compatibilité v2** | la v2 a servi à définir ce qu'on ne veut pas |
| D9 | **Stockage : Postgres + pgvector + Parquet/DuckDB + objets + Redpanda** | une matrice, pas une base unique |
| D10 | **Graphify est un outil de développement** | il navigue le code, il ne nourrit pas les agents |

---

## 6. Critères de succès des 3 mois

À la fin de la semaine 12, on doit pouvoir :

1. lancer un scénario mono-étage dans Godot, avec des personnages importés ;
2. cliquer sur une personne et lire sa bio, ses croyances, ses reçus, ses échanges ;
3. voir deux agents du même archétype prendre des décisions différentes et
   expliquer **pourquoi** (mémoire, source, confiance) ;
4. déclencher une fumée et voir la foule réagir (demi-tour, évitement) ;
5. rejouer le run depuis le journal et retrouver le même hash ;
6. produire un rapport de validation sur les quatre phénomènes prioritaires ;
7. comparer trois variantes de placement de sorties.

---

## 7. Index des documents

| Document | Contenu |
|---|---|
| [`architecture.md`](architecture.md) | artefacts, couches, contrats, flux |
| [`comportement.md`](comportement.md) | modèle cognitif, mémoire, individualité, phénomènes |
| [`monde-et-rendu.md`](monde-et-rendu.md) | WorldSpec, IFC, procédural, glTF, Godot, assets |
| [`agents-et-llm.md`](agents-et-llm.md) | registre de politiques, OpenJev, gateway LLM, traces |
| [`feu.md`](feu.md) | fumée grossière, ténabilité, couplage comportement |
| [`donnees-et-api.md`](donnees-et-api.md) | stockage, REST/WS, dossier agent, versioning |
| [`roadmap.md`](roadmap.md) | 12 semaines, jalons, risques, critères |
| [`decisions.md`](decisions.md) | journal des décisions d'architecture (ADR) |
| [`graphify.md`](graphify.md) | intégration de Graphify au développement |

---

## 8. Glossaire

| Terme | Sens |
|---|---|
| **WorldSpec** | description sémantique versionnée du bâtiment (étages, pièces, portes, sorties, dangers) |
| **SimArtifact** | ce que le moteur dérive du WorldSpec (polygones marchables, graphe, capacités) |
| **RenderArtifact** | ce que le front dérive du WorldSpec (glTF + manifeste) |
| **RunStream** | le flux dynamique d'un run (agents, croyances, fumée, métriques) |
| **Policy** | la stratégie de décision d'un agent (`rules`, `hybrid`, `llm`, `decision_head`) |
| **Receipt** | le reçu d'un apprentissage : fait, source, tick, confiance |
| **SharedKnowledge** | faits publics datés et versionnés, lisibles par les agents via perception |
| **Appraisal** | l'évaluation menace / urgence / efficacité / preuve sociale / responsabilité |
| **LevelCoordinator** | le composant qui transfère les agents entre étages (v3.1) |
| **HazardField** | le champ de fumée/chaleur/CO interrogeable par position et tick |
| **Dossier** | la fiche complète d'un agent, configurable par le front |
