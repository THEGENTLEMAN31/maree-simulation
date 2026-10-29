# MARÉE — Cadrage du projet

Oct 13, 2026 · @Jose

> **Ce document est un cadrage daté, pas un état des lieux.** Il a été écrit
> avant la première ligne de code et plusieurs choix y ont été invalidés par
> la mesure. Les sections corrigées le 2026-10-29 portent la mention
> *« corrigé »* ; l'état réel, exigence par exigence, est dans
> `docs/plan-socle.md`, et les résultats mesurés dans
> `docs/resultats/rapport-v2.md`.
>
> Les cinq affirmations qui étaient fausses : (1) le journal **Kafka** n'est
> pas la source de vérité, c'est le JSONL append-only — Kafka est un bus de
> diffusion ; (2) le RAG n'est pas sur **Chroma** mais sur FAISS exact ;
> (3) l'historique n'est pas en **Parquet** mais en JSONL lu par DuckDB ;
> (4) la population n'est pas 15 LLM / 45 règles avec un profil « amis » et
> un modèle OpenRouter, mais 12 LLM / 48 règles sur cinq profils et des
> modèles locaux ; (5) les indicateurs I4/I5 ne sont pas « suivi de meneur »
> et « cohérence temporelle » mais horloge et densité (voir le tableau).

## Résumé et décision

MARÉE sera construit en trois niveaux emboîtés, avec une architecture à deux vitesses : le corps bouge vite, le LLM pense lentement, et l'écart entre les deux est l'objet d'étude du projet.

- **Le monde :** la Fête des Lanternes de Port-Aubel, une esplanade avec trois sorties inégales. Vers 22 h, une fumée apparaît côté sud et personne ne sait vraiment quoi faire.
- **La question :** une foule qui ne sait rien construit-elle une croyance partagée sur la sortie sûre, et cette croyance la sauve-t-elle ou la piège-t-elle ?
- **La promesse technique :** un journal d'événements **append-only (JSONL)** comme source de vérité, Kafka en bus de diffusion best-effort, un rejeu à l'identique sans appel LLM, un Godot qui ne fait que lire le flux.
- **L'ambition portfolio :** montrer que tu sais découpler deux échelles de temps, mesurer une émergence et défendre un résultat négatif.

**Angle business.** Le monde est fictif, donc rien n'est prédictif. L'usage crédible est un banc d'essai pour comparer des stratégies d'annonce et des dispositifs de sécurité, au service d'organisateurs, d'assureurs ou de gestionnaires de lieux. Ce n'est pas une prévision de foule réelle. Pour un portfolio c'est solide ; pour une startup, il faudrait ensuite des données réelles ou un partenaire.

## Question de recherche et hypothèses

La question centrale est testable : la qualité et le moment d'une annonce officielle changent-ils la carte mentale collective de la foule, et donc l'évacuation ?

**Le « contexte commun » en termes observables (B1).** C'est la part des agents qui partagent la même croyance sur deux points : où est le danger, et quelle sortie est sûre. On la compare à la vérité terrain, que le moteur de monde connaît et que les agents ne connaissent jamais.

**Hypothèses, à écrire dans le dépôt avant toute mesure (C5).** Les seuils sont proposés et à ajuster après les runs pilotes.

1. **H1, annonce.** Une annonce claire émise moins de 3 min simulées après la première fumée réduit le temps d'évacuation médian et l'écart croyance/réalité, par rapport à une annonce ambiguë émise après 6 min.
2. **H2, meneur.** La fermeture soudaine de la sortie la plus chargée piège davantage de monde quand la foule suit surtout un meneur que quand chacun décide seul.
3. **H3, temps.** En mode asynchrone, la répartition entre sorties diffère du mode synchrone, parce que les agents qui décident vite atteignent les sorties en premier.
4. **H4, apport du LLM.** La version LLM diffère de la baseline à règles sur l'écart croyance/réalité, mais pas sur le temps d'évacuation. Un résultat contraire reste recevable s'il est démontré (E1).

**Hypothèses de contrôle, aussi préenregistrées.**

- **H5, mémoire (A1).** Un agent qui a reçu un échange préalable choisit plus souvent la sortie recommandée, ou évite celle déconseillée, que le même agent sans cet échange.
- **H6, profils (A3).** Deux profils placés dans la même situation décident différemment, et échanger leurs profils échange leurs décisions.
- **H7, RAG (F1).** Désactiver le RAG augmente l'écart croyance/réalité (I2).

**Ce que le projet ne prétend pas faire :**

- prédire le comportement d'une vraie foule ;
- valider un modèle sur des données réelles ;
- trancher le débat sur la « panique irrationnelle » : il rapporte seulement si ses agents la reproduisent, et pourquoi.

## Le monde

L'esplanade de Port-Aubel pendant la Fête des Lanternes : une scène, des stands, une passerelle, trois sorties. Le scénario de base est identique pour tous les runs.

| Élément | Choix proposé |
| --- | --- |
| Sortie A | Large, c'est l'entrée habituelle de la majorité du public |
| Sortie B | Étroite, au bout de la passerelle, goulot probable |
| Sortie C | Discrète, connue des habitués seulement |
| Danger | Foyer de fumée près des stands sud à 22 h 00, qui s'étend selon une loi simple et déterministe |
| Durée d'un run | Phase préalable de 3 jours simulés, puis 15 min simulées d'évacuation |
| Signal initial | Odeur de fumée perçue seulement près du sud, annonce du haut-parleur à peine audible |
| Vérité terrain | Position et extension de la fumée, état de chaque sortie : connues du moteur, jamais des agents |

**Événements injectables en direct (D3) :** annonce claire, annonce ambiguë, fausse information (« la sortie B est bloquée »), fermeture soudaine d'une sortie.

**Périmètre figé.** Un seul plan, un seul scénario de base, trois sorties. Les variantes passent par la configuration, pas par du code. Tailles de population : 20 agents pour les tests, 60 pour la cible, 150 si le niveau 3 est atteint.

## Les jours d'avant et la mémoire (A1)

> **État au 2026-10-29 : non implémenté.** La mémoire épisodique existe et
> fonctionne (elle se remplit pendant le run), mais la **préhistoire J−3**
> décrite ci-dessous n'est pas encore branchée : aucun run ne commence
> trois jours avant. C'est la tâche A1 de la vague 2 de
> `docs/plan-socle.md`. Le protocole X5 reste donc à jouer.

Pour que la mémoire compte, chaque run commence trois jours simulés avant l'évacuation, puis l'horloge saute jusqu'à 22 h 00 le soir de la fête.

| Jour simulé | Échange préalable | Ce que l'agent retient |
| --- | --- | --- |
| J-3 | Un habitué dit à un visiteur que la sortie C existe et qu'elle évite la passerelle | Le visiteur sait que C existe (information vraie) |
| J-2 | L'agent de sécurité rappelle à une famille que la sortie B se bouche dès qu'il y a du monde | La famille se méfie de B (information vraie) |
| J-1 | Un voisin raconte à une autre famille que la sortie A avait été fermée l'an dernier | La famille se méfie de A (information fausse, utile pour mesurer l'écart croyance/réalité) |

Chaque agent LLM a 2 à 3 échanges avant la fête, soit environ 45 appels de plus par run. Ils passent par les mêmes événements et la même mémoire que l'évacuation, sans mécanisme séparé. L'horloge simulée saute les périodes sans événement, ce qui évite de payer des appels pour rien (C3).

**Test de mémoire (X5, hypothèse H5).** Le même scénario est joué avec et sans les échanges préalables, sur au moins 5 runs par configuration. La preuve attendue est double : l'agent concerné choisit plus souvent la sortie recommandée, ou évite celle dont on lui a dit du mal, quand l'échange a eu lieu ; et son inspection (D2) montre cet échange, vieux de plusieurs jours simulés, cité dans la justification de sa décision.

## Population

**Corrigé le 2026-10-29.** La foule est hybride : **12 agents LLM** portent
les décisions qui comptent, et **48 agents à règles** assurent la densité
(A6), pour 60 agents au total. Le profil « groupe d'amis » n'existe pas dans
le moteur ; il est remplacé par `vendeur`, et les cinq profils réels sont
`securite`, `habitue`, `famille`, `visiteur`, `vendeur`.

| Profil | Priorité | Sait au départ | Type | Tier (A5) |
| --- | --- | --- | --- | --- |
| Famille (2 LLM + 14 règles) | Retrouver l'enfant égaré avant de partir | Seulement son entrée d'arrivée | LLM / règles | grand |
| Agent de sécurité (2 + 2) | Guider, sa parole pèse plus | Les trois sorties et le protocole | LLM / règles | grand |
| Habitué (2 + 6) | Partir vite, par la sortie C | La sortie discrète | LLM / règles | grand |
| Visiteur (4 + 24) | Comprendre avant d'agir | Seulement son entrée d'arrivée | LLM / règles | petit |
| Vendeur (2 + 2) | Tenir son stand | Son étal et ses habitudes | LLM / règles | petit |

**Règle d'attribution des modèles (A5).** Le modèle dépend du rôle et de
l'expérience du profil, jamais d'une catégorie sociale. Le profil porte un
**tier** (`big` / `small`), le YAML choisit le GGUF : `gemma4-e2b` (2,9 Go)
pour le tier grand, `qwen3-0.6b` (378 Mo) pour le petit. Les deux tournent
en local via llama.cpp — **aucun appel à OpenRouter**, contrairement à ce
qui était prévu ici.

**Dérives à tracer (A4, O2).** Sortie de rôle, réponse inexploitable (JSON invalide), absence de réponse, ton « assistant calme et altruiste ». Chaque incident est un événement typé et compté. En cas d'échec, l'agent retombe sur une règle par défaut pour que le monde ne se fige pas.

**Une interface commune.** Chaque agent expose `decide(perception, mémoire) -> intention`. Agents LLM et agents à règles sont interchangeables, ce qui fournit la baseline sans code supplémentaire (E1).

## Base de connaissances (F1, F2)

Le corpus fictif est écrit par le binôme avant la semaine 3 : environ 200 passages de 100 à 200 mots, répartis en cinq collections.

| Collection | Contenu | Accessible à |
| --- | --- | --- |
| Plan et signalétique | Zones, sorties, capacités, panneaux | Tous, selon ce qu'ils voient |
| Consignes de sécurité | Protocole d'évacuation de la fête | Agents de sécurité |
| Annonces | Variantes de l'annonce du haut-parleur : claire, ambiguë, fausse | Tous, à partir de la diffusion |
| Souvenirs des éditions précédentes | Incidents, sorties utilisées, rumeurs | Habitués, et familles qui en ont entendu parler |
| Savoir des profils | Ce que chaque profil sait au départ | Le profil concerné |

**Accès contrôlé par profil.** Chaque passage porte une date de disponibilité simulée et la liste des profils autorisés à le retrouver (décision 15). Un agent ne retrouve donc jamais ce qu'il n'aurait pas pu savoir à cet instant, ce qui alimente le contrôle de cohérence temporelle (C6).

**Preuve que le RAG compte (X7, hypothèse H7).** Le même scénario est joué avec le RAG activé, puis désactivé (l'agent n'a alors que son prompt), sur au moins 5 runs par configuration. On compare I2 et la part des décisions dont la justification cite un passage retrouvé.

**Qualité de la récupération (F2).** Pour 30 décisions tirées au hasard par type de run, le binôme note chaque passage retrouvé (pertinent ou non), et le rapport donne la précision sur les 3 premiers résultats. Un score de similarité sous un seuil à calibrer déclenche un événement de récupération douteuse : c'est ainsi que le système s'aperçoit d'une information mal retrouvée (question Q5 du jury).

## Architecture

Le journal Kafka est le seul endroit où l'état du monde s'écrit ; tous les autres composants le lisent ou y publient.

&#91;embedded content: architecture · 8 composants, un journal central\]

Lecture : les agents décident rarement, le moteur exécute à chaque pas, et seul le journal fait foi. Le moteur avance à pas fixe défini en configuration. Les agents LLM ne sont sollicités que sur déclencheur : un signal nouveau perçu, un changement d'état de leur sortie, ou 20 s simulées écoulées.

**Topics proposés.**

- `world.events` : événements du monde, une seule partition pour garantir l'ordre du registre
- `agent.decisions` : intentions, justifications, passages RAG retrouvés, coût
- `metrics.indicators` : I1 à I4 recalculés en continu
- `control.commands` : événements injectés depuis Godot
- `dlq.invalid` : événements non conformes, isolés sans arrêter la simulation (F4)

**Granularité des événements (C1).** Trois choix, faits pour tout pouvoir rejouer sans saturer le flux.

- Un événement par fait : perception d'un signal, message entre agents, décision LLM (intention, justification, passages RAG), changement de croyance, arrivée dans une zone, sortie du site. C'est de l'ordre du millier de messages par run.
- Un instantané agrégé des positions par seconde simulée, en un seul message pour tous les agents : 900 messages pour un run de 15 minutes. Godot interpole entre deux instantanés.
- Aucun message par agent et par pas. À 10 par seconde pour 60 agents, cela ferait environ 540 000 messages par run, sans rien apporter aux indicateurs ni au rejeu.

Une granularité plus grossière qu'une seconde ferait saccader la scène et fausserait la mesure de densité au goulot (I3).

**Stockage justifié par besoin d'accès (F3).** *Corrigé le 2026-10-29* :
les quatre stockages réels, et le besoin d'accès qui les justifie.

| Donnée | Où | Pourquoi |
| --- | --- | --- |
| Flux d'événements | **JSONL append-only**, un fichier par run (`runs/<id>/events.jsonl`) | Source de vérité, rejeu sans infrastructure, lisible à l'œil. Kafka est un bus de **diffusion** best-effort, jamais la persistance : un broker mort ne perd rien |
| État courant du monde | Mémoire du moteur + instantanés `world.snapshot` dans le même journal | Accès à chaque pas pour le rendu, reconstructible depuis le journal |
| Historique des runs | **Les mêmes JSONL, interrogés par DuckDB** (`read_json_auto`) | Volume modéré, lecture analytique, requêtes reproductibles (F5) sans exporter un second format |
| Base de connaissances (RAG) | **FAISS exact + JSON + `mean.npy`** dans `data/rag` | Quelques centaines de passages, recherche exacte, correction d'anisotropie mesurée |

Pas de Parquet, pas de Chroma, pas de Postgres : chacun ajouterait un format
ou un service sans changer le besoin d'accès. Les requêtes F5 vivent dans
`scripts/queries/` et lisent les JSONL directement.

## Décisions à figer dès le jour 1

Seize décisions d'architecture doivent exister avant la première ligne de simulation, parce que les ajouter plus tard oblige à tout reprendre ou rend la mesure impossible.

| # | Décision | Ce qui casse si tu l'ajoutes après | Exigences |
| --- | --- | --- | --- |
| 1 | Le journal d'événements est la source de vérité. L'état se reconstruit depuis le log, et chaque sortie LLM y est enregistrée (modèle, version, graine, prompt, tokens, latence). | Une sortie LLM non enregistrée est perdue : le rejeu sans appel LLM devient impossible. | E3, F6, E4 |
| 2 | Double horodatage sur chaque événement : instant simulé de production, instant simulé de traitement, heure réelle. | Il faut rouvrir tous les schémas, et aucun décalage ne se mesure rétroactivement. | C3, C6, C7 |
| 3 | Déterminisme : une graine par run et par agent, ordre canonique dans un pas (tri par identifiant d'agent), aucune horloge système dans la logique du monde. | Un non-déterminisme caché se traque très mal après coup, et le rejeu ne sera jamais identique. | E3 |
| 4 | Enveloppe d'événement commune et versionnée : run\_id, event\_id, type, schema\_version, agent\_id, t\_prod, t\_trait, causation\_id. | Sans causation\_id, impossible de remonter aux échanges qui précèdent une bascule de l'indicateur. | F4, F6, B4 |
| 5 | Identité de run : run\_id plus hash de la configuration (nombre d'agents, mode, modèles, graines, scénario). | Les 5 runs par configuration ne s'agrègent pas proprement. | E2, F5 |
| 6 | Interface unique `decide(perception, mémoire) -> intention` pour agents LLM et agents à règles. | Baseline et agents LLM divergent, la comparaison perd sa validité. | A6, E1 |
| 7 | Passerelle LLM unique : tous les appels y passent (quotas, retries, timeout, repli sur règle, journal de coût). | Mesurer le coût après coup oblige à retoucher chaque appel. | E4, A4, O7 |
| 8 | Frontière boucle rapide / boucle lente : le moteur de déplacement n'exécute que des intentions. | Passer du graphe à l'espace continu sans réécrire les agents n'est possible que si cette frontière existe. | Échelle de repli |
| 9 | Godot est un consommateur pur du flux : aucune logique de simulation dedans. | Si Godot calcule un état, le rejeu ne reproduit plus la même visualisation. | D1, E3 |
| 10 | Un ordonnanceur synchrone/asynchrone séparé des agents, avec perception figée à l'instant de décision. | Le mode de temps s'infiltre dans le code des agents et ne se greffe plus. | C4, C5, C6 |
| 11 | Nombre d'agents et tous les paramètres dans un fichier de configuration, rien en dur. | Des valeurs en dur partout, alors que C2 interdit toute modification de code. | C2 |
| 12 | Traçabilité du RAG : chaque décision journalise les passages retrouvés (identifiants et scores). | La qualité de la récupération ne peut plus être évaluée a posteriori. | F1, F2 |
| 13 | Hypothèses et graines préenregistrées dans le dépôt, datées, avant toute expérience. | Le jury peut soupçonner des hypothèses écrites après les résultats. | C5, E2 |
| 14 | Versions figées : lockfiles, version exacte des modèles locaux, images Docker. | Un run ancien ne se rejoue plus après une mise à jour. | E3, livrable dépôt |
| 15 | Chaque passage du corpus RAG porte une date de disponibilité simulée et la liste des profils autorisés à le retrouver. | Un agent peut retrouver une information qu'il n'aurait pas pu connaître, C6 ne se vérifie plus, et ré-indexer le corpus est long. | F1, C6, A1 |
| 16 | Chaque événement d'indicateur référence les offsets Kafka (topic, partition, plage) des événements qui l'ont produit. | Remonter d'une valeur affichée aux événements bruts devient une reconstruction approximative, et la vue de causalité de B4 n'est plus possible. | F6, B4, D2 |

**Le test qui protège le reste.** Un test automatique de rejeu (même log, mêmes indicateurs, comparés par hash) tourne à chaque commit dès la semaine 2. Si ce test passe au vert en continu, les décisions 1 à 4 et 9 tiennent.

## Indicateurs, baseline et protocole

Cinq indicateurs sont calculés pendant le run et affichés à côté de la scène, synchronisés avec elle (B2).

**Corrigé le 2026-10-29.** Les indicateurs livrés sont ceux du moteur
(`src/maree/metrics/indicators.py`), pas ceux esquissés ici. I4 et I5 ne
mesurent pas ce qui était prévu ; I6 et I7 ont été ajoutés.

| Indicateur | Ce qu'il mesure | Calcul |
| --- | --- | --- |
| I1 Consensus | Accord sur la sortie jugée sûre | Part de la croyance majoritaire, sur les agents informés |
| I2 Entropie | Dispersion des croyances | Entropie de Shannon normalisée (0 = tous d'accord, 1 = tous perdus) |
| I3 Évacuation | Résultat physique | Part des agents sortis (fait physique, distinct d'une décision) |
| I4 Horloge | **Quand** — et non combien de temps | `tick × 10 s`, **censuré à `max_ticks`** : à lire avec I3 |
| I5 Densité | Encombrement maximal | Pic de densité par noyau de 2 m (la grille de 1 m saturait à 2,0) |
| I6 Écart de croyance | Distance à la vérité terrain | Part des agents croyant en une sortie fermée ; **0 par construction si aucune sortie ne ferme** |
| I7 Délai | **Combien de temps** | Premier signal de danger → dernier sorti ; défini sous censure |

La « cohérence temporelle » n'est pas un indicateur affiché : c'est un
vérificateur (C6) qui produit un compteur de violations dans `run.ended`.

**Cohérence temporelle (C6).** Un vérificateur parcourt chaque décision et contrôle que tout ce qu'elle cite (perceptions, messages, passages RAG) était disponible à l'instant de la décision : date de production et, pour un message, date d'arrivée inférieures ou égales. Chaque écart devient un événement de violation compté dans I5, et le même vérificateur tourne en test automatique. En mode asynchrone, une décision appliquée sur un état déjà périmé n'est pas une violation : son décalage est mesuré à part (C7).

**Traçabilité d'un indicateur (F6) et inspection d'un agent (D2).** Chaque valeur d'indicateur publiée référence la plage d'offsets Kafka des événements qui l'ont produite (décision 16). Dans Godot, un clic sur un indicateur liste ces événements bruts. Un clic sur un agent affiche sa mémoire, la justification de sa dernière décision et les passages RAG utilisés, ou, pour un agent à règles, son état et la règle appliquée.

**Distinguer émergence et ressemblance (B3, O6).** Trois contrôles négatifs répondent à la question du jury « mesurez-vous l'émergence ou la ressemblance des réponses d'un même modèle ? ».

1. Communication désactivée : I1 doit chuter.
2. Annonce neutre sans contenu : I2 ne doit pas baisser.
3. Diversité des justifications (distance entre embeddings), comparée entre agents d'un même modèle et de modèles différents.

Si I1 monte sans communication, c'est un artefact du modèle, et il faut le rapporter.

**Baseline (E1).** Force sociale (Helbing) plus choix de sortie par proximité et visibilité, mêmes scénarios, mêmes graines.

| Expérience | Levier | Configurations | Indicateurs |
| --- | --- | --- | --- |
| X1 Annonce | Clarté et moment | Claire avant 3 min vs ambiguë après 6 min | I2, I3 |
| X2 Fermeture de sortie | Sortie A fermée 5 min après la première fumée | Avec meneurs vs sans meneur | I3, I4 |
| X3 Temps | Mode d'exécution | Synchrone vs asynchrone, mêmes scénarios | I1, I3, coût, décalage |
| X4 Apport du LLM | Type d'agent | LLM vs baseline à règles | I1 à I4 |
| X5 Mémoire (A1) | Échanges préalables des jours d'avant | Avec vs sans les échanges | Sortie choisie par l'agent concerné, justification citant l'échange |
| X6 Profils (A3) | Profil de l'agent | Même stimulus, profils d'origine vs profils échangés entre deux agents | Décision : sortie choisie, rester ou partir |
| X7 RAG (F1) | Base de connaissances | RAG activé vs désactivé | I2, part des décisions citant un passage retrouvé |

**Règles statistiques.** Au moins 5 runs par configuration, 10 si le budget le permet. Médiane et écart interquartile plutôt que moyenne, test non paramétrique (Mann-Whitney) avec la réserve que n est petit. Chaque run est rejouable depuis le log seul, et un hash des indicateurs vérifie l'identité du rejeu (E2, E3).

**Requêtes reproductibles (F5).** Tous les tableaux et figures du rapport sont produits par des requêtes SQL versionnées dans le dépôt, exécutées sur l'historique en Parquet avec DuckDB. Exemple : comparer I3 sur les 10 runs de X1.

## Échelle de repli

Le même socle tourne à chaque niveau : agents, Kafka, indicateurs et rejeu ne changent pas, seuls le moteur de déplacement et la scène Godot évoluent. Un niveau atteint n'est jamais jeté.

| Niveau | Ce que tu livres | Population | Critère de validation | Échéance |
| --- | --- | --- | --- | --- |
| 1. Graphe | Esplanade en environ 12 zones reliées, déplacement de zone en zone en temps discret, socle complet | 20 puis 60 | Rejeu identique, socle A à F validé, démo live | Fin S4 |
| 2. Continu | Déplacement continu, évitement simple, murs, goulot de la passerelle visible | 60 | 60 agents à 20 images/s dans Godot, rejeu identique, 3 runs sans plantage | Fin S5 |
| 3. Dense | Force sociale complète, deux tailles de population, décalage sous charge mesuré | 60 et 150 | Niveau 2 validé avec de la marge | S7 si en avance |

**Règle de bascule.** Si le niveau 2 ne passe pas son critère à la fin de la semaine 5, tu gèles le niveau 1 et tu consacres les semaines 6 à 8 aux expériences et au rapport. Ce n'est pas un échec : le socle reste complet, et les excellences B4, C7 et C8 restent possibles au niveau 1.

**Pourquoi ce passage est peu coûteux.** Il ne l'est que si les décisions 6 et 8 du tableau précédent sont tenues : une interface d'intention unique, et un moteur de déplacement qui se contente d'exécuter.

## Plan des 8 semaines

Le planning tient en cinq phases séparées par quatre jalons, et G3 est le seul qui décide du repli.

&#91;embedded content: plan · 8 semaines, 5 phases, 4 jalons\]

Seul G3 dépend d'un résultat technique incertain. S'il échoue, le niveau 1 est gelé et les semaines 6 à 8 restent intactes pour les expériences et le rapport.

## Budget d'appels et sobriété

Estimation à confirmer par mesure en semaine 3 : environ 450 appels LLM par run, soit 15 agents LLM × environ 25 décisions déclenchées par des événements, avec au plus une décision toutes les 20 s simulées, plus environ 45 appels pour les jours d'avant (A1).

- **Local (Gemma, environ 50 tokens/s) :** environ 370 appels par run, soit à peu près 18 minutes en séquentiel. À vérifier par mesure.
- **OpenRouter :** environ 75 appels par run, réservés aux profils à expérience (sécurité, habitués). Sur environ 60 runs (X1 à X3 et X5 à X7, 10 runs chacun), cela fait 4 500 appels, soit 5 jours de quota à étaler. Les quotas des modèles gratuits changent souvent : à vérifier au démarrage.
- **Baseline :** aucun appel.

**Levier de sobriété (E5).** Comparer la configuration mixte (petit modèle local plus grand modèle sur les profils clés) à une configuration où tous les agents utilisent le grand modèle, à apport comparable sur I2 et I3.

**Mesure du coût (E4, O7).** Appels, tokens, latence, énergie locale avec CodeCarbon, estimation des appels d'API avec EcoLogits, le tout journalisé par la passerelle LLM.

## Risques et réponses

Le risque le plus grave n'est pas technique : c'est un LLM qui joue la foule trop calme, trop rationnelle et trop altruiste.

| Risque | Réponse |
| --- | --- |
| Agents LLM trop calmes ou altruistes | Profils ancrés (priorités, peur comme variable du monde), taux de sortie de rôle mesuré, comparaison à la baseline. Si le biais reste, c'est un résultat à rapporter. |
| Boucle lente trop lente pour le visuel | Décisions déclenchées par des événements, intentions mises en cache, repli sur règle en cas de timeout |
| Godot qui dérive vers un jeu vidéo | Cercles colorés, pas de sprites, une semaine de budget visuel au total |
| Quota d'API qui tombe pendant la démo | Rejeu d'un run enregistré, Gemma local en secours |
| Rejeu qui n'est pas identique | Déterminisme, test de rejeu automatique à chaque commit dès S2 |
| Dispersion trop forte entre runs | Graines fixes par scénario, médiane et écart interquartile, réduction du nombre d'agents LLM |
| Indicateur qui ne distingue pas l'émergence | Contrôles négatifs avant toute conclusion |
| Dérive vers le niveau 3 | Critère daté à la fin de S5, pas de négociation |
| Charge mal répartie dans le binôme | Découpage par bloc dès la semaine 1 (à confirmer) |

## Excellence : B4, C7, C8

Les trois excellences sont prévues en semaine 7, sur des runs déjà enregistrés, et ne demandent presque aucun développement si les décisions du jour 1 sont tenues. Dans l'ordre de coût croissant : C8, C7, B4.

| Exigence | Ce qui est livré | Comment |
| --- | --- | --- |
| C8 | Deux tailles de population en soutenance | Deux runs enregistrés, 20 et 60 agents, rejoués côte à côte, avec comparaison de I1, I3 et du coût ; 150 agents si le niveau 3 est atteint |
| C7 | Décalage entre un événement et sa prise en compte dans les indicateurs, et son évolution sous charge | Le champ t\_trait moins t\_prod est déjà journalisé ; on trace sa distribution (médiane et 95e centile) pour 20 et 60 agents, avec et sans rafale d'événements injectés, en mode asynchrone |
| B4 | Pour une variation marquée de I1 ou I2, la chaîne d'échanges qui l'a précédée | Une vue de causalité remonte, via causation\_id et les offsets sources de l'indicateur (décision 16), jusqu'aux messages, décisions et passages RAG ; deux ou trois cas sont argumentés dans le rapport |

## Correspondance avec le socle

Les 32 exigences du cahier des charges (20 du socle, 9 Standard, 3 Excellence) ont chacune un emplacement dans le projet et une preuve livrée.

| Exigence | Niveau | Où dans le projet | Preuve livrée |
| --- | --- | --- | --- |
| A1 | Socle | Jours d'avant, mémoire event-sourcée | X5 : l'échange ancien change la décision |
| A2 | Socle | Messages en langage naturel qui mettent à jour la croyance du destinataire | Contrôle « communication désactivée » : I1 chute |
| A3 | Standard | Profils différenciés | X6 : profils échangés, décisions échangées |
| A4 | Standard | Dérives typées dans le journal, repli sur règle | Compteurs par type de dérive dans le rapport |
| A5 | Standard | Gemma local et grand modèle OpenRouter selon rôle et expérience | Table de population, comparaison E5 |
| A6 | Standard | 15 agents LLM et 45 agents à règles | Justification de la répartition dans le rapport |
| B1 | Socle | Carte mentale collective définie en termes observables | Section Question de recherche |
| B2 | Socle | I1 à I5 calculés pendant le run, affichés à côté de la scène | Démo live |
| B3 | Socle | Contrôles négatifs : communication coupée, annonce neutre | Résultats des contrôles dans le rapport |
| B4 | Excellence | Vue de causalité | Deux ou trois cas argumentés |
| C1 | Socle | Granularité des événements justifiée | Volumétrie chiffrée : 900 instantanés contre 540 000 messages |
| C2 | Socle | Fichier de configuration | Runs à 20 puis 60 agents sans changer le code |
| C3 | Socle | Double horodatage dans chaque événement, horloge simulée avec sauts | Champs t\_prod et t\_trait |
| C4 | Socle | Ordonnanceur synchrone ou asynchrone choisi au lancement | X3 |
| C5 | Standard | X3, hypothèse H3 écrite avant la mesure | Comparaison des deux modes sur le phénomène et le coût |
| C6 | Standard | Vérificateur de cohérence temporelle | I5, test automatique |
| C7 | Excellence | Distribution du décalage t\_trait moins t\_prod sous charge | Courbe de décalage pour 20 et 60 agents |
| C8 | Excellence | Deux tailles de population rejouées côte à côte | Démo en soutenance |
| D1 | Socle | Godot consommateur pur du flux, agents colorés selon leur croyance | Démo live |
| D2 | Socle | Inspection : mémoire, justification, passages RAG ou règle appliquée | Démo live |
| D3 | Socle | Quatre événements injectables depuis Godot | Démo live |
| E1 | Socle | Baseline à règles (force sociale) | X4 |
| E2 | Socle | 5 runs ou plus par configuration, médiane et écart interquartile | Tableaux du rapport |
| E3 | Socle | Rejeu depuis le journal seul, test automatique | Hash des indicateurs identique |
| E4 | Socle | Coût journalisé par la passerelle LLM | Bilan de sobriété |
| E5 | Standard | Configuration mixte contre tout en grand modèle | Comparaison à apport égal sur I2 et I3 |
| F1 | Socle | Corpus RAG de cinq collections, accès par profil | X7 : RAG activé contre désactivé |
| F2 | Socle | Échantillon de 30 décisions notées par type de run | Précision sur les 3 premiers résultats |
| F3 | Socle | Tableau de stockage justifié par besoin d'accès | Section Architecture |
| F4 | Socle | Schémas versionnés, file des événements invalides | Compteur d'événements isolés |
| F5 | Standard | Requêtes SQL versionnées sur l'historique | Tableaux et figures du rapport |
| F6 | Standard | Offsets sources référencés par chaque indicateur | Clic sur un indicateur : événements bruts |
