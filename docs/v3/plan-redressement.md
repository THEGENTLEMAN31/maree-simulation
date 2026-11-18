# Redressement v3 — audit, tri des résultats, chantiers

_2026-11-17. Ce document ne raconte pas la v3 : il dit ce qu'elle fait
vraiment, ce qu'on garde, ce qu'on refait, et dans quel ordre. Il précède le
code (règle du dépôt : une décision structurante est consignée avant d'être
implémentée)._

---

## 0. En une page

**Le constat.** Trois bras sont censés être comparés (`règles`, `LLM`,
`hybride`). En pratique : l'hybride n'appelle **jamais** le modèle ; même le
bras `llm` ne décide pas à chaque changement du monde ; la perception ne
contient ni les autres agents, ni la densité, ni la distance au danger ; la
physique ne sait exécuter qu'**une action sur sept** et envoie « rester » vers
le coin du bâtiment ; les jetons sont comptés sur la dernière décision de
chaque agent seulement. Les chiffres de décision (§1–2bis) tiennent. Les
chiffres de coût et tout ce qui touche la foule ne tiennent pas.

**Ce qui tient.** Le journal, le rejeu, le bus Kafka, le contrat WS, le
dossier agent, le monde généré + validé, l'adaptateur JuPedSim, et le
scénario « sortie bloquée » (le seul endroit où la réponse par défaut est
fausse, donc le seul où la taille du modèle se mesure). **On ne les
réécrit pas.**

**Ce qu'on refait.** La perception, la physique (mapping des intentions),
le calendrier de décision, le déclencheur d'escalade, le comptage du coût,
les indicateurs de foule, et un monde où une foule existe vraiment.

**La porte de décision** (§6) : aucun nouveau chiffre publié avant que trois
preuves à coût nul passent — les trois bras se distinguent avec un stub, un
agent qui « reste » reste sur place, et une foule produit un goulot mesurable.
Si l'une échoue, on répare avant de mesurer.

---

## 1. Ce qui tient (ne pas y toucher)

| Brique | Preuve existante |
|---|---|
| Journal JSONL append-only + rejeu sans LLM | `demo_replay_v3.jsonl`, `make v3-replay-demo` |
| Enveloppes + schémas versionnés | `maree.event/1.0`, 36/36 conformes |
| Bus Kafka réel (C1/F4) | `scripts/v3_kafka_roundtrip.py`, 36/36, `seq` continus |
| Contrat WS + dossier + injections (P4) | `api/server.py`, `api/dossier.py`, test client |
| Monde généré + validé + navgraph | `world/generate.py`, `world/validate.py` |
| Physique JuPedSim derrière un port | `adapters/physics.py`, 5 tests |
| Scénario bloqué + preuve GPU-free du 0,50 | `verify/scenario_blocked.py`, `tests/v3/test_scenario_blocked.py` |
| Petit modèle = politique positionnelle (0,50) | `runs/v3/campaign_blocked.json` |

Le harnais expérimental est bon. Ce qu'il mesure est incomplet.

---

## 2. Audit — ce que le code fait vraiment

Chaque ligne est vérifiée dans le code, pas supposée.

| # | Constat | Preuve | Effet | Verdict |
|---|---|---|---|---|
| D1 | **La perception est vide.** `State()` neuf à chaque tick, `seen_agents=()`, `crowding=0`, `distance_to_danger=None`, `exits_visible=∅` | `sim/scene.py:perception_for` | La preuve sociale vaut toujours 0 ⇒ `SUIVRE` (règle 4) **inatteignable** ; l'urgence ne dépend que de la fumée ; la densité et la distance n'existent pas pour la cognition | **à réparer** |
| D2 | **La physique est découplée, et « rester » envoie au coin.** `Target.stay()` → `_stay_journey((0.0, 0.0))` ; mesuré : un agent à (5,5) qui « reste » finit à (1,18 ; 1,18) | `adapters/physics.py:_journey_for` ; sonde exécutée | Toute action non-évacuation fabrique une foule dans un coin, et fausse densité, I5, I7 | **bug, à corriger** |
| D3 | **1 action sur 7 a un effet physique.** `_apply_intention` ne mappe que `EVACUER` ; le reste → `stay()` | `sim/orchestrator.py:_apply_intention` | `CHERCHER`, `SUIVRE`, `AIDER`, `CHERCHER_PROCHE`, `REVIRER` sont des mots sans corps | **à réparer** |
| D4 | **Le calendrier de décision est une liste fixe partagée par les trois bras** : fumée, annonce, proche, message | `agents/agent.py:_novel_events`, `sim/orchestrator.py:_process_tick` | « quand penser » est déterministe partout ; le bras `llm` n'est pas intégral ; aucune réaction à une sortie qui ferme, à la densité, ni au temps | **à remplacer** |
| D5 | **L'hybride n'escalade jamais** (critère circulaire : « les règles ne savent pas ») et, s'il escaladait, il appellerait toujours le grand modèle (`LLMPolicy()` sans alias) | `agents/policy_llm.py:hybrid_decide` ; sonde : 0 appel | Le bras « hybride » publié est un clone des règles | **à remplacer** |
| D6 | **Les jetons sont comptés sur `_last_decision`**, une décision par agent, alors que les appels sont comptés sur toutes les lignes | `verify/campaign.py:run_once`, `scripts/v3_campaign_*.py` | `appels=8` et `jetons` calculés sur 4 : le coût publié est sous-estimé et les bras ne sont pas comparés sur la même base | **à refaire** |
| D7 | **Aucune communication entre agents.** Les messages n'arrivent que par la chronologie du scénario ou une injection | `grep say/emit_message` : néant | Pas de rumeur, pas de cascade, pas de démenti : H3/H4/H5 et le phénomène P3 sont **structurellement** hors d'atteinte | **à trancher** (§5 C7) |
| D8 | **Une annonce ne devient pas une croyance.** `_consume` la marque « vue » mais n'écrit ni `exit:` ni `hazard:` | `agents/agent.py:_consume` | Pas de contradiction calculable entre annonce et croyance ; `authority_trust` ne sert à rien | **à réparer** |
| D9 | **Des couches déclarées et mortes** : `risk_aversion`, `authority_trust`, `impulsivity` = 0 usage ; `kin` jamais assigné ; `prehistory=True` jamais utilisé hors tests | comptage d'usages | L'archétype `famille` est un `visiteur` qui marche moins vite ; la mémoire J−3 est décorative en run | **à réparer ou à retirer du discours** |
| D10 | **Aucun indicateur I1–I7 en v3.** `grep I3/I5/I7` : néant | — | Pas de goulot, pas de délai, pas de censure : la « foule » n'est pas mesurée | **à porter** depuis `src/maree/metrics/indicators.py` |
| D11 | **60 agents ne font pas une foule.** `hall_3` = 120×80 m ; 60 agents = 0,006 pers/m². Les spawns sont 6 points réutilisés en boucle | `world/generate.py`, `sim/orchestrator.py:spawn`, `simartifact.py` | Densité de pointe dictée par les 6 grappes de spawn, pas par le goulot | **à calibrer** |
| D12 | **L'émergence est gonflée et aveugle.** `consensus` inclut les agents sortis ; `couplage` ne compte que les croyances `exit:` renforcées par ouï-dire, donc ignore « A est bloquée » | `verify/emergence.py` | Dans le scénario bloqué, le drapeau d'émergence vaut 0 par construction | **à corriger** |
| D13 | **Les graines sont cosmétiques** : monde fixe, température 0 ⇒ les N runs sont le même run | `scripts/v3_campaign_blocked.py` | « 5 graines, 5/5 » = 1 observation répétée ; aucune variance, aucun test possible | **à requalifier** |
| D14 | **Le score micro garde la *dernière* cible, pas la première.** Les règles envoient d'abord (t2) les agents vers la sortie qu'on vient de leur dire bloquée, puis se corrigent à la fumée (t10) | `scenario_blocked.py:score` ; journal mesuré : t2 `A01→A`, t10 `A01→B` | « règles 1,00 » est vrai **à t10 seulement** ; avec physique, 8 ticks de marche vers une porte crue bloquée sont invisibles. Le message « La sortie A est bloquée » est lu comme un ordre d'évacuer **vers A** (`_is_evacuation_order` reconnaît « sortie ») | **à corriger + à remesurer** |

---

## 3. Tri des résultats publiés

Rien ne se supprime : on déplace, on requalifie, ou on refait. Archive :
`runs/v3/avant_correctif/`.

| Résultat | Ce qui reste vrai | Action |
|---|---|---|
| §1 mémoire personnelle : règles 1,00 / LLM 0,50/0,50 | Le LLM n'utilise pas un message **positif** ; les règles le suivent | **garder**, requalifier : « le défaut A gagne, donc ce scénario ne teste pas la lecture de mémoire » |
| §2 annonce contradictoire : règles 0,50 / LLM 1,00 | L'annonce fait basculer les règles ; les LLM arbitrent pour la mémoire | **garder** ; noter que « désobéir à un ordre » est un choix de conception, pas une victoire |
| §2bis sortie bloquée : grand 1,00 / petit 0,50 | **Le résultat phare** : le petit applique une position | **garder**, requalifier « 1 run rejoué 5 fois », puis étendre à 60 agents (C6). **Corriger la métrique** : noter la **première** cible et chaque décision, pas la dernière — les règles passent de A (faux) à B (juste), le grand est juste aux deux, le petit faux aux deux. |
| Ablation `dangers` (grand reste à 1,00) | Le grand intègre le fait brut, pas seulement le champ pré-digéré | **garder** ; compléter par une ablation par champ (`messages_recus`, `memoire`, `sorties_connues`) |
| §3 sync/async : lag 0 / 4 | Le mode asynchrone applique avec retard | **garder**, renommer « latence **déclarée** » (elle vient de `latency_ticks`, elle n'est pas mesurée) |
| §3bis Kafka 36/36 | Contrat tenu **sur le fil** | **garder tel quel** — indépendant des correctifs |
| §4 énergie 0,0256 vs 0,1058 Wh | Le petit consomme moins | **refaire** : jetons faux, run de 5,7 s échantillonné à 1 Hz (bruit), et le bras « hybride » n'est pas un bras |
| Bras « hybride, 0 appel » | Rien sur le modèle ; tout sur le déclencheur | **retirer** des tableaux ; renommer « règles, 0 escalade » |
| `e2e_real_hall3.jsonl`, `v3_foule_hybride.jsonl` | Journaux de démonstration | **garder comme démos**, ne plus les citer comme mesures |
| Rapport §3.5 « l'hybride ne déclenche que sur l'ambiguïté » | — | **faux en pratique** : corriger |

À ajouter au rapport, comme **résultat** et non comme excuse : « ce qui était
mesuré n'était pas exactement ce que nous croyions mesurer ; voici la liste,
voici ce qui tient ». Un audit publié vaut mieux qu'un chiffre gonflé.

---

## 4. Le modèle expérimental cible

### 4.1 Les trois bras

| Bras | Qui décide | Calendrier | Ce qu'il répond |
|---|---|---|---|
| `regles` | la politique déterministe | fronts (fumée, annonce, message, proche, **fermeture**) | que fait-on sans modèle ? (témoin, coût 0) |
| `llm` | **le modèle, à chaque fois que l'agent reconsidère** | changement perçu (hash de perception) ou revue bornée | que fait un modèle quand il pilote ? (coût complet) |
| `hybride` | règles en routine, modèle sur critères **du monde** | fronts + escalade (§4.3) + revue | qu'apporte le modèle, à quel prix ? (courbe de coût) |

Les trois partagent la même perception, la même physique, le même journal.
Ils ne diffèrent que par la décision et le calendrier.

### 4.2 Le calendrier, par bras

Le calendrier sort de `Agent.react` et devient une fonction de politique :
`should_decide(agent, perception, tick) -> (bool, raison)`.

- `regles` : la liste de fronts actuelle, plus `sortie_fermee` et `proche_reapparu`.
- `llm` : décide sur **changement pertinent** (ADR-014) — information
  nouvelle, plan invalidé (cible bloquée/saturée, pas de progression),
  contexte franchissant un palier (densité, agents partant ailleurs, menace)
  — et non sur « le monde a bougé ». Référence : 4 appels pour 30 ticks.
- `hybride` : fronts + escalade + revue.

**Pourquoi « full LLM » n'est pas « chaque tick ».** Le prompt contient la
perception. À température 0, si la perception n'a pas changé, le modèle rend
la même réponse : rappeler est du coût pur, pas une architecture différente.
Le vrai sujet n'est donc pas la cadence, c'est **ce que la perception
contient** — d'où C2 avant C3. Si l'on veut mesurer le coût de la cadence,
on ajoute un bras `llm_chaque_tick` sur **un** monde, et on publie l'écart.

### 4.3 Trois définitions possibles de l'hybride — **tranché : option 1**

**Décidé le 2026-11-17 (ADR-014) : escalade sur ambiguïté du monde.** Les
deux autres restent des instruments, pas des bras : l'option 2 (quota ε) est
un test de sensibilité sur un seul scénario, l'option 3 (arbitre) un
diagnostic micro (« quand le modèle s'écarte du premier choix des règles,
a-t-il raison ? »). Aucune des deux ne se présente comme une architecture.

Les trois options, pour mémoire :

1. **Escalade sur ambiguïté du monde** (retenue) : les critères de
   `agents-et-llm.md` §3, calculables, journalisés. Le modèle ne parle que
   quand le monde est contradictoire.
2. **Quota** : le modèle traite une fraction ε des décisions routinières,
   tirée par SHA-256(tick, agent, graine). ε ∈ {0 ; 0,05 ; 0,25 ; 0,5 ; 1}.
   Donne une **courbe** qualité/coût, pas un point. Instrument seulement.
3. **Arbitre** : les règles produisent 3 à 8 actions candidates, le modèle
   choisit. Diagnostic seulement : à 100 % du coût, il ne compare plus
   « modèle vs règles » mais « modèle contraint vs règles ».

### 4.4 Les critères d'escalade (option 1), calculés sur le monde

| Critère | Condition | Journal |
|---|---|---|
| `annonce_ambigue` | annonce présente et : aucune sortie nommée, ou ≥ 2 nommées, ou sortie nommée crue bloquée | cause + texte + sorties citées |
| `information_contradictoire` | même sortie avec `exit:` **et** `hazard:` ; ou deux reçus de confiance à ≤ 0,2 d'écart ; ou annonce opposée à une croyance | sortie + confiances + sources |
| `situation_inédite` | aucune croyance de sortie ; ou première fumée à moins de X m ; ou densité > seuil | quoi |
| `revue` | menace > 0 et `tick - dernier_avis ≥ R` | — |
| `regles_indecises` | l'ancien critère, conservé et **nommé** (il n'est plus le seul) | — |

Chaque escalade publie `agent.escalation` (nouveau type d'événement), et le
rapport de run porte `taux_escalade` + l'histogramme des causes. Une
escalade non motivée est un incident.

### 4.5 Les scénarios

- **Micro — sortie crue bloquée** (existant, à garder). 4 agents, A et B
  connus, moitié « A bloquée » / moitié « B bloquée » à t2, fumée t10, pas
  d'annonce. Réponse par défaut fausse ⇒ plafond 0,50 pour toute politique
  positionnelle.
- **Macro — la même croyance, avec une foule** (nouveau). Même design de
  croyances, mais 60 agents, physique réelle, un monde **calibré** pour
  produire un goulot (voir C5) : 30 croient A bloquée, 30 croient B bloquée,
  les deux portes restent **physiquement ouvertes**. On mesure la part
  **des décisions** (et non des agents) qui visent une sortie crue bloquée,
  la **première** cible séparément, I5 (noyau 2 m), I7, I3, la répartition par
  sortie au cours du temps, et la distance parcourue vers une porte crue
  bloquée avant demi-tour.
- **Contradiction officielle** (existant, §2) : l'annonce nomme une sortie
  que la croyance dit bloquée. C'est le cas d'escalade `annonce_ambigue` par
  excellence.

### 4.6 La statistique

- **Une graine = un monde**, pas un redémarrage du même monde. Générer N
  géométries distinctes (même distribution) ; le monde est l'unité.
- **Pré-enregistrer** : critère principal par scénario, N, sens attendu,
  avant de lancer. Exemple macro : principal = part entrant dans une sortie
  crue bloquée ; secondaires = I5, I7, I3.
- Comparaison **appariée par monde** (Wilcoxon signé) entre bras ; jamais
  deux runs LLM appariés (l'ordre du batching change les flottants).
- Déclarer le nombre de runs rejoués à l'identique (déterminisme) à part de
  l'échantillon.

---

## 5. Chantiers

Chaque chantier : objectif, contenu, preuve, coût (effort effectif).
Ordre imposé par les dépendances.

### C0 — Triage et ADR (0,5 j)

Archiver `runs/v3/*.json` dans `runs/v3/avant_correctif/`, requalifier
`docs/v3/resultats-campagnes.md` et `rapport-v3.md` (bandeau « avant
correctif »), écrire les ADR : définition des trois bras (§4.1), calendrier
(§4.2), critères d'escalade (§4.4), option d'hybride retenue (§4.3),
statistique (§4.6).
**Preuve** : les docs ne contiennent plus aucune des phrases de §8.

### C1 — Physique honnête (1 j)

1. `Target.stay` = position **courante** ; `Target.point(p)` devient réel
   (aujourd'hui `_journey_for` ignore `point`).
2. Mapper les 7 actions : `EVACUER` → sortie ; `RESTER` → place ;
   `CHERCHER` → point de la zone (déterministe, borné) ; `CHERCHER_PROCHE` →
   dernière position connue du proche ; `AIDER` → agent le plus proche non
   sorti ; `SUIVRE` → sortie visée par le flux local ; `REVIRER` → espace
   précédent. Non mappé ⇒ `stay`, journalisé `intention: none`.
3. Spawn : distribution déterministe (min 0,4 m), plus de 6 points réutilisés.
**Preuve** : `test_physique` — « rester reste » (position stable à ±0,2 m sur
10 s), « chercher bouge et reste dans la zone », « suivre suit », « 60 agents
répartis, pas 6 grappes ».

### C2 — Perception (1,5 j)

`Scene.perception_for` calcule depuis le monde et la physique :
`seen_agents` (8 plus proches, ordre déterministe), `crowding` (noyau 2 m),
`distance_to_danger` (origine du foyer/fumée à ajouter dans la chronologie),
`exits_visible`, et un `State` qui **évolue** (stress ← menace + densité +
durée ; fatigue ← distance parcourue ; visibilité ← fumée et distance).
**Preuve** : tests purs — « seul, il ne voit personne » ; « serrés, la densité
monte » ; « près du foyer, la visibilité baisse » ; et **conséquence** :
`SUIVRE` devient atteignable chez un visiteur (herding 0,8) dès que la preuve
sociale ≥ 0,6.

**État 2026-11-18 : fait.** `Scene` recopie les positions physiques en tête
de tick, calcule les 8 voisins (ordre distance puis uid), la densité en noyau
de 2 m, la distance au foyer (`Timestep.hazard_origin`), les sorties visibles
(distance + ligne de vue) et un `State` qui évolue (stress ← proximité +
entassement, fatigue ← mètres parcourus, co-exposition ← fumée, visibilité
← co-exposition). L'état est idempotent dans un tick. La preuve sociale monte
avec le nombre de voisins (8 voisins = poids plein) : 4 voisins suffisent à
un visiteur pour suivre. 9 tests dans `tests/v3/test_perception.py`.

### C3 — Calendrier, bras, escalade (2 j)

1. `should_decide` par bras (§4.2), sorti de `Agent.react`.
2. Critères d'escalade (§4.4) + `agent.escalation` + `taux_escalade`.
3. ε (SHA-256, jamais `hash()`), et `LLMPolicy(alias=agent.llm_alias)` dans
   `hybrid_decide` (le tier du profil est aujourd'hui ignoré).
4. Schéma `maree.event/1.1` (additif) : `arm`, `escalation_cause` dans
   `agent.decision` ; type `agent.escalation`. `1.0` reste accepté.
**Preuve (coût nul, stub compteur)** : sur le scénario bloqué, `regles` = 0
appel, `hybride` escalade exactement 4 fois à t2 avec la cause
`information_contradictoire`, `llm` appelle à chaque changement perçu et
**pas** deux fois pour la même perception. Un test échoue si l'hybride est à
zéro.

### C4 — Mesure (2 j)

1. Coût : appels **tentés/réussis**, replis par cause, jetons **par ligne du
   journal** (plus jamais `_last_decision`) ; temps mural séparé
   (`wall_llm` = somme des latences de trace, `wall_physique`, `wall_total`).
2. Indicateurs de foule : porter `src/maree/metrics/indicators.py` (I1–I7)
   avec ses leçons déjà encodées (partie active, noyau 2 m, censure
   `max_ticks`, I7 depuis le premier événement de danger). Un adaptateur
   `v3.Agent → AgentState`.
3. Émergence : `consensus` sur les agents **actifs** ; `couplage` = part
   d'agents dont la préférence **change** après un ouï-dire (pas seulement
   « source = ENTENDU ») ; `E_social` avec le null (mémoires brouillées)
   réellement exécuté.
4. Chaque JSON de campagne porte un bloc `metrics` avec formule et unité.
5. **Note par décision, pas par agent** : `part_des_decisions_visant_une_sortie_crue_bloquee`,
   et la **première** cible d'évacuation séparément de la dernière. Une politique
   qui se corrige à t10 n'est pas une politique qui a bien choisi à t2.
**Preuve** : un test vérifie que `jetons == somme des traces du journal` sur
un run à 2 décisions par agent ; un test vérifie que I5 est nul sur un monde
vide et > 0 au goulot ; un test vérifie que le score micro distingue
« A puis B » de « B puis B ».

### C5 — Monde macro calibré (1,5 j)

Choisir (population, largeur de sortie, surface) pour que le bras `regles`
produise un goulot réaliste : densité de pointe **0,8–1,5 pers/m²** au
passage, dernier sorti entre **40 et 80 s**. Calcul de départ : débit ≈ 1,3
pers/(m·s) × largeur ; 60 agents sur 2 sorties de 1,4 m ⇒ ~23 s de flux, donc
une file visible. `hall_3` (9 600 m²) n'y arrive pas à 60 agents : réduire la
surface utile ou la largeur des sorties. **Geler les paramètres avant toute
comparaison** (calibration ≠ validation).
**Preuve** : le goulot est mesuré dans le bras témoin, et I5 ne culmine pas
au spawn.

### C6 — Campagne macro et rapport (2 j)

3 bras × 5 mondes × 2 scénarios (bloqué, contradiction officielle), avec
`hybride` ε ∈ {0, 0,25}. Mesures : part entrant dans une sortie crue
bloquée, I3, I5, I7, répartition par sortie, coût (appels, jetons, temps),
taux d'escalade par cause.
**Preuve** : le résultat micro se retrouve-t-il dans la foule ? Si non, c'est
un résultat (la foule absorbe le biais individuel) et il se publie.

### C7 — Communication (2 j, conditionnel)

Émission après les décisions (comme le plan §5 le prévoit) : qui parle
(`altruism`, rôle), quoi (action + cible, ou danger cru), à qui
(`seen_agents`). Réception déjà codée. Plus : une annonce **devient** une
croyance pondérée par `authority_trust` (D8).
**Preuve** : H4 (cascade + démenti tardif) et H5 (le démenti corrige la
croyance, pas l'action engagée) deviennent mesurables. **Sans C7, le rapport
ne peut pas revendiquer B2/B3 comme mesurés.**

---

## 6. Ordre et portes

```
C0 ─► C1 ─► C2 ─► C3 ─► [G1] ─► C4 ─► C5 ─► [G2] ─► C6 ─► [G3] ─► C7 ─► rapport
```

| Porte | Condition | Si échec |
|---|---|---|
| **G1** | À coût nul : `regles`=0 appel, `hybride` escalade avec la bonne cause sur le scénario bloqué, `llm` ne rappelle pas sans changement, « rester » reste | On ne mesure rien ; on répare C2/C3 |
| **G2** | Le bras `regles` produit un goulot 0,8–1,5 pers/m², I5 ne culmine pas au spawn, I7 ∈ [40, 80] s | On recalibre C5, pas la politique |
| **G3** | Sur 5 mondes : la part entrant dans une sortie crue bloquée est stable par bras (petit ≫ grand), et I3/I5/I7 sont cohérents avec la décision | On publie le désaccord décision/foule comme résultat |

Ordre de grandeur : **C0–C3 ≈ 5 j**, **C4–C5 ≈ 3,5 j**, **C6 ≈ 2 j**,
**C7 ≈ 2 j**. Rien de tout cela ne demande de GPU avant C6.

---

## 7. Hors périmètre (gelé jusqu'à G2)

- RAG et F2 (pertinence) : le corpus et bge-m3 ne sont pas en cause.
- Godot / trames : le contrat tient ; il suivra `1.1` sans refonte.
- `two_floor`, IFC, procédural.
- `decision_head` / OpenJev.
- Toute campagne multi-graines (> 5 mondes) tant que G1 n'est pas passé.

---

## 8. Ce qu'on ne dira plus

- « L'hybride ne déclenche le LLM que sur l'ambiguïté — comportement voulu »
  (il ne déclenche **rien**).
- « 5 graines, 5/5 » (c'est un run rejoué).
- « Les agents perçoivent la densité / la distance au danger » (faux).
- « L'émergence est mesurée » (le consensus inclut les sortis, le couplage
  ignore les dangers).
- « La mémoire J−3 » (jamais amorcée en run).
- « 60 agents » quand il n'y a pas de physique : dire « décisions seules ».
- « Le LLM coûte X jetons » tant que C4 n'est pas passé.

---

## 9. État d'avancement

| Chantier | État | Preuve |
|---|---|---|
| C0 — triage + ADR | **fait** | ADR-014 ; JSON dans `runs/v3/avant_correctif/` ; bandeaux sur les deux rapports |
| C1 — physique honnête | **fait** | 4 tests : « rester reste » (±0,3 m sur 10 s), `Target.at` réel, 60/60 placements distincts (2,37 m mini), mapping des 7 actions |
| C2 — perception | **fait** | 9 tests : 8 voisins ordonnés, densité noyau 2 m, distance au foyer, sorties visibles (A/C oui, B à 60 m non), état qui évolue (fatigue = 10 m × 0,0015), `SUIVRE` atteignable (4 voisins), idempotence |
| C3 — calendrier + bras + escalade | à faire | — |
| C4 — mesure | à faire | — |
| C5 — monde macro | à faire | — |
| C6 — campagne | à faire | — |
| C7 — communication | à faire (conditionnel) | — |

Mesure de contrôle C1 (hall_3, 60 agents, 10 ticks sans décision) :
déplacement maximal **0,10 m** — les agents tiennent leur position au lieu de
marcher vers le coin.
