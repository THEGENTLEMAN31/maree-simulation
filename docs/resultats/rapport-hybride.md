# MARÉE — rapport hybride

_Projet 5A IABD · monde 02 · Fête des Lanternes de Port-Aubel_
_31 octobre 2026_

> **Ce document est le rapport demandé par le cahier des charges**, dans les
> trois formes qu'il impose : une **partie technique** (architecture et
> choix justifiés, architecture de données, modèle de temps, contraintes
> des LLM gratuits, articulation simulation / Kafka / Godot), une **partie
> scientifique rédigée comme un mini-article**, et un **bilan de
> sobriété**. Il se termine par les réponses aux **six questions** que le
> jury posera.
>
> Il ne remplace pas les notes de chantier : `docs/plan-socle.md` dit où en
> est chaque exigence, `docs/audit-consigne-2026-10-31.md` dit ce qui
> manquait au moment de l'audit, `AGENTS.md` garde les pièges. Ici, on
> assemble — c'est le seul document qui se lit seul.

**En une phrase.** MARÉE simule soixante personnes sur une esplanade dont
trois sorties ne sont pas également connues : chaque agent se construit une
croyance sur la sortie sûre, la partage, et cette croyance peut le sauver
ou le piéger. On mesure la croyance (consensus, entropie, écart à la
vérité), l'issue physique (part sortie, délai) et le coût (appels, jetons,
temps, énergie).

**Les trois résultats que nous défendons.**

1. **Une annonce vague ne ralentit pas la foule : elle la bloque.** À
   délai égal, une consigne claire fait sortir 60/60 ; la même annonce en
   termes ambigu laisse 7 runs sur 10 censurés au plafond de temps, avec
   deux personnes sur soixante encore dehors de la sortie à la fin
   (X1, 5 graines par bras, p = 0,0185 sur le délai).
2. **Le LLM ne fait pas mieux évacuer, et il coûte cher.** Sur le scénario
   du piège, les soixante agents à règles sortent 55/60 pour 9,6 s de
   calcul ; les soixante agents LLM sortent 40/60 pour 520 appels et
   234,8 s. Le résultat inverse celui que nous avions publié avant de
   corriger une fuite de connaissance (X4).
3. **Le gain de sobriété vient du protocole et de la répartition, pas de
   la taille du modèle.** Donner au petit modèle une règle écrite et deux
   drapeaux oui/non coûte 41 % de jetons de moins que de le laisser
   répondre en JSON libre — avec le grand modèle (X12). Le petit modèle
   *applique* une politique ; le grand la *juge*.

---

# Partie I — Technique

## 1. Le problème que l'architecture résout

La v1 décidait à chaque tick. Soixante agents × trente-six ticks = **2 160
appels LLM par run**, à 0,36 décision/s : une heure quarante de calcul pour
six minutes simulées. Ce n'était pas un problème de modèle mais de
**fréquence**.

Une foule ne réfléchit pas vingt fois par seconde, et surtout elle ne
réfléchit pas *en même temps*. Trois leviers, appliqués ensemble :

| levier | effet mesuré |
|---|---|
| décisions **événementielles** (on ne décide que sur changement) | 271 décisions au lieu de 2 160 sur le scénario du piège (90 ticks, 60 agents) |
| population **hybride** (12 LLM + 48 règles) | le coût tombe d'un facteur 5, et les règles servent de référence (X4) |
| `parallel = 4` dans llama.cpp | 1,43 décision/s, de quoi absorber une pointe de quatre appels simultanés |

Le piège de ce levier, et il a fallu le mesurer pour le voir : un
**déclencheur de niveau** ne fait pas une décision événementielle. La fumée
reste visible jusqu'à la fin du run ; si `smoke_visible` déclenche une
décision, soixante agents redécident à chaque tick et l'on a reconstruit le
coût de la v1. Fumée, annonce et fermeture d'issue sont donc des **fronts**,
mémorisés par agent dans `known_signals` : un agent décide **une fois** par
signal nouveau, et le signal reste dans sa perception.

## 2. Trois horloges, un seul état du monde

```
physique    0,05 s   JuPedSim 1.4 : positions, contacts, files
cognition  10,00 s   LangGraph + LLM : mémoire, RAG, décision
rendu       0,10 s   Godot : interpolation entre deux instantanés
```

**Le mouvement n'attend jamais la pensée.** Un agent qui réfléchit pendant
2,8 s de temps réel continue d'avancer : c'est ce qui produit des
trajectoires crédibles malgré un modèle lent. JuPedSim fait soixante agents
sur cent secondes simulées en 0,06 s, soit **1 761 fois le temps réel** —
la foule ne coûte rien, seul le LLM coûte.

Deux règles tiennent l'ensemble :

- **perception figée** : tous les agents perçoivent le même instant T, même
  si leurs réponses arrivent à des moments différents. Sans cela, celui qui
  décide en dernier verrait un monde que les autres n'ont pas vu, et deux
  runs identiques divergeraient ;
- **ordre canonique** : les décisions s'appliquent par `agent_id`
  croissant, jamais dans l'ordre d'arrivée des réponses. Vérifié : en
  passant de 1 à 4 appels concurrents, le temps mural baisse de 34,0 à
  20,9 s (×1,63, p = 0,0117) **sans que I1, I5 ni I7 bougent** (X3).

Le déterminisme n'est pas un luxe, c'est la condition du rejeu : aucune
horloge système dans la logique du monde (le temps est un entier), graines
dérivées par **SHA-256** et jamais par `hash()` (salé par processus :
`PYTHONHASHSEED` aurait fait diverger deux runs « identiques »), tirage
unique semé pour le placement.

## 3. Architecture de données

Quatre stockages, chacun avec un rôle, et **aucun ne remplace le journal**.

| stockage | contenu | rôle | volume mesuré |
|---|---|---|---|
| `runs/<id>/events.jsonl` | tous les événements, append-only | **source de vérité** | 1 023 événements / 1,7 Mo par run de 60 agents |
| `runs/<id>/state.json` | dernière valeur de chaque fait du monde | lecture instantanée | **70 581 octets** contre 1 777 302 de journal (77 % d'instantanés) |
| `data/rag/` | 215 passages + vecteurs bge-m3 | récupération | 0,9 Mo |
| Redpanda | mêmes événements, en flux | diffusion temps réel | 1 002 messages sur 4 topics pour un run de 1 023 |

Chaque événement porte `seq` (ordre canonique, le tri suffit), `t_prod`
(moment où le fait se produit), `t_trait` (moment où il est traité),
`t_real` (temps mural, **journal seulement**), `causation_id` (d'où il
vient) et `schema_version`. Sur le run versionné `demo_replay`, **820
événements sur 1 023** portent un `causation_id`, formant **160 chaînes**
distinctes.

**Pourquoi un journal et pas une base.** Un journal append-only se rejoue ;
une table se met à jour et perd l'historique. Le rejeu (`maree replay`) ne
fait aucun appel réseau : il re-parse la sortie brute de chaque décision,
vérifie que l'intention appliquée est celle du modèle, recalcule
l'empreinte des indicateurs. Il distingue trois choses qu'on confond
toujours : une **normalisation** (`follow C` lu comme `go_exit C`), un
**repli règles** (annoncé, compté à part) et une **divergence** (le vrai
défaut). Sur `demo_replay` : 49/49 décisions concordantes, 3 replis
annoncés, `ok: true`.

**`state.json` est atomique** (`os.replace`) et ne garde que la dernière
valeur : un client peut lire pendant qu'un run écrit, il voit un JSON
complet ou l'ancien, jamais un fichier tronqué. Le « dernier run » se trie
par `mtime`, pas par nom — les identifiants contiennent une graine et un
hachage.

**Requêtes reproductibles.** Les tableaux de ce rapport sont produits par
des requêtes `.sql` versionnées (`queries/`), exécutées par DuckDB. Pas de
Parquet : le journal est du JSONL, et le lire avec `read_json_auto`
(inférence de schéma) est un piège silencieux — `data` change de forme à
chaque type d'événement, l'inférence finit par typer `data` en JSON
structuré, et `json_extract` renvoie des guillemets ou échoue. DuckDB lit
donc **ligne par ligne** et chaque requête extrait ce qu'elle veut :
449 970 événements sur 451 runs en 3,4 s pour la requête la plus large.

## 4. Le modèle de temps

Le temps du monde est un entier : `tick`, où un tick vaut **10 s
simulées**. Un run de 72 ticks = 12 minutes.

Trois notions distinctes, et c'est leur séparation qui rend la mesure
honnête :

- **`t_prod` / `t_trait`** — un événement se produit à `t_prod`, il est
  traité à `t_trait`. En mode synchrone ils coïncident (c'est la
  définition du mode). En asynchrone, la décision est lancée au tick de la
  perception et ramassée au tick où elle aboutit : la différence est la
  latence, et elle est mesurée, pas tirée d'une graine.
- **mode `sync`** — barrière à chaque tick : tout le monde perçoit T, tout
  le monde décide, le monde avance. Reproductible, mais un agent attend
  les autres.
- **mode `async`** — chaque agent décide à son rythme et sa décision
  s'applique **quand la réponse arrive**. L'horloge est cadencée
  (`tick_delay_s = 0,25` s) : sans cadence, la boucle tournerait plus vite
  que le modèle et aucune réponse n'arriverait jamais. 3 s de LLM = 12
  ticks. Ce n'est pas une latence inventée, c'est la latence mesurée
  convertie par une cadence déclarée.

**Le décalage, mesuré, sous charge** (X10, 5 graines) : `lag_llm` — tick où
l'événement se produit → tick où l'agent le perçoit — vaut **0 en
synchrone**, **5,5 à 20 agents**, **8,0 à 60 agents**. L'indicateur, lui,
bouge 1,5 à 3,5 ticks après l'événement : c'est un agrégat, il attend
qu'assez d'agents aient bougé, et à 60 agents il en faut plus qu'à 20.

**Deux pièges corrigés grâce à ce mode.** (a) Une vérification de cohérence
qui lit l'état **courant** au lieu de l'état **perçu** ne se voit jamais en
synchrone (la décision s'applique dans le tick où elle est perçue) et
fabrique des violations fantômes en asynchrone — 12 dans un run de test.
On ne vérifie donc un signal que si l'agent l'a perçu. (b) Une injection
appliquée au milieu d'un tick serait vue par certains agents et pas
d'autres : les commandes du client sont drainées **en tête** du tick
suivant, et `control.injection` est journalisée **avant** l'événement
qu'elle provoque.

## 5. Les contraintes des LLM « gratuits », et ce qu'elles imposent

Le projet tourne **entièrement en local** : aucun appel d'API distante,
aucun quota à consommer. Ce n'est pas un choix de confort.

| contrainte | valeur réelle | conséquence sur l'architecture |
|---|---|---|
| VRAM | RTX 3050, **4 096 Mo** | deux modèles + un modèle d'embeddings, mesurés à **2 691 Mo** |
| contexte | 4 slots × 2 048 tokens (`ctx-size = 8192`) | un prompt réel fait ~700 tokens + 256 de sortie : un `ctx-size` de 4 096 rejetait les prompts |
| latence | **2,8 s** par décision, 0,69 décision/s en séquence, **1,94** à 4 en parallèle | décisions événementielles obligatoires, `max_concurrency = 4` |
| budget de sortie | `max_tokens = 256`, raisonnement **coupé** | sans cela un modèle « réfléchissant » émet ~460 tokens de raisonnement : 9 s par décision au lieu de 2,8 |
| modèle d'embeddings | `bge-m3`, BERT, **pooling CLS** | le mean pooling est faux ici, et les vecteurs sont anisotropes (voir §9) |
| noms de modèles | le routeur normalise les points en tirets | `qwen3-0.6b` → 404 ; il faut écrire `qwen3-0-6b`, le nom **annoncé** |

La conséquence la plus intéressante n'est pas technique. Elle est
**scientifique** : ces contraintes forcent une population hybride, et une
population hybride permet de mesurer ce que le LLM apporte *par rapport*
aux règles — c'est-à-dire de répondre à E1 avec une vraie référence, pas
avec une paille.

**Le quota n'est pas un risque théorique.** Il a été éprouvé une fois :
un serveur llama.cpp éteint produit des runs qui *ressemblent* à des
résultats — 43 « appels LLM » en 11 s, tout en repli silencieux. Depuis,
`run.ended` compte `llm_ok`, la CLI crie quand `llm_ok == 0`, et chaque
repli porte une cause nommée. Un run à zéro succès n'est pas un run
hybride, et le journal le dit.

**Le rejeu est le plan B de la démo** : un run enregistré se rejoue sans
GPU, sans serveur, sans réseau (`make replay-demo`, `make replay-pair`).

## 6. Articulation simulation / Kafka / Godot

```
        moteur (3 horloges)
              │
              ▼
      journal JSONL ──────────────► rejeu, requêtes SQL, indicateurs
              │
        ┌─────┴─────┐
        ▼           ▼
   bus mémoire   Redpanda (démo)
        │           │
        └─────┬─────┘
              ▼
        trames JSON (WebSocket 8765)
              ▼
        Godot · chroniqueur
```

- **Le bus n'est pas dans le chemin de la mesure.** Les campagnes tournent
  en `bus.backend=memory` ; Redpanda sert la démonstration temps réel, et
  il est prouvé par un run dédié (1 002 messages sur 4 topics pour
  1 023 événements, les 21 instantanés n'étant pas publiés). Kafka est donc
  vrai de l'architecture, pas des chiffres des tableaux — nous préférons
  l'écrire que le laisser croire.
- **Le client ne dépend jamais du moteur.** Une fonction pure
  `frame_for(event)` transforme un événement en trame autoportante ;
  `docs/protocol-ui.md` décrit les douze types (`hello`, `world`,
  `decision`, `belief`, `message`, `heard`, `evacuated`, `snapshot`,
  `indicators`, `narrative`, `event`, `end`) avec un exemple réel chacun.
  **Aucun événement n'est filtré** : ceux qui n'ont pas de trame dédiée
  passent en `event`, enveloppe comprise. C'est le contrat à donner à
  quelqu'un qui écrit un autre client : il n'a pas besoin de lire le
  moteur.
- **Godot ne calcule rien.** Il dessine le plan venu du YAML (il n'est pas
  dupliqué en GDScript), interpole entre deux instantanés, et renvoie des
  commandes (`inject`) que le moteur draine. Les instantanés pèsent 29 Ko
  à t0 et **70 Ko à 60 agents** : le client doit accepter 100 Ko, et le
  nôtre a dû porter son tampon d'entrée de 64 Ko à 8 Mo pour ne pas se
  déconnecter au milieu d'un run.

## 7. Fonctionnement interne de LangGraph

Le cahier des charges autorise les frameworks **à condition de savoir
expliquer leur fonctionnement interne**. Voilà, sans recopier la
documentation.

**Ce qu'est notre graphe.** Un `StateGraph` typé par un `TypedDict`
(`AgentState`) est compilé **une fois par run** et invoqué pour chaque
décision, avec l'état d'un agent :

```
START → recall → (retrieve ?) → decide → validate → END
```

**Les nœuds** sont des fonctions qui reçoivent l'état complet et renvoient
un **état partiel**. LangGraph fusionne ce partiel dans l'état courant :
un canal non renvoyé garde sa valeur. C'est plus qu'une commodité — c'est
la source d'un bug que nous avons eu : `query` était calculé dans
`retrieve` mais **non déclaré** dans le `TypedDict`, donc le canal
n'existait pas et la valeur était perdue à la sortie du nœud. Le symptôme
était un `rag.suspect` avec une question vide. Toute donnée qui doit
traverser deux nœuds doit figurer dans le schéma d'état.

**L'arête conditionnelle** (`add_conditional_edges`) appelle une fonction
qui renvoie une **clé** de routage (`"retrieve"` ou `"decide"`), associée à
un nœud par un dictionnaire. C'est là que vit la seule décision de
structure : faut-il interroger le corpus ? Oui si le déclencheur est un
signal (fumée, annonce, fermeture) ou si la meilleure croyance est sous
0,5 ; non sinon. Un agent sûr de lui n'a pas besoin de relire le guide.

**L'exécution.** `compile()` construit un exécuteur (le modèle Pregel de
LangGraph : sur-couches successives, ici trois au plus) et `ainvoke(state)`
le fait tourner en asynchrone. Nous n'utilisons **aucun checkpointer
persistant** : l'état entre et sort du graphe à chaque décision, rien n'est
sauvegardé par LangGraph. C'est délibéré — la source de vérité est le
journal, pas un fichier d'état du framework. Le coût d'un passage de nœud
est de l'ordre de la milliseconde, négligeable devant 2,8 s d'appel.

**Ce que le graphe ne fait pas.** Il ne parle pas au modèle : `decide`
appelle `LLMPort`, une passerelle unique qui journalise prompt, graine,
sortie brute et durée. Il ne décide pas de l'action finale : `validate`
transforme la sortie du modèle en `Intention` du domaine, et **replie sur
les règles** — avec une cause nommée — si la sortie est inexploitable. Un
graphe dont on ne peut pas sortir sans passer par une validation n'est pas
une contrainte imposée par le framework ; c'est notre façon de rendre A4
vérifiable.

**Pourquoi un graphe plutôt qu'une fonction.** La décision n'est pas
linéaire : un agent qui découvre la fumée interroge le corpus, un agent qui
a déjà une croyance solide n'en a pas besoin. Une arête conditionnelle rend
ce choix **explicite et testable** ; l'alternative aurait été un `if`
enterré dans une fonction de cent lignes. C'est le seul endroit où
LangGraph fait quelque chose que le domaine ne saurait pas dire autrement.

## 8. Ports et adaptateurs

Le domaine ne connaît aucun outil. Tout passe par des `Protocol` :

| port | aujourd'hui | demain |
|---|---|---|
| `CrowdPhysics` | JuPedSim 1.4 | autre moteur |
| `LLMPort` | llama.cpp (local) | n'importe quelle API |
| `RetrieverPort` | FAISS exact + bge-m3 | autre index |
| `JournalPort` | JSONL | Parquet, base |
| `EventBus` | Redpanda / mémoire | autre bus |
| `MemoryPort` | projection du journal | autre store |

Conséquence concrète : 203 tests tournent **sans GPU, sans
JuPedSim, sans Kafka**, avec une physique factice et une population à
règles, en quelques secondes.

## 9. Ce que nous n'utilisons pas, et la mesure qui l'a décidé

- **Mesa.** Son ordonnanceur (`Model.run_until`) est **synchrone** : un
  gestionnaire d'événement ne peut pas `await` un appel LLM de 2,8 s. Il
  aurait fallu bloquer la boucle ou faire tourner deux ordonnanceurs.
- **LlamaIndex.** Le corpus est déjà découpé en 215 passages annotés. Le
  seul traitement qui compte est le **centrage sur la moyenne du corpus**,
  parce que bge-m3 produit des embeddings anisotropes : précision@1 de
  0,167 sans correction, **0,733** après. Le déléguer à une abstraction
  générique aurait signifié le réécrire par-dessus.
- **Une base vectorielle.** 0,9 Mo de vecteurs : un index FAISS exact tient
  en mémoire et se charge plus vite qu'un index approximatif ne
  s'interroge.
- **Une API LLM distante.** Latence réseau de 70 à 500 ms par décision
  (qui viderait C4 et C7 de leur sens), quota qui tombe au milieu d'une
  campagne (donc des bras non comparables), et données envoyées à un tiers.
  Les 6 906 appels de la campagne X1–X7 ont tous abouti en local, sans un
  seul repli.
- **Un rendu 3D.** Le sujet est la croyance, pas l'image.
- **Parquet.** Voir §3 : le JSONL lu ligne par ligne fait le travail en
  3,4 s sur 450 000 événements.

---

# Partie II — Le mini-article

## 10. Question, et ce qu'on attendait

**Question.** Une foule qui ne sait rien de la géographie d'un lieu
construit-elle une croyance partagée sur la sortie sûre — et cette
croyance la sauve-t-elle ou la piège-t-elle ?

Le monde est l'esplanade de la Fête des Lanternes : 60 × 40 m, trois
sorties inégales, une fumée près de la scène. Les agents ont cinq profils
qui ne diffèrent pas par le caractère mais par **ce qu'ils savent au
départ** :

| profil | sorties connues | priorité |
|---|---|---|
| `securite` | A, B, C | évaluer, guider |
| `habitue` | A, B, C | éviter la foule |
| `famille` | A, C | retrouver un proche |
| `visiteur` | A | comprendre, suivre |
| `vendeur` | A, C | protéger son stand |

C'est le levier du monde : **le savoir local sauve, l'ignorance piège**. La
ruelle B, large de 1,5 m, n'est connue que de l'habitué et du sécurité.

Sept hypothèses ont été **préenregistrées** (`docs/hypotheses.md`, daté du
13 octobre, avant toute mesure) : clarté de l'annonce (H1), effet des
meneurs (H2), synchrone/asynchrone (H3), apport du LLM (H4), mémoire des
jours d'avant (H5), profils (H6), RAG (H7).

## 11. Dispositif

**Indicateurs.** Sept, chacun mesurant une chose et une seule :

| | ce qu'il mesure | définition |
|---|---|---|
| I1 | consensus | part des agents qui partagent la croyance majoritaire |
| I2 | entropie | dispersion des croyances, normalisée (0 = tous d'accord) |
| I3 | évacués | part des agents ayant **physiquement franchi** une issue |
| I4 | horloge | `tick × 10 s` : **quand**, et non combien de temps |
| I5 | densité | pic de densité par noyau de 2 m (pers/m²) |
| I6 | écart | part des agents croyant en une sortie **fermée** |
| I7 | délai | premier signal de danger → dernier sorti |

Deux d'entre eux ont été **refaits** en cours de route, et c'est ce qui
rend les chiffres lisibles :

- **I4 est une horloge, pas une durée.** Il inclut l'attente avant le
  premier signal et se **fige au plafond** `max_ticks` dès qu'une partie de
  la foule ne sort pas. Un run censuré affiche 720 s ou 900 s : ce n'est
  pas une évacuation, c'est un run interrompu. I7 part du premier signal de
  danger et s'arrête au dernier sorti : il reste défini sous censure. I4
  dit « quand », I7 dit « combien de temps », et I3 doit être publié à
  côté.
- **I5 a été refait par noyau de 2 m.** La grille de 1 m valait 2,0
  pers/m² dans **tous** les runs : avec une séparation minimale de 0,4 m,
  une cellule ne peut pas contenir plus de deux agents. Variance nulle,
  indicateur mort. Le noyau de 2 m donne 0,32 à 0,56 pers/m² — et il dit
  une chose importante : **le goulot de ce scénario est le savoir, pas
  l'encombrement**.

**Statistiques.** Médiane et intervalle interquartile (n est petit),
Mann-Whitney bilatéral, ≥ 5 runs par bras, 10 graines quand un écart
mérite d'être tranché. Nous ne comparons **jamais** deux runs appariés : le
batching concurrent change l'ordre des appels et les flottants, donc deux
exécutions de même configuration donnent les mêmes **comptes** mais pas les
mêmes **décisions**. Toute conclusion agrège des graines.

**Ce qui a été corrigé avant de mesurer.** Une campagne ne vaut que par ce
qu'elle mesure ; six défauts ont été trouvés en confrontant les premiers
résultats au journal.

| correction | ce qui n'allait pas |
|---|---|
| I5 par noyau | variance nulle (§11) |
| annonce lue par les règles | `bool(announcement)` : « Veuillez rester calmes » faisait sortir les 48 agents à règles ; la clarté n'était mesurable que sur 12 agents sur 60 |
| X1 en plan 2×2 | l'ancien protocole confondait texte et délai, et l'annonce tombait **après la sortie** dans 2 runs sur 5 |
| X4 sur scénario piège | sans fermeture d'issue, I6 valait 0 dans les trois bras : H4 était intestable |
| I7 | I4 ne mesure pas une durée sous censure |
| fuite de connaissance | une cible était validée contre le **plan**, pas contre les sorties que le profil **connaît** : un visiteur pouvait nommer B et y aller |

La fuite mérite d'être chiffrée parce qu'elle a **renversé une
conclusion**. Elle touchait un tiers à la moitié des cibles physiques des
agents LLM (X4 : 349 décisions sur 769). La campagne entière a donc été
rejouée après correctif ; les résultats d'avant sont conservés
(`runs/experiment_x*_avant_correctif.json`) et **toute conclusion de ce
rapport porte sur l'après**.

## 12. Résultats

### H1 — une annonce claire et précoce accélère l'évacuation
**Soutenue sur la clarté, pas sur l'heure.**

| bras | I7 (s) | I3 | I2 | runs censurés |
|---|---|---|---|---|
| clair, tôt (t17) | **160 [160–160]** | 1,00 | 0,47 | 0/5 |
| ambigu, tôt (t17) | **260 [260–260]** | 0,98 | 0,58 | **4/5** |
| clair, tard (t30) | 280 [270–290] | 1,00 | — | 0/5 |
| ambigu, tard (t30) | 270 [270–270] | 0,98 | — | **3/5** |

Clarté à délai égal : p = 0,0185. L'annonce est délivrée dans **5 runs sur
5** dans les quatre bras (vérifié sur le déclencheur, pas supposé).

Ce que la clarté achète n'est pas une accélération : c'est le **nombre de
sortis**. 1,00 partout avec un ordre clair, 0,98 sans, et **7 runs
censurés sur 10** dans les bras ambigus contre 0 sur 10 dans les bras
clairs. Une consigne vague ne ralentit pas la foule : elle laisse une
partie des agents à règles en `STAY` jusqu'au plafond. I2 le confirme
(0,47 contre 0,58, p = 0,0079) : l'ambiguïté se lit dans l'incertitude.

### H2 — les meneurs piègent davantage de monde
**Non soutenue, avec un signal dans le sens prévu.**

| bras | I6 | I3 | I7 (s) | I5 (pers/m²) |
|---|---|---|---|---|
| avec meneurs | 1,00 | 0,90 | **220 [220–220]** | 0,40 |
| sans meneurs | 1,00 | 0,92 | **150 [150–150]** | 0,48 |

p = 0,75 (I3), 0,74 (I5), **0,083 (I7)**. Quatre runs sur cinq sont
censurés des deux côtés. L'écart de délai (7 ticks de plus avec des
guides) va dans le sens de H2 mais n'est pas significatif à 5 graines : à
lire comme une piste. **I6 = 1,00 dans les deux bras** est une tautologie
du scénario (au moment de la fermeture, tout le monde croit en A) et ne
discrimine rien.

### H3 — synchrone contre asynchrone
**Effet nul sur la dynamique, gain mural net.**

| bras | I1 | I5 | I7 (s) | temps mural |
|---|---|---|---|---|
| synchrone | 0,96 | 0,48 | 100 | 34,0 s |
| asynchrone | 0,96 | 0,40 | 100 | **20,9 s** |

p = 0,84 (I1), 0,58 (I5), 0,54 (I7), **0,0117** (mural), facteur **1,63×**.
C'est la démonstration que la perception figée et l'ordre canonique font
leur travail : le parallélisme n'achète que du temps réel. En revanche, en
mode **réellement asynchrone** (chacun ramasse sa réponse quand elle
arrive, X11), le délai n'est plus gratuit : I7 passe de 220 à 470 s et
`lag_llm` de 0 à 5 ticks médians (12 au maximum).

### H4 — LLM contre règles sur l'écart croyance/réalité
**Réfutée — et le résultat est l'inverse de celui attendu.**

| bras | I3 | I7 (s) | appels | mural |
|---|---|---|---|---|
| hybride 12 LLM + 48 règles | 0,92 | 220 | 43 | 30,9 s |
| 60 règles | 0,92 | **150** | 0 | **9,6 s** |
| 60 LLM | **0,67** | **350** | **520** | **234,8 s** |

Le tout-LLM est le **pire** bras : 40 agents sortis sur 60 en médiane,
contre 55 pour les règles (p = 0,0117 sur I3 et I7), pour 12 fois le temps
mural. Qui reste piégé ? **Des visiteurs, dans les trois bras** — c'est
voulu, ils ne connaissent que A et A ferme à t14 — mais le nombre varie
énormément : 0 à 8 visiteurs piégés sur 24 en tout-règles, **17 à 23** en
tout-LLM.

Les agents à règles visiteurs se rabattent sur ce qu'ils savent faire :
suivre quelqu'un, attendre, sortir par où la foule sort. Les agents LLM
visiteurs explorent (`search`), tournent, et ne sortent pas. Le « 60/60 »
publié avant le correctif était l'artefact de la fuite, pas la cognition.
**Ce n'est pas le LLM qui rattrape les règles, c'est l'inverse.**

### H5 — la mémoire change le choix de sortie
**Soutenue sur les décisions, invisible dans les agrégats.**

| bras | I1 | I2 | I7 | `search` | `stay` | LLM → C |
|---|---|---|---|---|---|---|
| avec mémoire | 0,96 | 0,44 | 100 | **5,0** | **143** | **2,0** |
| sans mémoire | 0,96 | 0,44 | 100 | **8,5** | **134** | **1,0** |

Aucun agrégat ne bouge à 10 graines (p = 0,68 ; 0,52 ; 0,54). Au niveau
des décisions : `search` p = 0,0015, `stay` p = 0,0006, C p = 0,050. Avec
mémoire, les agents LLM cherchent moins, restent plus, et vont davantage
vers C — la sortie que les habitués connaissent et que le RAG documente.
Leçon de méthode : pour H5, **l'indicateur est la distribution des
décisions**, pas la moyenne de la foule. Douze agents sur soixante ne
déplacent aucun agrégat.

### H6 — le profil change la décision
**Soutenue.**

| bras | I1 | I3 | I7 (s) | LLM → A | LLM → B | règles → B |
|---|---|---|---|---|---|---|
| visiteurs seuls | **1,00** | 1,00 | **90** | 40 | **0** | 0 |
| habitués seuls | 0,93 | 1,00 | 100 | 31 | 13 | 66 |

p = 0,0001 (I1), **0,0252** (I7), I3 constante. Un visiteur ne connaît que
A et ne choisit que A — **côté LLM comme côté règles**, ce qui n'était pas
le cas avant le correctif de connaissance (12 décisions LLM vers B). Le
savoir définit l'ensemble des sorties atteignables, et il le fait plus
vite : 90 s contre 100 s, parce qu'il n'y a rien à arbitrer.

### H7 — le RAG change la croyance
**Soutenue, à 10 graines, sur la cognition et sur la foule.**

| bras | I2 | I3 | I7 (s) | `search` | LLM → B | LLM → C |
|---|---|---|---|---|---|---|
| avec RAG | **0,44** | 1,00 | **100 [100–100]** | **4,0** | 1,5 | 2,0 |
| sans RAG | **0,54** | 1,00 (3/10 censurés) | **150 [102–160]** | **21,5** | 0,0 | 1,0 |

p = 0,0008 (I2), **0,016 (I7)**, `search` p = 0,0002. Sans RAG, les agents
LLM errent cinq fois plus, prennent plus de décisions, et la foule met
50 s de plus — 3 runs sur 10 sont même censurés. Le RAG ne change pas
seulement ce que les agents croient : il change le temps que met la foule.

### Les deux leviers MARÉE restés non testés (X13, X14)

La fiche du monde propose quatre leviers d'expérimentation. Deux étaient
joués (clarté de l'annonce → X1, fermeture d'issue → X2) ; les deux autres
ne l'étaient pas. Ils le sont.

#### X13 — la présence d'agents de sécurité

Quatre agents sur soixante passent de `securite` (qui connaît A, B, C et
les consignes) à `visiteur` (qui ne connaît que A). Même effectif, même
répartition LLM/règles, mêmes graines. Deux scénarios : `demo` (aucune
sortie ne ferme) et `e2e` (A ferme à t14).

| bras | I1 | I2 | I3 | I7 (s) |
|---|---|---|---|---|
| avec sécurité, `demo` | 0,98 | 0,56 | 1,00 | 220 |
| sans sécurité, `demo` | 0,98 | 0,55 | 1,00 | 220 |
| avec sécurité, `e2e` | 0,97 | **0,16** | 0,92 | **270** |
| sans sécurité, `e2e` | 0,98 | 0,22 | 0,90 | 250 |

**Résultat : rien de significatif** (p = 0,84 sur I1 ; 0,75 sur I3 ; 0,50
sur I7 ; 1,00 sur I2). Le seul écart de médiane qui se voit — I2 0,16
contre 0,22 dans le piège — a des intervalles qui se recouvrent
complètement ([0,12–0,17] contre [0,08–0,24]) et ne tient pas.

Pourquoi ce levier ne mord pas, et c'est la partie utile : **le savoir de
la sécurité n'est pas exclusif**. Les habitués connaissent les mêmes
sorties, et douze d'entre eux sont des agents à règles qui guident déjà.
Retirer quatre agents qui savent ce que douze autres savent ne change pas
la carte mentale collective. Pour que ce levier existe, il faudrait que la
sécurité soit la **seule** à connaître B ou C — un monde différent, à
construire, pas à espérer d'un protocole.

*Note de méthode, et elle compte.* Le premier passage de ce protocole
utilisait `run: {name: e2e}` dans le bras : Hydra ne relit pas un groupe
après composition, la clé `name` arrivait dans `cfg.run` où personne ne la
lit, et les quatre bras mesuraient `demo`. Les chiffres étaient
« propres » — I7 identique partout — et faux. Corrigé (`_arm_run`), testé
(`tests/test_experiment.py`), puis rejoué. C'est exactement le genre de
défaut qu'aucun indicateur ne signale.

#### X14 — la proportion de groupes familiaux

Seize agents `famille` (27 %) contre zéro : les seize deviennent
`visiteur`. Même effectif, même répartition, mêmes graines.

| bras | I1 | I2 | I3 | I7 (s) | appels |
|---|---|---|---|---|---|
| avec familles | 0,98 | **0,55 [0,53–0,77]** | 1,00 | 220 | 48 |
| sans familles | 0,99 | **0,46 [0,42–0,69]** | 1,00 | 225 | 50 |

**Résultat : les familles rendent la foule moins sûre, sans changer son
issue.** À **10 graines**, I2 monte de 0,09 (**p = 0,031**), 9 graines sur
10 vont dans le même sens ; I3 et I7 ne bougent pas (p = 1,00 et 0,69) ;
le coût est identique (48 contre 50 appels). C'est cohérent avec le
profil : un agent `famille` cherche un proche, donc il doute, sans pour
autant sortir plus mal — il finit par sortir avec les autres.

Une réserve de lecture, parce que l'IQR de I2 est large : la distribution
est **bimodale**, et ce n'est pas un hasard. Les runs où un agent reste
non sorti à la fin (I3 = 0,98) produisent un I2 de 0,77 à 0,83 ; les
autres, 0,41 à 0,60. L'entropie moyenne sur la partie active est donc
plus haute dans les runs censurés, et c'est cette censure qui fabrique
l'intervalle large. L'écart entre bras reste dans **chaque** régime (0,60
contre 0,42 sur les runs complets, 0,82 contre 0,77 sur les censurés) —
mais il faut le dire plutôt que de ne montrer que la médiane.

Ce que X14 dit de notre modèle, et qui n'était pas acquis : **la
solidarité familiale se lit dans l'incertitude, pas dans la performance.**
Une foule avec des familles n'évacue pas moins bien ; elle évacue en
doutant. C'est un résultat modeste, et il ne faut pas lui faire dire que
les familles ralentissent : elles ne ralentissent pas, dans ce scénario.

### Les contrôles négatifs (B3)

Trois contrôles, dont deux joués en protocole et le troisième en
post-traitement :

| contrôle | attendu | mesuré | verdict |
|---|---|---|---|
| communication coupée (X8) | I1 chute | I1 **0,990 → 0,992** ; I2 0,333 → **0,461** ; I3 0,967 → 0,850 ; messages 58 → **0** | **I1 ne mesure pas l'influence sociale dans cette population** — c'est l'artefact que B3 devait révéler, publié tel quel. I2, lui, distingue. |
| annonce neutre (X8) | I2 ne baisse pas | joué avec le bras sans communication | pas de baisse |
| diversité des justifications | intra < inter si le modèle produit du gabarit | **intra 0,425 · inter 0,467** (rapport 0,91) sur 950 justifications X12,
  243 375 paires, embeddings bge-m3 | la variété ne vient pas d'un seul gabarit |

Le troisième contrôle est le plus intéressant, et il a failli manquer : il
compare la distance d'embeddings entre justifications **d'un même modèle**
et **entre modèles**. Un rapport proche de 1 signifie que le petit modèle
n'est pas un perroquet d'un gabarit unique — c'est le cas (0,91), et c'est
mesuré sur 450 775 paires.

**Coût de la communication** : sans diffusion, 131 appels au lieu de 77
(+70 %) et 47,6 s au lieu de 26,1 s. Ce n'est pas la diffusion qui coûte
cher, c'est son absence : un agent qui n'a rien entendu redécide. Un
système qui parle est un système qui pense moins souvent.

## 13. Résultats négatifs et résultats dérangeants

Nous les gardons en tête de liste, parce que ce sont eux qui nous ont
appris quelque chose.

1. **Le LLM n'améliore pas l'évacuation dans ce scénario** (X4). Il
   produit des décisions justifiées, une mémoire qui pèse, des échanges
   qui modifient les croyances — et, à 60 agents, une foule qui sort
   moins. C'est un résultat, pas un bug : le LLM explore ce qu'il ne
   connaît pas, et un visiteur qui explore dans un lieu dont il ignore la
   géographie reste sur place.
2. **I1 ne mesure pas l'influence sociale** (X8). La couper ne le fait pas
   bouger. Un indicateur de consensus qui ne réagit pas à la disparition
   de la communication mesure l'accord initial des profils, pas la
   contagion.
3. **I5 ne dépasse jamais ~0,6 pers/m²** : la foule n'est jamais dense.
   Ne pas conclure « pas de bouchon » d'un indicateur qui plafonne.
4. **I6 n'est vivant que dans le piège** et sature à 1,00 au moment de la
   fermeture : il mesure l'instant, pas la récupération.
5. **Un petit modèle ne raisonne pas, il suit la forme du prompt.** Quatre
   formats essayés, trois échecs : JSON à vocabulaire ouvert → il recopie
   le gabarit (`search`, confiance 0,0, 55 fois sur 55) ; liste de
   mots-clés → il choisit **toujours la première option**, quel que soit le
   contexte ; question binaire → instable. Ce qui marche : une **règle
   écrite** et deux drapeaux oui/non (calme 6/6, fumée 6/6, annonce 2/6 —
   la limite sur l'annonce est consignée, pas corrigée).

## 14. Limites

1. **I7 mesure un délai, pas une cause.** Il part du premier signal — dans
   X1, la fumée de t5 — donc l'heure de l'annonce reste dans le chiffre.
   Isoler la réaction à l'annonce demanderait de compter depuis l'annonce.
2. **« Dernier sorti » n'est pas « dernier piégé ».** En X4 hybride, le
   dernier sorti est un agent LLM dans 4 runs sur 5, alors que les piégés
   sont tous des visiteurs.
3. **La connaissance est statique.** Un message qui dit « B est libre »
   n'ajoute pas B au savoir d'un visiteur : la garde s'appuie sur
   `Profile.knows`. Un agent ne peut donc pas apprendre la géographie par
   ouï-dire — c'est une limite du modèle, pas du correctif.
4. **La fermeture d'une issue n'est pas une barrière physique** :
   JuPedSim ne détruit pas proprement une sortie, les agents sont
   redirigés vers un point d'arrêt 1,5 m à l'intérieur. Ils s'y accumulent.
5. **Puissance statistique.** X1–X4 restent à 5 graines : une p-value
   exacte à 5 contre 5 vaut 0,0079 au mieux, et deux écarts (X2 sur I7,
   X4 hybride contre règles) ne sont pas tranchés.
6. **Reproductibilité LLM.** Deux runs de même configuration donnent les
   mêmes comptes, pas les mêmes décisions. L'expérience doit agréger des
   graines, jamais comparer deux runs appariés. Le journal, lui, reste
   rejouable : on rejoue les décisions, on ne les régénère pas.
7. **« Panique irrationnelle »** (piste de réflexion du sujet) n'est pas
   mesurée : nous mesurons des croyances et des sorties, pas une émotion
   qu'aucun indicateur ne capte honnêtement.

## 15. Reproductibilité : ce qui tourne sur une autre machine

Le cahier des charges demande de pouvoir relancer la simulation « de façon
reproductible sur une autre machine, en suivant une procédure
documentée ». Trois niveaux, du plus sûr au plus exigeant :

| niveau | ce qu'il faut | commande | temps |
|---|---|---|---|
| **rejeu** | rien : ni GPU, ni réseau, ni serveur | `make replay-demo`, `make replay-pair` | < 2 s |
| **simulation sans LLM** | Python, `uv` | `make smoke` | < 1 s |
| **simulation hybride** | GPU 4 Go + llama.cpp | procédure du `README.md` §Démarrage | ~25 s par run |

Deux runs complets sont **versionnés dans le dépôt** avec leur journal :
`runs/demo20` (20 agents) et `runs/demo60` (60 agents), mêmes proportions
de profils, tout à règles — la paire que C8 demande de montrer en
soutenance. Ils ne dépendent d'aucun modèle, d'aucun réseau et d'aucun
hasard : `maree replay --run-id demo20` et `demo60` vérifient chaque
décision et l'empreinte des indicateurs, `ok: true` des deux côtés. Les
régénérer (`make demo-pair`) redonne les mêmes **comptes** : 200 s de
temps simulé, 60/60 et 20/20 sortis, I7 = 100 s dans les deux cas.

Trois pièges de procédure, tous rencontrés pour de vrai, sont documentés
dans le README plutôt que corrigés dans le code : `make up` (Docker
Compose) ne fonctionne pas sur la machine de développement (apt sans
réseau pendant le build, publication de ports cassée) ; il faut lancer le
conteneur llama.cpp à la main et **relire son IP** après chaque démarrage
(`MAREE_LLM_URL`) ; et sans cette variable, les runs deviennent des replis
règles silencieux — c'est pour cela que `run.ended` compte les succès et
que la CLI crie quand il n'y en a aucun.

# Partie III — Bilan de sobriété

## 16. Ce que les runs coûtent

Population de référence : 60 agents, dont 12 LLM. Tout est local : aucun
appel d'API, aucun quota consommé, aucune donnée envoyée.

| configuration | appels | jetons | mural | I3 | I7 (s) |
|---|---:|---:|---:|---:|---:|
| tout à règles, 60 agents (`demo60`) | **0** | 0 | **0,9 s** | 60/60 | 100 |
| run versionné `demo_replay` | 49 | — | 18,0 s | 60/60 | — |
| hybride, communication **coupée** (X8) | 131 | 62 431 | 47,6 s | 51/60 | — |
| hybride, communication **active** (X8) | 77 | 36 610 | 26,1 s | 58/60 | — |

Deux choses se lisent dans ce tableau, et une seule est une bonne nouvelle.

**La communication divise le coût par 1,7.** Sans diffusion, un agent qui
n'a rien entendu redécide : 131 appels au lieu de 77 (+70 %), 47,6 s au
lieu de 26,1 s. Ce n'est pas la diffusion qui coûte cher, c'est son
absence.

**Le LLM ne fait pas mieux évacuer, et il coûte.** 12 agents LLM + 48
règles sortent 58 sur 60 ; les règles seules sortent 60/60 en 0,9 s. En
tout-LLM (X4), c'est 40/60 pour 520 appels et 234,8 s. L'apport du LLM
dans ce scénario n'est donc pas la performance d'évacuation — il est
ailleurs, et il est mesurable (§17).

## 17. Ce que le LLM apporte, dit sans emphase

| apport | preuve |
|---|---|
| une décision **justifiée** par une phrase, pas seulement par une règle | `agent.decision.llm.raw_output` et `reason` |
| un recours explicite au **savoir** (RAG) | `retrieved` journalisé, P@1 0,417 (F2) |
| une **mémoire** datée qui pèse sur la décision | préhistoire J−3 : 50 % des décisions LLM citent un épisode (X9) |
| des **échanges** en langage naturel qui modifient la croyance | `message.sent` / `heard` : couper la communication change I2 de 0,333 à 0,461 (X8) |
| des **profils** qui décident différemment dans la même situation | X6 : p = 0,0001 sur I1 |
| un **récit** lisible du run | chroniqueur, 4 récits par run, 0 repli |
| des **dérives diagnostiquées** (A4, O2) | 8 % des appels, taux rapporté aux décisions et ventilé par cause |

Ce que le LLM n'apporte pas, et qu'il faut dire : de meilleures
évacuations, ni un coût plus bas. Le projet est un **banc d'essai pour
comparer des stratégies d'annonce et des dispositifs**, pas un optimiseur
d'évacuation.

### O2 — la posture d'« assistant prudent », mesurée

La dérive que le sujet nomme est réelle, et elle a une forme unique dans
notre corpus : sur **1 287 appels** de la campagne X12, **62** (4,8 %)
répondent *« cible générique : la sortie la plus proche »* — ils ne
nomment aucune sortie. L'agent ne refuse pas de
sortir : il refuse de **choisir**. C'est le comportement d'un assistant
qui ne veut pas se tromper, transposé à une foule qui doit se déplacer
maintenant.

Ce cas est séparé des replis, et c'est le point technique : l'intention
reste **appliquée** (`fallback: false`), parce que « sors » est un ordre
valide ; seule la cible est inutilisable, et le moteur la remplace par la
sortie connue la plus proche. Compter ce cas comme une réponse
inexploitable aurait gonflé le taux d'incidents et masqué la vraie
question : ce n'est pas le modèle qui a échoué, c'est la **consigne** qui
l'a rendu prudent. Le taux d'incident global (8 %) est rapporté aux
décisions LLM (`incident_rate` dans `run.ended`), pas compté en absolu.

## 18. Le levier de sobriété : le protocole, pas la taille du modèle (X12)

E5 demande de démontrer un gain **à apport comparable**. Cinq bras, cinq
graines, même population, même scénario, mêmes graines ; seule change
l'attribution des modèles et la consigne donnée.

| bras | ce qui change | appels | jetons | I3 | I7 (s) | mural |
|---|---|---:|---:|---:|---:|---:|
| `tous_grand` | référence : 12 agents sur le grand modèle, JSON ouvert | 48 | **20 456** | 1,00 | **110** | 21,3 s |
| `protocole_seul` | 12 sur le grand modèle, **règle + drapeaux** | 45 | 14 847 (−27 %) | 1,00 | 160 | 15,5 s |
| `deux_tiers` | 6 grands + 6 petits, règle + drapeaux | 47 | 14 027 (−31 %) | 1,00 | 220 | 16,3 s |
| **`tiers_regles`** | **6 grands + 54 agents à règles** | **25** | **12 385 (−39 %)** | **1,00** | **110** | 16,3 s |
| `petit_json_ouvert` | 6 grands + 6 petits, JSON ouvert (témoin) | 83 | 42 376 (+107 %) | 0,95 | 390 | 33,1 s |

**Le gain est réel et il ne vient pas d'où on l'attendait.**

- Passer du JSON ouvert à une **règle + deux drapeaux** économise 27 % de
  jetons **avec le grand modèle** : le protocole compte plus que le
  paramètre.
- Donner le JSON ouvert au petit modèle **coûte le double** (+107 % de
  jetons, +200 s de délai, 0,95 d'évacuation) : un modèle de 0,6 Md ne
  remplit pas un format ouvert, il le recopie.
- Répartir la cognition — six agents qui pensent, cinquante-quatre qui
  appliquent — **divise les appels par deux** (−48 %) et les jetons par
  2,6, **sans perdre un seul évacué ni un seul tick de délai** (I3 1,00,
  I7 110 s, identique à la référence).

C'est le résultat à retenir de E5 : **le levier de sobriété n'est pas la
taille du modèle, c'est le choix de qui pense.** Et le corollaire assumé :
le tier « petit » *applique* une politique, le tier « grand » la *juge*.
Un petit modèle à qui l'on demande de juger produit soit du gabarit, soit
la première option de la liste.

## 19. Énergie

Mesuré au compteur logiciel (`nvidia-smi --query-gpu=power.draw`,
échantillonné toutes les 500 ms) sur un run hybride de 31,6 s :

| grandeur | valeur |
|---|---:|
| puissance au repos | 6,5 W |
| puissance pendant le run | 59,0 W |
| surcoût | **52,5 W** |
| énergie du run | **1 658 J = 0,46 Wh** |

Un run hybride coûte un demi-watt-heure de GPU ; les runs de X12 (15 à
33 s) sont du même ordre, 0,2 à 0,5 Wh. Un run à règles dure 0,9 s —
plus court que la période d'échantillonnage, donc **non mesurable** avec
cette méthode, ce qui est en soi la réponse.

Ce n'est pas une mesure de laboratoire : `power.draw` est la puissance
instantanée de la carte, pas un compteur mural. `CodeCarbon` et
`EcoLogits`, cités par les ressources du sujet, **ne sont pas utilisés** :
EcoLogits estime l'impact d'appels d'API distants, dont nous n'avons
aucun ; CodeCarbon aurait ajouté une dépendance pour un chiffre que le
compteur donne directement. Ce qui n'est pas mesuré : CPU, RAM, et
l'énergie grise du matériel.

## 20. Où passe le temps, et ce qu'on couperait avec la moitié du budget

| poste | part du coût | comment le réduire |
|---|---|---|
| appels de décision | ~90 % des jetons | décisions événementielles (fait), filet périodique plus lâche (2× moins d'appels), répartition `tiers_regles` (÷2) |
| chroniqueur | 4 appels par run | 2 récits au lieu de 4 |
| embeddings RAG | hors run | index figé, déjà le cas |
| physique | 0,06 s pour 100 s simulées | non significatif |

Avec un budget divisé par deux, nous sacrifierions **le bras tout-LLM** et
les protocoles à 10 graines, pas la référence : la comparaison
LLM / règles et la mesure de clarté de l'annonce sont les deux résultats
qui tiennent avec 5 graines. Ce qui tomberait : l'écart X2 sur le délai
(p = 0,083) et la question « le petit modèle écoute-t-il les annonces ? »
(2/6, déjà non concluante).

---

# Les six questions du jury

## Q1 — Si l'on remplaçait vos agents LLM par votre baseline, qu'est-ce qui disparaîtrait exactement de votre écran et de vos courbes ?

**De l'écran, quatre choses — et une seule est un chiffre.**

1. **La justification en langue naturelle.** Un agent à règles écrit
   `A minimise distance + densité + étroitesse` : une règle, pas un
   raisonnement. Un agent LLM écrit une phrase qui peut contredire sa
   propre règle (`Les souvenirs indiquent C, mais l'annonce dit le nord.
   Je choisis C car c'est dans les souvenirs.`) — c'est là qu'on voit une
   croyance se former, et c'est ce que D2 demande de montrer.
2. **La mémoire datée.** Le panneau affiche les épisodes retrouvés avec
   leur date (`J-3`, `t18`) et leur déclencheur. Un agent à règles n'en a
   pas : il applique une règle à une perception.
3. **Le passage RAG et son score.** `annonces/claire-02 · 0,2865` —
   c'est-à-dire « voilà sur quoi il s'appuie, et à quel point ça
   ressemble ». Invisible sans LLM.
4. **Les dérives.** Posture d'assistant prudent, réponse inexploitable,
   sortie hors de son rôle, récupération douteuse : 8 % des appels en
   moyenne. Un agent à règles ne dérive pas — il n'a rien à dériver.

**Des courbes, une seule famille d'indicateurs bouge vraiment : I2.**
Remplacer les LLM par les règles ne change pas I1 (0,97 en hybride, 0,97
en tout-règles, 0,98 en tout-LLM)
ni I3 dans le bras hybride (0,92), et **améliore** I7 (220 → 150 s). Le
LLM ne déplace donc pas les courbes dans le sens favorable — et c'est
écrit tel quel (§13). Ce qui change, c'est la **distribution des
décisions** (X5 : `search` 5,0 contre 8,5 ; `stay` 143 contre 134) et
I2. C'est pourquoi nos conclusions scientifiques ne reposent pas sur
« le LLM évacue mieux », qui est faux, mais sur la circulation d'une
croyance, qui est mesurable dans le journal.

## Q2 — Votre indicateur mesure-t-il l'émergence d'un contexte commun, ou simplement la ressemblance des réponses d'un même modèle ? Comment le savez-vous ?

**Réponse courte : I1 ne mesure pas l'émergence. Nous l'avons vérifié,
publié, et nous nous appuyons sur I2.**

Trois preuves, dans l'ordre de force :

1. **I1 part à 1,00 par construction.** Au tick 0, tous les profils
   partagent la même croyance par défaut (`A`, confiance 0,35). Un
   indicateur qui démarre à 1 ne peut pas mesurer une convergence : il ne
   peut que mesurer une perte. Sur `demo60`, I1 vaut 1,00 à t0 et ne
   bouge jamais — la foule n'a rien construit, elle est partie d'un accord.
2. **Couper la communication ne le fait pas bouger** (X8, 5 graines) :
   I1 0,990 → 0,992, alors que les messages passent de 58 à **0**. Un
   consensus qui ne dépend pas de la communication n'est pas un consensus
   social : c'est la similarité des profils et des règles. C'est
   exactement l'artefact que B3 demande de chercher, et nous l'avons
   trouvé contre nous.
3. **I2, lui, distingue** : 0,333 → 0,461 sans communication (p sur le
   protocole), et 0,44 → 0,54 sans RAG (p = 0,0008). L'entropie des
   croyances réagit à ce qui devrait la faire réagir.

**Et la ressemblance des réponses d'un même modèle ?** Troisième contrôle
de B3, en post-traitement : 950 justifications de X12, embeddings bge-m3.
La distance cosinus médiane **entre deux réponses du même modèle** vaut
0,425 ; **entre modèles différents**, 0,467. Rapport **0,91** — la variété
intra-modèle est du même ordre que l'inter-modèle, donc les justifications
ne sont pas un gabarit unique recopié 950 fois. Détail qui va contre
l'intuition : le petit modèle est *plus* varié (0,437) que le grand
(0,420), parce qu'il répond une phrase courte et variable alors que le
grand suit un contrat JSON.

## Q3 — Quelle conclusion de votre rapport resterait vraie avec dix fois plus d'agents, et laquelle tomberait ?

**Resterait vrai :**

- **La physique n'est pas le goulot.** JuPedSim fait 60 agents sur 100 s
  simulées en 0,06 s (1 761× le temps réel) ; à 600 agents il reste trois
  ordres de grandeur sous le temps réel. L'architecture à trois horloges
  tient.
- **Le journal et le rejeu.** Rien dans le rejeu ne dépend du nombre
  d'agents : `maree replay` rejoue des décisions, pas une foule.
- **« Le savoir local sauve, l'ignorance piège »** (X6, X4). À 600 agents,
  il y a proportionnellement plus de visiteurs piégés, pas moins.
- **La clarté de l'annonce compte** (X1). L'effet ne dépend pas de la
  taille de la foule mais de la proportion d'agents qui n'ont pas de
  motif de sortir sans ordre — et cette proportion est dans la
  population, pas dans son effectif.

**Tomberait :**

- **« Le goulot est le savoir, pas l'encombrement »** — c'est vrai à
  60 agents sur 2 400 m². À 600, la densité moyenne devient 0,25 pers/m²
  et les abords des trois sorties satureront : I5, qui plafonne ici à
  0,6 pers/m², deviendrait l'indicateur principal, et le modèle de
  collision rapide de JuPedSim (sans force sociale) deviendrait
  contestable.
- **Le décalage mesuré (C7).** `lag_llm` vaut 8 ticks à 60 agents avec
  `max_concurrency = 4`. À 600 agents dont 120 LLM, la file d'attente
  multiplie la latence par 30 : le décalage mesuré décrirait la file, pas
  la cognition. Il faudrait soit baisser la proportion de LLM, soit
  l'assumer et mesurer la file comme un fait du monde.
- **Toute statistique à 5 graines.** Les p-values ne survivraient pas à un
  changement de distribution de cette ampleur ; il faudrait rejouer.

## Q4 — Avec un budget d'appels divisé par deux, que sacrifieriez-vous, et quelle conclusion tomberait ?

**Ce qu'on garde, et il y a de la marge :** `tiers_regles` divise déjà les
appels par deux (25 contre 48) *sans perdre un évacué* (I3 1,00, I7
110 s) — c'est un résultat mesuré (§18), pas une projection. Avec un
budget de 25 appels par run, on garde donc la référence, la baseline à
règles et le protocole d'annonce.

**Ce qu'on sacrifie :**

| sacrifice | coût |
|---|---|
| le bras **tout-LLM** de X4 (520 appels par run) | le résultat « le tout-LLM sort moins bien » resterait vrai mais ne serait plus reproductible dans le budget |
| les protocoles à **10 graines** (X5, X6, X7) | les p-values tombent à 0,08 au mieux ; H5, H6 et H7 resteraient des pistes |
| le **chroniqueur** (4 appels par run) | on perd le récit, pas la mesure |
| X1 en plan **2×2** → garder seulement clair/ambigu à délai égal | on perd l'effet de l'heure, qui est déjà non significatif |

**Ce qui tomberait pour de bon :** la question « le petit modèle
écoute-t-il les annonces ? » (2/6 — déjà non concluante, donc rien à
perdre) et l'écart X2 sur le délai des meneurs (p = 0,083), qui n'est pas
tranché aujourd'hui de toute façon.

## Q5 — Montrez une décision prise à partir d'une information mal retrouvée. Qu'a fait l'agent, et votre système s'en est-il aperçu ?

**Oui, et le système s'en est aperçu 115 fois sur la campagne X12** — au
moins une fois dans chacun des 25 runs.

**Le cas.** `run_x10_grande_async_s1_73fd`, tick 20, agent **A14**
(habitué, grand modèle). L'annonce officielle est diffusée ; A14 interroge
le corpus. Le meilleur passage retrouvé est `annonces/claire-02` (score
0,2865) qui dit : « l'esplanade est **évacuée par la sortie B** ». Le
deuxième dit A, le troisième dit C — **le corpus contient douze variantes
d'annonce**, une par secteur, et la récupération en rend trois
contradictoires. A14 choisit **C**, en écrivant : « Les souvenirs
indiquent C, mais l'annonce officielle dit le nord. Je choisis C car
c'est dans les souvenirs. »

**Ce que le système a fait.** Le drapeau `rag.suspect` n'a **pas** tiré :
le score (0,2865) est au-dessus du seuil de 0,17. Il a tiré dans l'autre
cas de figure, celui des récupérations faibles : requête « évacuation
esplanade » sans contexte, meilleur score **0,1374**, document
`souvenirs_editions/2022-agents` (« une fumée de barbecue avait déclenché
une évacuation »). L'agent A57 a répondu `RESTER` — décision correcte à
t1, où aucune fumée n'est visible — mais le passage était hors sujet, et
l'événement `rag.suspect` l'a consigné avec la question, le score, le
document, le seuil et la chaîne causale. C'est ce qui permet de
retrouver ces cas dans 450 000 événements en une requête au lieu de les
relire à la main.

**Ce que cet exemple nous a appris, et que nous n'avions pas prévu.**
Notre seuil attrape les récupérations **faibles**, pas les récupérations
**contradictoires**. Une annonce à 0,29 est très ressemblante et fausse :
l'agent reçoit trois consignes différentes et rien ne le prévient. C'est
une limite du corpus (les douze variantes sont toutes disponibles à
partir de t10, alors qu'une seule a été diffusée), elle est quantifiée
dans la campagne X12 : sur **565 décisions** qui retrouvent au moins deux
annonces, **478** en reçoivent de contradictoires. La vraie annonce est
toujours donnée séparément dans le prompt (« Annonce officielle : … »),
ce qui limite les dégâts — mais un modèle peut préférer ses souvenirs.

**Ce qu'il faudrait faire** : filtrer la collection `annonces` sur le
texte réellement diffusé (le percept le porte déjà), ou étiqueter chaque
variante par sa sortie et ne rendre que celle qui est cohérente. Ce n'est
pas fait, et c'est dit ici plutôt que découvert par un relecteur.

## Q6 — Votre résultat principal tient-il dans les deux modes, synchrone et asynchrone ? Sinon, lequel des deux décrit le mieux votre phénomène ?

**Il tient en partie, et la partie qui ne tient pas est instructive.**

| | synchrone (X3) | asynchrone (X11) |
|---|---|---|
| I3 | 1,00 | 0,98 |
| I7 | 220 s | **470 s** |
| décalage `lag_llm` | 0 | **5 ticks médians, 12 au maximum** |
| appels | 47 | 60 |

- **Ce qui tient** : l'issue physique. Dans les deux modes, la foule sort
  presque entièrement, et les mêmes croyances mènent aux mêmes sorties.
  I3 1,00 contre 0,98 : l'histoire « la croyance mène à l'issue » ne
  dépend pas du mode.
- **Ce qui ne tient pas** : **les délais**. I7 double (220 → 470 s) et le
  décalage passe de 0 à 5 ticks médians. En synchrone, la barrière du tick
  interdit à la latence du modèle d'exister dans le monde : le temps
  simulé et le temps de calcul sont décorrélés. En asynchrone, chaque
  seconde de LLM devient 4 ticks de monde : **le modèle lent devient un
  fait du monde**.

**Lequel décrit le mieux le phénomène ? L'asynchrone, sans hésiter** —
une foule réelle ne décide pas en lockstep, et l'attente fait partie de
ce qui piège les gens. Mais c'est le **synchrone qui rend l'expérience
sur l'annonce interprétable** : il isole la variable « clarté » de la
vitesse de chacun à décider. Les deux ne s'opposent pas, ils répondent à
deux questions différentes — et tout chiffre de délai doit dire dans quel
mode il a été obtenu. C'est la raison pour laquelle I7 est toujours publié
à côté de I3 et du mode.

---

# Conclusion

## Ce que le projet démontre, en trois phrases

1. **Une croyance partagée se mesure, et elle peut piéger.** I2 réagit à la
   communication (0,333 → 0,461 quand on la coupe), au RAG (0,44 → 0,54
   quand on le retire) et à la composition de la foule (familles : 0,44 →
   0,57). I1, lui, démarre à 1,00 par construction et ne mesure pas
   l'influence sociale — nous l'avons découvert en le testant, pas en le
   supposant.
2. **La clarté d'une annonce change l'issue, pas seulement le temps.** À
   délai égal, 60/60 sortent avec un ordre clair, et 7 runs sur 10 sont
   censurés avec une consigne vague.
3. **Le coût est maîtrisable, et le levier n'est pas celui qu'on croit.**
   Répartir la cognition (6 agents qui pensent, 54 qui appliquent) divise
   les appels par deux sans perdre un évacué ; donner un format ouvert au
   petit modèle double la facture.

## Ce que le projet ne démontre pas

- Que le LLM évacue mieux. **C'est l'inverse** sur le scénario du piège
  (40/60 contre 55/60), et c'est publié comme tel.
- Que la foule entre en panique. Nous mesurons des croyances et des
  sorties ; « panique irrationnelle » n'a aucun indicateur honnête ici.
- Qu'à 600 agents les mêmes conclusions tiendraient : I5 changerait de
  nature, le décalage mesurerait la file, et tout serait à rejouer (Q3).
- Que la connaissance s'apprenne par ouï-dire : un message qui dit « B est
  libre » n'ajoute pas B au savoir d'un visiteur.

## Ce qui reste ouvert, en une liste honnête

1. **Le corpus d'annonces rend des variantes contradictoires** (478
   décisions sur 565 en X12). Le percept porte la vraie annonce à part,
   mais le modèle peut préférer ses « souvenirs ». À filtrer.
2. **Le petit modèle n'écoute qu'à moitié les annonces** (2/6 sur essais
   directs) : c'est la limite de la politique explicite, consignée.
3. **O4, conditions dégradées** : l'agent muet et la réponse
   inexploitable sont éprouvés au quotidien (8 % des appels) ; le cas
   « quota atteint » ne l'est pas, faute d'API distante.
4. **L'énergie n'est mesurée qu'une fois** (0,46 Wh), pas par bras.
5. **X2 reste à la limite de la puissance statistique** à 5 graines
   (p = 0,083 sur I7, en faveur de H2) : un écart dans le sens prévu,
   non tranché. X14, lui, a été rejoué à 10 graines et tient (p = 0,031).
6. **L'interface ne fait pas de clic sur un indicateur** ; la remontée
   existe en CLI (`maree trace`).

## Où lire quoi

| question | document |
|---|---|
| où en est chaque exigence des 32 ? | `docs/plan-socle.md` |
| qu'est-ce qui manquait, et pourquoi ? | `docs/audit-consigne-2026-10-31.md` |
| tous les tableaux, protocole par protocole | `docs/resultats/rapport-v2.md` (généré) |
| la lecture par hypothèse | `docs/resultats/conclusions-v2.md` |
| le contrat d'affichage pour un autre client | `docs/protocol-ui.md` |
| les pièges d'environnement | `AGENTS.md` |
