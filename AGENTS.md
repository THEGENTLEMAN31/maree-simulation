# AGENTS.md — mémoire de chantier

_Ce fichier n'est pas de la documentation utilisateur. C'est ce qu'il faut
savoir **avant** de toucher au code, et surtout ce qui a déjà coûté du
temps. Mis à jour le 2026-10-28._

---

## 1. Ce qu'est ce dépôt

MARÉE v2 : simulation d'évacuation de foule à Port-Aubel, 60 agents,
trois sorties, une croyance par agent. Python 3.12+, `uv`, Hydra,
LangGraph, JuPedSim, FAISS, Redpanda, Godot 4.

La v1 est conservée par le tag `v0-prototype`. **Ne pas la ressusciter** :
elle décidait à chaque tick (2 160 appels LLM par run) et n'était pas
rejouable de bout en bout.

---

## 2. Pièges d'environnement (tous rencontrés pour de vrai)

### Python

- **`hash()` est salé par processus** (`PYTHONHASHSEED`). Deux runs
  « identiques » divergent. Utiliser SHA-256 pour toute graine dérivée.
  C'est corrigé dans `agents/graph.py` et `engine/simulation.py`.
- Le venv est en **Python 3.13** (`uv` l'a choisi), le lock est fait pour
  `--python 3.12`. Les deux fonctionnent ; ne pas « corriger » l'un pour
  l'autre sans raison.
- Les dataclasses `slots=True` n'ont **pas** de `__dict__` :
  `dataclasses.asdict()` pour sérialiser (`Passage` dans le RAG).

### llama.cpp

- `parallel = 4` **et** `ctx-size = slots × fenêtre` : `8192 = 4 × 2048`.
  Un `ctx-size` de 4096 avec 4 slots donne 1024 tokens par slot, et les
  prompts réels (~700 tokens + 256 de sortie) sont rejetés.
- `reasoning = off` + `max_tokens = 256` sont **obligatoires**. Sans eux,
  Gemma 4 émet ~460 tokens de raisonnement : 9 s par décision au lieu de
  2,8 s.
- Budget VRAM (RTX 3050, 4 Go) : E2B 2,9 Go + bge-m3 0,42 Go = 3,3 Go.
  **E4B (4,7 Go) évince un modèle.** Si OOM au premier `make up` :
  `parallel = 2`, `ctx-size = 4096`.
- **A5 exige un troisième modèle** : `qwen3-0-6b` Q4_K_M (378 Mo,
  `unsloth/Qwen3-0.6B-GGUF`). Le conteneur a été recréé le 2026-10-30 avec
  `--models-max 3` : les deux tiers tournent pour de vrai (mesuré : 24
  appels `gemma4-e2b` + 73 `qwen3-0-6b` dans un run hybride, 0 repli).
  Tant qu'il tourne avec `--models-max 2`, les appels au petit modèle
  répondent « model not found » et l'adaptateur **retombe sur le grand**
  en le journalisant (`requested_model` ≠ `model`). Un run « two_tier »
  n'est donc pas forcément un run à deux modèles : vérifier la trace.
- **Le routeur normalise les points en tirets.** L'alias `qwen3-0.6b` du
  preset est annoncé `qwen3-0-6b` par `GET /v1/models`. Configurer
  `small_model: qwen3-0.6b` donne un 404 à chaque appel « small », et le
  repli sur le grand **ressemble** à un run à deux tiers. `configs/llm/`
  utilise donc le nom annoncé.
- Le routeur llama.cpp **n'annonce pas** un modèle absent : `GET /v1/models`
  liste les alias déclarés, chargés ou non (`status.value`). Un alias
  manquant du preset renvoie 404 au premier appel, pas à l'indexation.
- bge-m3 est un BERT : **pooling CLS**, pas mean pooling.

### JuPedSim 1.4

- Un agent doit être **à plus de 0,2 m des parois** et **à plus de 0,4 m
  d'un autre agent**, sinon `RuntimeError` à l'ajout. D'où `_place()` en
  spirale déterministe et `_safe_position()`.
- L'issue est un **polygone à l'intérieur** du domaine marchable. La
  normale brute pointe vers l'extérieur pour B et C : `stage_polygon()`
  la réoriente vers le centroïde.
- `switch_agent_journey(agent_id, journey_id, stage_id)` prend **trois**
  arguments (le `stage_id` est obligatoire).
- `Simulation(..., seed=…)` est accepté (via `**kwargs`).
- Les agents sortis sont retirés : `removed_agents()` / `agents()`.
  **Corollaire** : `switch_agent_journey` sur un agent sorti lève
  `RuntimeError: Trying to access unknown Agent N`. `set_destination()`
  doit vérifier `_alive_ids()` avant d'appeler — sinon fermer une issue
  en cours de run plante.
- Les obstacles sont passés en **trous** du polygone marchable. Sans eux,
  les agents traversent la scène.

### Simulation (leçons de modèle)

- **Un déclencheur de niveau est un piège.** `smoke_visible` reste vrai
  jusqu'à la fin : sans `known_signals`, chaque agent redécide à chaque
  tick (60 appels/tick, le coût de la v1 reconstruit). Fumée, annonce et
  fermeture d'issue sont donc des **fronts**, mémorisés par agent
  (`known_signals`).
- **Sans signal de danger, les agents restent** (`rules_decide` →
  `STAY`). La version qui faisait fuir tout le monde dès t0 rendait la
  fumée de t10 décorative : l'évacuation était finie au tick 9.
- **Toute annonce valait danger.** `rules_decide` testait
  `bool(percept.announcement)` : « Veuillez rester calmes » faisait
  sortir les 48 agents à règles. La clarté du message (H1) n'était donc
  mesurable que sur les 12 agents LLM — et un plan 2×2 à 5 graines l'a
  montré : 190 s dans les deux bras. Une annonce n'est un ordre que si
  elle en contient un (`_EVACUATION_WORDS`), et si elle nomme une sortie
  par son étiquette (`_announced_exit`), les agents y vont — ce qui crée
  un goulot que I5 peut mesurer. Corrigé avant la campagne X1–X7.
- `agent.decision` ≠ `agent.evacuated`. Le second est un fait physique
  (l'agent a franchi l'issue), le premier une cognition. Les confondre
  faisait compter 60 « décisions » fantômes par run.
- **Un appel LLM raté ne fait pas échouer le run** : le graphe replie
  sur les règles. Sans serveur, `maree run` produisait 43 « appels LLM »
  en 11 s et un résultat d'apparence normale. `RunResult.llm_ok` compte
  les succès, le journal marque `llm.fallback=true`, et la CLI crie
  quand `llm_ok == 0`. Un run à 0 succès n'est **pas** un run hybride.
- **Un souvenir de J−3 s'efface en 200 s si on ne fait rien.** La récence
  vaut `1 / (1 + âge/20)` : un épisode daté −25 920 avait un score de
  0,0008 et n'était jamais rappelé. La préhistoire a donc un **plancher de
  récence** (0,35) dans `memory/store.py`, documenté comme un choix : un
  souvenir ancien mais saillant ne s'efface pas comme une perception de la
  dernière minute. Aucun run d'avant A1 n'a de tick négatif, la campagne
  X1–X7 n'est pas affectée.
- **Une injection appliquée dans le tick est une perception à deux
  vitesses.** Les commandes du client sont drainées en tête de
  `_world_events`, donc au tick suivant : une fumée injectée au milieu
  d'un tick serait vue par certains agents et pas d'autres. `submit()` ne
  fait que mettre en file ; `_drain_injections` journalise
  `control.injection` **avant** l'événement qu'elle provoque.
- **Un mode asynchrone révèle les vérifications qui lisent l'état courant
  au lieu de l'état perçu.** `_check_temporal` (C6) comparait
  `self._signal_events["smoke"].t_prod` à `percept.tick` : en synchrone,
  la décision est appliquée dans le tick où elle est perçue, donc les deux
  coïncident et le bug reste invisible. En asynchrone, une décision de t1
  appliquée à t12 voyait la fumée de t10 et se déclarait en violation —
  12 violations fantômes dans `c4_async_01`. Corrigé : on ne vérifie un
  signal que si l'agent l'a **perçu** (`smoke_visible`, `announcement`,
  `closed:`). Toute vérification causale doit lire la perception, jamais
  le monde.
- **Une latence réelle n'a de sens en ticks que si l'horloge est cadencée.**
  En asynchrone, la tâche est lancée au tick de la perception et ramassée
  au tick où elle aboutit ; `tick_delay_s` (0,25 s par défaut dans ce
  mode) fixe le rapport : 3 s de LLM = 12 ticks. Sans cadence, la boucle
  tournerait plus vite que le modèle et aucune réponse n'arriverait
  jamais. Ce n'est pas une latence inventée : c'est la latence mesurée,
  convertie par une cadence déclarée.
- **Un repli sur les règles sans cause nommée n'est pas un incident.**
  `graph._validate` renvoyait `fallback: true` sans dire pourquoi. A4
  exige « tracé et dénombré » : la cause (`no_response`, `unparseable`,
  `unknown_exit`, `out_of_role`, …) est maintenant portée jusqu'à
  `agent.incident`, et `out_of_role` est distinct de `unknown_exit` — un
  visiteur qui nomme B ne se trompe pas de vocabulaire, il parle d'un lieu
  qu'il ne connaît pas.
- **`runs/` dans `.gitignore` interdit toute exception enfant.** Git ne
  descend pas dans un répertoire exclu : `!runs/demo_replay/events.jsonl`
  ne marche que si le motif parent est `runs/*`, pas `runs/`. C'est ce qui
  rend le run versionné E3 visible.
- **Le rejeu confondait normalisation et divergence.** `graph._to_intention`
  efface la cible de `stay`/`search` et lit `follow <sortie>` comme
  `go_exit` : 20 des 49 décisions du run `demo_replay` étaient comptées
  « divergentes » alors qu'elles étaient seulement normalisées. Le rejeu
  journalise désormais `parsed` (sortie du parseur) et vérifie deux choses
  séparément : `parse(raw) == parsed`, puis `parsed → intention` par les
  seules normalisations connues. Un repli règles (`fallback: true`) est
  compté à part (`replis_regles`), pas comme une divergence.
- **Un `run_id` explicite déjà journalisé était accepté** : le journal étant
  en append, deux runs se retrouvaient dans le même `events.jsonl` avec un
  `seq` continu. `maree run` refuse maintenant un `run_id` déjà présent.
- **LangGraph ne propage que les canaux déclarés dans le `TypedDict`.** Un
  nœud qui renvoie une clé absente du schéma ne plante pas : la valeur est
  simplement perdue à la sortie du nœud. `query` était calculé dans
  `retrieve` puis effacé, et `rag.suspect` sortait avec une question vide.
  Toute donnée qui traverse deux nœuds doit figurer dans `AgentState`.
- **L'inspection d'un agent et l'injection d'événements ne se testent pas
  en Python.** D2 et D3 étaient « tenus » côté protocole et absents du
  client : le test vérifiait le transport, pas l'usage. Un test de client
  (`make godot-test`) fait le trajet complet — connexion, `hello`,
  snapshot, `ack`, écho d'injection, persistance — contre `maree live`.
- **Le tampon d'entrée de `WebSocketPeer` vaut 64 Kio**, contre des
  instantanés de ~70 Ko à 60 agents : le client se déconnecte au milieu du
  run, sans erreur visible. Porté à 8 Mio. Tout client doit accepter
  100 Ko par trame.
- **Le corpus d'annonces contient douze variantes contradictoires**, toutes
  disponibles à partir de t10 : une décision qui interroge `annonces/`
  reçoit trois consignes nommant des sorties différentes (483 décisions
  en retrouvent une en X12, 358 en reçoivent de contradictoires). Le
  percept porte la vraie annonce à part, et le seuil de `rag.suspect`
  (0,17) ne voit rien — le score est bon (0,27). À filtrer par le texte
  réellement diffusé si l'on veut un modèle propre ; consigné en Q5.
- **L'inspection d'un indicateur était un chemin en CLI, pas un geste.**
  `sources` porte la plage de `seq`, `maree trace` remonte la chaîne, et
  depuis le 2026-11-01 **Godot fait le clic** (`indicators.sources` →
  `event`) : testé par `make godot-test`, pas seulement documenté.
- **Le dernier tick d'indicateurs est dégénéré** : tout le monde est
  sorti, donc I1/I2/I5/I6 valent 0. Utiliser `metrics.summarise()` (pic
  pour I5/I6, moyenne sur la partie **active** pour I1/I2) et non
  `indicators[-1]`. Le tick dégénéré était inclus dans la moyenne : un
  run de 19 ticks comptait un zéro sur 19, un run de 55 ticks un sur 55,
  donc les runs courts étaient pénalisés par leur durée. Corrigé.
- **I6 = 0 par construction si aucune sortie ne ferme.** I6 est la part
  des agents croyant en une sortie fermée ; avec `close_exit: null`
  (config `demo`, celle de X1, X3–X7), elle ne peut pas bouger. Seul X2
  passe `run: e2e` (fermeture de A à t14). Ne pas déclarer I6 dans un
  protocole qui ne ferme rien.
- **I4 n'est pas une durée, c'est une horloge.** I4 = tick × 10 s : le
  temps depuis t0, qui inclut l'attente avant le premier signal et se
  fige au plafond `max_ticks` dès qu'une partie de la foule ne sort pas
  (X1 ambigu : I4 = 720 s pour un dernier sorti à t31). **I7** (premier
  signal de danger → dernier sorti) reste défini sous censure et ne
  dépend plus de l'instant où l'on a commencé à compter. Il **ne retire
  pas** l'heure de l'annonce du délai : dans X1 la fumée de t5 est le
  premier signal pour tous les bras, donc I7 = I4 − 50 s ; il retire le
  temps d'avant-signal et le plancher de censure. Le signal est le
  premier **événement du monde** (fumée, annonce, fermeture), pas le
  premier agent qui bouge : un guide ou un proche cherché part avant
  tout danger. I4 est gardé : il dit « quand », I7 dit « combien de
  temps ».
- **Une cible validée contre le plan n'est pas une cible connue.** La
  garde de `_to_intention` ne vérifiait que `target in plan.exits`. Un
  visiteur, qui ne connaît que A, pouvait donc nommer B — et y aller.
  Incidence mesurée sur la campagne pré-correctif : 108 décisions dans
  X1, 349 dans X4, 12 dans X6. Toute cible `go_exit`/`guide` est
  maintenant validée contre `Profile.knows()` ; si elle échoue, le
  graphe replie sur les règles, qui ne choisissent que parmi
  `_known_open`. **Corollaire** : deux tests de `test_graph.py`
  passaient par la fuite (profil `visiteur` + cible B ou C) ; ils
  utilisent désormais `habitue`.
- **I5 saturait à 2.0 avec une grille de 1 m.** Séparation minimale de
  0,4 m : au plus 2 agents par cellule, donc le pic valait 2 dans tous
  les runs, sans variance. Corrigé : I5 est un **noyau circulaire de
  2 m** (0,08 à 1,51 pers/m² selon le bras) ; la grille de 1 m reste
  calculée pour l'affichage du client (`density_cells`), pas pour
  l'indicateur.
- Les protocoles `configs/experiment/*.yaml` sont le **contenu** du
  groupe Hydra : pas de `# @package _global_`, pas de clé `experiment:`
  englobante, sinon `cfg.experiment.experiment.arms`.
- **Une cible rendue par le LLM est du texte libre.** Il a répondu
  `guide → "Signalétique — la scène principale"` et `follow → "C"`.
  Le premier devenait une croyance de sortie : au tick suivant l'agent
  croyait qu'elle avait fermé (`sortie_fermee`) et évacuait sur un
  événement inexistant. Le second ne correspondait à aucun agent : le
  moteur le figeait sur place. Toute cible est désormais validée contre
  le plan (`exits`, `zones`, motif `A\d{2}`), et `follow <sortie>` est
  lu comme `go_exit <sortie>`.
- **`missing_kin` était un déclencheur de niveau.** Un proche resté hors
  de vue faisait redécider l'agent à chaque tick : 142 des 202 appels
  LLM d'un run. Il est maintenant mémorisé comme la fumée, et réarmé si
  le proche réapparaît.
- **`SEARCH` visait `walkable[0]`**, un sommet posé sur la limite du
  domaine, souvent dans une issue : les agents « cherchaient » en
  sortant. On cherche dans la zone où l'on est, et la recherche est
  bornée (`SEARCH_TICKS`) — sinon un agent cherche indéfiniment.
- **Les proches étaient appariés après le placement**, par ordre de
  liste : deux tirages indépendants dans une zone, souvent à plus de
  10 m. 14 des 16 agents « famille » cherchaient un proche dès le tick 1
  et sortaient avant la fumée. Les paires sont maintenant placées
  ensemble, dans la même zone, à moins de 2 m.
- **Un guide qui n'a rien vu ne prévient personne.** `_diffuse`
  transformait un `GUIDE` de tick 1 en « il faut sortir par… » ; tout
  message reçu valant danger, la foule sortait avant la fumée. On ne
  parle que si l'on a perçu quelque chose.
- **Un petit modèle ne raisonne pas, il suit la forme du prompt.** Quatre
  formats ont été essayés sur `qwen3-0-6b` (0,6 Md), et trois échouent :
  - JSON à vocabulaire ouvert → `{"action":"search","confidence":0.0}`, le
    gabarit recopié, jamais une sortie (55 décisions sur 55) ;
  - **liste de mots-clés** → il choisit **la première option**, quel que
    soit le contexte. `SORTIR A` en tête → les visiteurs évacuent au tick
    3, **avant la fumée de t10** ; `RESTER` en tête → personne ne part
    jamais. Ce n'est pas du hasard, c'est de la position ;
  - question binaire `OUI/NON` → instable : la réponse dépend de la
    formulation du prompt système et vire au OUI par défaut.
  Ce qui marche : une **règle écrite** et deux drapeaux (`Fumée visible :
  oui/non`, `Annonce d'évacuation : oui/non`). Mesuré 6 essais par cas
  avec la persona réelle : `calme` → RESTER 6/6, `fumée` → SORTIR 6/6,
  `annonce` → SORTIR 2/6 (limite consignée, pas corrigée).
  **Corollaire à assumer** : le tier « small » *applique* une politique,
  le tier « big » la *juge*. Et le prompt système du petit modèle ne doit
  pas contenir le contrat JSON du grand (`Profile.persona` le retire) :
  les deux consignes mêlées le faisaient répondre OUI à t1, sans fumée.
  Les chiffres X10/X11 de la vague 3 sont **faux pour cette raison** et
  ont été refaits ; `llm.small_protocol: open` rejoue le premier défaut.

### Stockage et requêtes

- **DuckDB + `read_json_auto(union_by_name=true)` sur des JSONL
  hétérogènes, c'est un piège silencieux.** `data` change de forme à
  chaque type d'événement ; l'inférence finit par typer `data` en JSON
  structuré et `json_extract` échoue (`Malformed JSON … Input: "llm"`) ou
  renvoie des valeurs entre guillemets. `queries/_base.sql` lit donc
  **ligne par ligne** (`read_csv(columns={'line':'VARCHAR'}, delim='',
  quote='', escape='', ignore_errors=true)`) et laisse les requêtes
  extraire ce qu'elles veulent.
- **`max()` sur des chaînes classe « 90.0 » au-dessus de « 220.0 ».** Le
  `CAST(… AS DOUBLE)` doit être **à l'intérieur** du `max`, sinon I7
  ment sans erreur. Un test le garde.
- **`state.json` est atomique et ne garde que la dernière valeur.** Un
  client peut lire pendant que le run écrit : sans `os.replace`, il verrait
  un JSON tronqué. Et « le dernier run » se trie par `mtime`, pas par nom
  (les identifiants contiennent une graine et un hachage).

### Corpus RAG

- Un passage mal daté ou tagué d'un profil inexistant **n'échoue jamais** :
  il devient simplement invisible. Deux cas réels : les 43 annonces
  étaient datées t120–t590 pour un run de 90 ticks (aucune n'était
  lisible), et 16 passages portaient le profil `amis`, absent du moteur.
  `tests/test_corpus.py` vérifie profils, dates et lisibilité par profil.
- `scripts/generate_corpus.py` **ne réécrit pas** un fichier existant
  (`if path.exists(): return`). Pour régénérer : supprimer `world_corpus/`
  **après avoir sauvegardé les 14 fichiers écrits à la main** (annonces,
  protocole, plans, fiches de profil), que le script ne produit pas.

### Environnement de l'hôte

- **LangSmith sature les logs.** `~/.bashrc` exporte
  `LANGCHAIN_TRACING_V2=true` ; le quota mensuel de traces est épuisé,
  donc chaque nœud LangGraph émet un `LangSmithRateLimitError` (429) dans
  la sortie. **Aucun effet sur les runs** (les événements partent en
  asynchrone), mais la sortie devient illisible : 85 runs ont produit
  des milliers de lignes de bruit. Pour une campagne propre :
  `LANGCHAIN_TRACING_V2=false uv run maree experiment …`. La variable est
  dans le profil de l'utilisateur, pas dans le dépôt — ne pas la
  « corriger » dans le code, il n'y a rien à y corriger.
- **Le port 22 sortant est bloqué** (constaté après le reboot du
  2026-10-29 : `ssh: connect to host github.com port 22: Connection
  timed out`). GitHub répond sur `ssh.github.com:443`, mais
  `~/.ssh/config` ne déclare que `Host github.com` — la clé n'est donc
  pas choisie pour `ssh.github.com` (`Permission denied (publickey)`).
  Pour pousser sans toucher au profil de l'utilisateur :

  ```bash
  GIT_SSH_COMMAND="ssh -i ~/.ssh/id_github -o IdentitiesOnly=yes" \
    git -c url."ssh://git@ssh.github.com:443/".insteadOf="git@github.com:" push
  ```

  `-i` est obligatoire : sans lui, ssh essaie `id_ed25519` et `id_rsa`,
  qui ne sont pas autorisées sur ce dépôt.

### Docker

- La publication de ports est cassée dans cet environnement. Seul le
  relais sur **16080** fonctionne (`~/.local/share/maree-relay/`).
- `apt-get` n'a **pas** de réseau pendant les builds. PyPI fonctionne.
- Le conteneur `maree-llama-cpp` tourne ici sur **8080** avec le preset
  du dépôt (8192/4), lancé à la main. `docker compose up` reconstruirait
  l'image (apt sans réseau) et la publication de ports est cassée. Le
  8080 de l'hôte appartient à `llama-stack.service` : depuis l'hôte, on
  joint le conteneur par son IP, pas par `localhost`.
- **L'IP du conteneur change au redémarrage de la machine.** Après un
  reboot, `docker start maree-llama-cpp` (le conteneur est en
  `Exited (255)`, pas de politique de redémarrage) puis relire l'IP :
  `docker inspect maree-llama-cpp --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'`.
  Le 2026-10-29 elle est passée de `172.19.0.3` à `172.19.0.2` : un
  `MAREE_LLM_URL` figé dans un script pointait dans le vide, et les runs
  redevenaient des replis règles sans le dire.
- **Recréer le conteneur change aussi de réseau.** Le 2026-10-30, pour
  passer à `--models-max 3`, `docker run` sans `--network` l'a posé sur
  le bridge **par défaut** : l'IP est devenue `172.17.0.2`, et non plus
  `172.19.0.x`. Toujours relire l'IP après un `docker run`, pas seulement
  après un reboot.
- `MAREE_LLM_URL` est la variable lue par `configs/llm/llamacpp.yaml`.
  Le compose exportait `MAREE_LLM_BASE_URL`, que **personne** ne lisait :
  le run retombait silencieusement sur l'URL par défaut.
- Ne pas ajouter de service Godot dans `docker-compose.yml` : le rendu
  OpenGL en container exige X ou noVNC pour un gain nul. Godot tourne
  nativement sur l'hôte (`make godot`), sur l'iGPU Intel. Les deux
  conteneurs noVNC/headless ont été supprimés le 2026-10-28 : le VNC
  brûlait **87 % de CPU** à rendre dans le vide, pour un client qu'on
  ouvre de toute façon à la main.

---

## 3. Conventions non négociables

1. **Le journal est la source de vérité.** Tout ce qui n'est pas journalisé
   n'existe pas. Un appel LLM sans trace = run non rejouable.
2. **Aucune horloge système** dans la logique du monde. Le temps est un
   entier (`tick`). `t_real` est réservé au journal.
3. **Ordre canonique** : les décisions s'appliquent par `agent_id`
   croissant, jamais dans l'ordre d'arrivée des réponses.
4. **Perception figée** : tous les agents perçoivent le même instant T.
5. **Un `run_id` ne se réutilise jamais.** Le journal est en append.
6. **Les agents ne parlent à la physique que par une intention.** Ni
   croyance, ni message dans l'adaptateur physique.
7. **Le narrateur lit tout, n'écrit rien chez les agents.** Aucun agent ne
   s'abonne à `narrative.generated`.
8. **Le vocabulaire du domaine est en français** (`croyance`, `intention`,
   `sortie`, `écart`). Le code technique peut rester en anglais. Ne pas
   mélanger dans un même identifiant.
9. **Pas de framework décoratif.** Si un outil n'a pas de rôle mesurable,
   il sort (voir `docs/architecture-v2.md` §10).

---

## 4. Mesures de référence

| Mesure | Valeur | Méthode |
|---|---|---|
| JuPedSim, 60 agents × 2 000 pas | 0,06 s → **1 761×** temps réel | spike `spike4.py` |
| JuPedSim + `SocialForceModel` | 0,07 s → 1 353× | idem |
| Déterminisme JuPedSim | identique à 1e-9 | idem |
| Un appel LLM (E2B) | 2,8 s | v1 |
| Débit `parallel=1` / `parallel=4` | 0,36 / **1,43** décision/s | v1 |
| Run 60 agents à règles, démo (v2) | 20 ticks, 1 023 événements, **0,8 s**, 60/60 sortis | `run_demo_02` |
| Run 60 agents à règles, piège (v2) | 90 ticks, 1 204 événements, 1,1 s, **54/60** (6 visiteurs piégés) | `run_trap_07` |
| Décisions, scénario piège | **259** (dont 22 `sortie_fermee`, 142 périodiques) | `run_trap_07` |
| Protocole X1, 5 graines × 4 bras | I7 clair_tôt 380 s, ambigu_tôt 370 s, clair_tard 280 s, ambigu_tard 440 s (p = 0,67 sur la clarté) ; I3 **1,00 / 0,95 / 1,00 / 0,95** (p = 0,0095) ; **2/10 censurés** avec un ordre clair, **10/10** sans | `experiment_x1` |
| Protocole X2 (meneurs), 10 graines × 2 bras | I7 **265 s des deux côtés** (p = 0,91), I3 0,90 / 0,89 (p = 0,62) ; I5 0,48 contre 0,56 (p = 0,058, sens inverse) : aucun effet mesurable | `experiment_x2` |
| Protocole X3, 5 graines × 2 bras | I1 0,98 / 0,97, I5 0,40 / 0,40, I7 220 s des deux côtés ; mural **18,1 → 14,1 s** (5 paires sur 5, p = 0,095, non tranché à 5 paires) | `experiment_x3` |
| Protocole X4, 5 graines × 3 bras | `llm_60` **42/60 sortis** (5/5 censurés, 477 appels, 89,5 s), hybride 53/60 (5/5), règles 55/60 (4/5, 11,1 s) ; piégés : 0 à 8 visiteurs en tout-règles, **9 à 19 visiteurs sur 24 + 1 à 7 habitués** en tout-LLM | `experiment_x4` |
| Campagne rejouée (X1–X14 + témoins C1) | **260 runs, 14 181 appels / 14 181 succès, 0 repli** ; 1 409 incidents (9,9 % des appels) | `runs/experiment_x*.json` |
| C1, le bus ne touche pas aux indicateurs | X3K (Redpanda) contre X3M (mémoire) : médianes I1 0,98 / I3 1,00 / I5 0,48 / I7 220 s identiques (p ≥ 0,60) ; mural 24,2 contre 18,2 s (**+33 %**, 5 paires sur 5) | `experiment_x3k` / `experiment_x3m` |
| C1, volume publié | **10 084 événements** sur 4 topics pour 10 runs (453 instantanés exclus) | journaux `run_x3k_*` |
| I5 par noyau de 2 m | 0,08 à 1,51 pers/m² selon le bras (0,32–0,56 pour la population de référence) ; la grille de 1 m, elle, valait 2,0 partout | campagne 2026-11-01 |
| Preset 8192/4 (E2B) + bge-m3 | `n_slots = 4`, `n_ctx_slot = 2048`, **1 980 Mo / 4 096** | `nvidia-smi`, RTX 3050 |
| Débit LLM, concurrence 1 / 4 | 0,69 / **1,94** décision/s | 12 appels, ~700 tokens |
| Run hybride 12 LLM + 48 règles, démo | 21 ticks, **44 appels / 44 succès**, 21,9 s, **60/60** | `run_hybrid_08` |
| Récits du chroniqueur | 4, **0 repli**, chiffres conformes au digest | `run_hybrid_08` |
| Trames diffusées, démo à règles | **1 024** (212 décisions, 212 croyances, 60 messages, 434 écoutes, 60 évacuations, 21 instantanés) | `maree serve` |
| `maree index` sur le corpus réel | 215 passages en **7 s** | bge-m3, `data/rag` |
| Chaîne causale (B4) | **820 / 1 023** événements avec `causation_id`, 160 chaînes | run `demo_replay` |
| Récupération (F2) | P@1 **0,417**, P@3 **0,750**, MRR **0,569** sur 24 requêtes annotées | `eval/rag_queries.yaml` |
| Rejeu E3 | `ok: true`, 49/49 décisions concordantes, 3 replis annoncés | `maree replay --run-id demo_replay` |
| Protocole X10, 4 bras × 5 graines | `lag_llm` 0 (sync) → **2** (async, les deux tailles) ; `lag_ticks_median` 0 → 4 (5 au maximum) ; `lag_indicator` 1 à 2 | `experiment_x10` |
| Protocole X11, 2 bras × 5 graines | sync I3 1,00 / I7 220 s / lag 0 ; async **1,00 / 230 s** / `lag_ticks_median` 4, max 6 | `experiment_x11` |
| Protocole X12 (E5), 5 bras × 5 graines | `tous_grand` 43 appels, 20 073 jetons, I3 1,00, I7 100 s ; `tiers_regles` **21 / 10 724 (−47 %) / 1,00 / 100 s** ; `protocole_seul` 40 / 13 207 (−34 %) / 1,00 / 110 s ; `deux_tiers` 43 / 13 069 (−35 %) / 1,00 / 220 s ; `petit_json_ouvert` 88 / 47 959 (+139 %) / 0,93 / 460 s | `experiment_x12` |
| Protocole X13 (sécurité), 4 bras × 5 | **rien de significatif** : I3 1,00/1,00 en `demo`, 0,90/0,90 en `e2e` ; I7 220/220 et 270/250 s, p ≥ 0,14 — les habitués savent déjà ce que la sécurité sait | `experiment_x13` |
| Protocole X14 (familles), 2 bras × **10 graines** | I2 **0,52 [0,51–0,54] contre 0,41 [0,40–0,44]**, p = 0,017 (9 graines sur 10) ; I3 1,00, I7 220-225 s : les familles font douter, pas ralentir | `experiment_x14` |
| O2, posture « assistant prudent » | **62 cas sur 1 196 appels X12 (5,2 %)**, tous « cible générique : la sortie la plus proche », `fallback=false` | journaux X12 |
| Q5, récupération douteuse | **100 `rag.suspect`** sur 25 runs X12 (4 par run) ; le seuil 0,17 ne voit **pas** les annonces contradictoires (483 décisions en retrouvent une, 358 en reçoivent de contradictoires) | `experiment_x12` |
| B3, 3ᵉ contrôle (diversité) | intra-modèle **0,400**, inter-modèle **0,472**, rapport 0,85 sur 939 justifications X12 (440 391 paires) | `scripts/diversite.py` |
| E4, énergie par bras | **0,163 Wh** actifs (60 règles) à **1,673 Wh** (60 LLM) ; hybride 0,397 ; `tiers_regles` 0,217 contre `tous_grand` 0,370 ; repos 6,5 W | `scripts/energie.py` |
| C8, paire versionnée | `demo20` 200 s, 20/20 ; `demo60` 200 s, 60/60 ; I7 100 s des deux côtés, rejeu `ok: true` | `make replay-pair` |
| F3, état courant | `state.json` **70 581 octets** contre 1 777 302 de journal (77 % d'instantanés) ; `maree state` 0,40 s | `f3_state_01` |
| F5, requêtes reproductibles | **449 970 événements, 451 runs, 3,4 s** sur 1,2 Go de JSONL | `maree query runs` |
| Petit modèle, 4 formats | JSON ouvert : `search` 55/55 ; liste : **1re option** 100 % ; oui/non : instable ; **règle + drapeaux** : calme 6/6, fumée 6/6, annonce 2/6 | essais directs sur `qwen3-0-6b` |
| Petit modèle contre grand, sous charge | `lag_ticks_median` **4 pour les deux** (5 au maximum) : la file mange l'écart de vitesse | `experiment_x10` |
| C1, Redpanda réel | **1 002 messages** sur 4 topics pour un run de 1 023 événements (21 instantanés exclus) | `scripts/kafka_check.py` |
| A4, incidents réels | 8 incidents / 2 causes en async 60 agents, 3 en sync ; run allé au bout | `c4_async_02`, `c4_sync_01` |

**Le KV cache de 4 slots tient** : 1 980 Mo sur 4 096, 2,1 Go libres.
Le repli `parallel=2` n'est pas nécessaire.

**Non mesuré en v2** : le bras E4B, la reproductibilité exacte d'un run
LLM (voir §6), et l'énergie au compteur matériel (le chiffre par bras
vient de `power.draw`, échantillonné à 1 Hz).

---

## 5. Commandes

```bash
uv sync --all-extras          # venv + deps
uv run pytest                 # 167 tests, sans GPU
uv run maree run population=rules_only bus.backend=memory narrative.enabled=false
uv run maree serve            # WebSocket sur 8765 (rejeu d'un run)
uv run maree serve --prompts  # + le prompt LLM dans les décisions
uv run maree live --tick-ms 600  # run + diffusion + injections (D3)
godot --path godot/project    # client
uv run maree replay           # rejeu du dernier run
uv run maree replay --run-id demo_replay   # le run versionné (E3)
uv run maree trace --run-id demo_replay --indicator I1_consensus  # B4
uv run maree lag --run-id demo_replay          # C7 : monde -> perception -> mesure
uv run maree run run.mode=async bus.backend=memory   # C4 : chacun à son rythme
uv run maree experiment --name x1 --seeds 3
```

`make smoke` enchaîne le run sans LLM. `make test` lance pytest.

Depuis l'hôte, `experiment` exige deux choses, sinon il échoue ou ment :

- `bus.backend=memory` **ou** `MAREE_KAFKA_BOOTSTRAP=172.28.0.10:9092`. Le
  défaut `localhost:9092` ne résout pas hors compose (`Unable connect to
  "localhost:9092"`, une ligne par tentative, le run ne démarre jamais).
  La variable `MAREE_KAFKA_BOOTSTRAP` est lue par `configs/config.yaml`
  (`bus.bootstrap`) ; `bus.backend=redpanda` sans elle fait échouer les
  10 runs. Pour un protocole **sur broker réel**, voir `x3k.yaml` — il
  publie ~1 054 événements par run sur 4 topics et donne les mêmes
  indicateurs que `x3m.yaml` en mémoire (+24 % de temps mural seulement) ;
- `MAREE_LLM_URL=http://<ip-du-conteneur>:8080/v1` — sans lui, le client
  vise `llama-cpp:8080`, tous les appels échouent et les 10 runs sont des
  replis règles qui *ressemblent* à des résultats. L'IP change au reboot
  (voir §2) : la relire, ne pas la recopier.

```bash
MAREE_LLM_URL=http://$(docker inspect maree-llama-cpp \
  --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'):8080/v1 \
  uv run maree experiment --name x1 --seeds 5 bus.backend=memory

# pareil, mais les événements passent par Redpanda (C1) :
MAREE_KAFKA_BOOTSTRAP=172.28.0.10:9092 \
  uv run maree experiment --name x3k --seeds 5 bus.backend=redpanda
```

**Un témoin contemporain, sinon rien.** Comparer X3K (broker) au X3 du
2026-10-29 donnait I7 = 220 s contre 100 s : on aurait conclu « Kafka
ralentit la foule ». Faux — entre-temps les règles suivent la sortie
annoncée (`_announced_exit`). D'où `x3m.yaml`, même code, mêmes graines,
en mémoire : I1/I3/I5/I7 **identiques à la décimale**, +24 % de mural.
Deux runs séparés par une version de code ne comparent rien.

**Contrat d'affichage** : `docs/protocol-ui.md` décrit chaque trame
(`hello`, `world`, `decision`, `belief`, `message`, `heard`, `evacuated`,
`snapshot`, `indicators`, `narrative`, `event`, `end`) avec un exemple
réel. **Aucun événement du journal n'est filtré** : les types sans trame
dédiée passent en `event`, enveloppe comprise. C'est le document à donner
à la personne qui écrit le client : elle n'a pas besoin de lire le
moteur.

---

## 6. Ce qui reste ouvert

- **`make up`** : le KV cache de 4 slots tient (1 980 Mo / 4 096), le
  repli `parallel=2` est inutile. Mais `docker compose up` n'est pas
  utilisable tel quel ici : l'image `maree/llama-cpp:b11609` devrait être
  reconstruite (apt sans réseau) et la publication de ports est cassée.
  Le conteneur a été relancé à la main sur 8080 avec le preset du dépôt.
- **Index RAG** : `maree index` tourne (215 passages, 7 s). La qualité
  sémantique de bge-m3 est bonne sur trois requêtes témoins (fumée →
  annonce + souvenir ; sortie A fermée → souvenir de fermeture + plan),
  mais elle n'est pas mesurée par un jeu de questions annotées.
- **Reproductibilité LLM** : deux runs de même configuration donnent les
  mêmes nombres (46 appels, 211 décisions, 20 ticks, 60/60) mais **pas
  les mêmes décisions** : A01 reste au tick 1 dans l'un, cherche dans
  l'autre. Le batching concurrent change l'ordre et les flottants. Le
  journal reste rejouable (on rejoue les décisions), mais une
  ré-exécution n'est pas identique : les expériences doivent agréger
  plusieurs graines, pas comparer deux runs appariés.
- **Godot** : le client a été ouvert nativement. `godot` 4.4.1 est
  installé dans `~/.local/bin` ; le rendu `gl_compatibility` passe sur
  l'**iGPU Intel** (le pilote NVIDIA n'est pas chargé pour GL), ce qui
  évite de disputer la VRAM à llama.cpp. Lancement : `maree serve` puis
  `godot --path godot/project`. Deux défauts corrigés le 2026-10-28 :
  le serveur fermait la socket dans la même passe que la trame `end`
  (perdue : 48 trames sur 49) et le client remettait le statut à
  « connecté » juste après `end`, d'où « déconnecté » sur une diffusion
  pourtant terminée. Rappel : `Node2D` n'a **pas** de `size` (c'est
  `Control`) — utiliser `get_viewport_rect().size`.
- **X1–X14** : campagne complète rejouée le 2026-11-01 (260 runs,
  5 graines pour X1, X3, X3K, X3M, X4, X8–X13 et 10 pour X2, X5, X6, X7,
  X14 ; 14 181 appels LLM, 14 181 succès, 0 repli). Résultats :
  `docs/resultats/rapport-v2.md`
  (tables) et `conclusions-v2.md` (lecture par hypothèse). **I4 est
  censuré à `max_ticks`** dès qu'une partie de la foule ne sort pas
  (X1 ambigu, X2, X4) : lire I3 et I7 avec. Les campagnes antérieures
  sont conservées (`runs/experiment_x*_avant_correctif.json`,
  `runs/avant_correctif_rag/`) — elles mesuraient un modèle où un
  visiteur LLM pouvait nommer B, puis un corpus où le profil `visiteur`
  ne lisait aucune annonce. Elles ne sont pas publiées.
- **Le LLM n'aidait pas les visiteurs avec le protocole ouvert** : en X4
  `llm_60`, 9 à 19 visiteurs sur 24 restaient piégés (plus 1 à 7
  habitués), contre 0 à 8 en tout-règles (le « 60/60 » de la campagne
  précédente était l'artefact de
  la fuite de connaissance). Avec la politique explicite de la vague 4,
  ils sortent : X12 `deux_tiers` évacue 1,00 à 60 agents. Ce qui reste
  ouvert n'est donc plus « pourquoi ils restent » mais **« ce qu'ils
  perdent »** : le petit modèle n'écoute qu'à moitié les annonces (2/6).
- **La connaissance est statique** : la garde s'appuie sur
  `Profile.knows`, comme `_known_open` pour les règles. Un message qui
  dit « B est libre » n'ajoute pas B au savoir d'un visiteur. À trancher
  si l'on veut un modèle où l'on apprend la géographie par ouï-dire.
- **Le corpus d'annonces rend des variantes contradictoires** : douze
  annonces nommant des sorties différentes, toutes disponibles dès t10.
  Une décision qui interroge `annonces/` en reçoit trois qui se
  contredisent (483 décisions en retrouvent une en X12, 358 en reçoivent
  de contradictoires). Le percept porte la vraie annonce à
  part, donc le dégât est borné, mais un modèle peut préférer ses
  « souvenirs ». Le seuil `rag.suspect` (0,17) ne voit rien — le score
  est bon (0,27). À filtrer sur le texte réellement diffusé.
- **Le rapport hybride existe** : `docs/resultats/rapport-hybride.md`
  assemble partie technique, mini-article, bilan de sobriété et réponses
  Q1–Q6. Les autres documents sont des notes ; celui-là se lit seul.
- **Le suivi d'agent** vise la position du meneur au moment de la
  décision, pas en continu.
- **La fermeture d'issue** redirige vers un point d'arrêt, ce n'est pas
  une barrière physique.
- **Les visiteurs restent piégés** dans le scénario `e2e` : c'est voulu
  (ils ne connaissent que A, et A ferme à t14), mais le nombre dépend
  fortement du bras — 0 à 8 en tout-règles, 9 à 19 sur 24 en tout-LLM
  (plus 1 à 7 habitués). Le run consomme alors `max_ticks` et le filet
  périodique les fait redécider jusqu'au bout : c'est là que passe le
  coût LLM (477 appels pour `llm_60`, 89,5 s).
