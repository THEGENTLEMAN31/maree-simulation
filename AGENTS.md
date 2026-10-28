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
- `agent.decision` ≠ `agent.evacuated`. Le second est un fait physique
  (l'agent a franchi l'issue), le premier une cognition. Les confondre
  faisait compter 60 « décisions » fantômes par run.
- **Un appel LLM raté ne fait pas échouer le run** : le graphe replie
  sur les règles. Sans serveur, `maree run` produisait 43 « appels LLM »
  en 11 s et un résultat d'apparence normale. `RunResult.llm_ok` compte
  les succès, le journal marque `llm.fallback=true`, et la CLI crie
  quand `llm_ok == 0`. Un run à 0 succès n'est **pas** un run hybride.
- **Le dernier tick d'indicateurs est dégénéré** : tout le monde est
  sorti, donc I1/I2/I5/I6 valent 0. Utiliser `metrics.summarise()` (pic
  pour I5/I6, moyenne pour I1/I2) et non `indicators[-1]`.
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

### Docker

- La publication de ports est cassée dans cet environnement. Seul le
  relais sur **16080** fonctionne (`~/.local/share/maree-relay/`).
- `apt-get` n'a **pas** de réseau pendant les builds. PyPI fonctionne.
- Le conteneur `maree-llama-cpp` tourne ici sur **8080** avec le preset
  du dépôt (8192/4), lancé à la main. `docker compose up` reconstruirait
  l'image (apt sans réseau) et la publication de ports est cassée. Le
  8080 de l'hôte appartient à `llama-stack.service` : depuis l'hôte, on
  joint le conteneur par son IP (`172.19.0.3:8080`), pas par `localhost`.
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
| Protocole X1, 1 graine × 2 bras | clair **190 s** / ambigu **550 s** (I4) | `experiment_x1` |
| Preset 8192/4 (E2B) + bge-m3 | `n_slots = 4`, `n_ctx_slot = 2048`, **1 980 Mo / 4 096** | `nvidia-smi`, RTX 3050 |
| Débit LLM, concurrence 1 / 4 | 0,69 / **1,94** décision/s | 12 appels, ~700 tokens |
| Run hybride 12 LLM + 48 règles, démo | 21 ticks, **44 appels / 44 succès**, 21,9 s, **60/60** | `run_hybrid_08` |
| Récits du chroniqueur | 4, **0 repli**, chiffres conformes au digest | `run_hybrid_08` |
| Trames diffusées, démo à règles | **377** (212 décisions, 60 messages, 60 évacuations, 21 instantanés, 20 indicateurs) | `maree serve` |
| `maree index` sur le corpus réel | 215 passages en **7 s** | bge-m3, `data/rag` |

**Le KV cache de 4 slots tient** : 1 980 Mo sur 4 096, 2,1 Go libres.
Le repli `parallel=2` n'est pas nécessaire.

**Non mesuré en v2** : aucun protocole X complet (≥ 5 graines), le bras
E4B, et la reproductibilité exacte d'un run LLM (voir §6).

---

## 5. Commandes

```bash
uv sync --all-extras          # venv + deps
uv run pytest                 # 125 tests, sans GPU
uv run maree run population=rules_only bus.backend=memory narrative.enabled=false
uv run maree serve            # WebSocket sur 8765
uv run maree serve --prompts  # + le prompt LLM dans les décisions
godot --path godot/project    # client
uv run maree replay           # rejeu du dernier run
uv run maree experiment --name x1 --seeds 3
```

`make smoke` enchaîne le run sans LLM. `make test` lance pytest.

**Contrat d'affichage** : `docs/protocol-ui.md` décrit chaque trame
(`hello`, `world`, `decision`, `message`, `evacuated`, `snapshot`,
`indicators`, `narrative`, `end`) avec un exemple réel. C'est le document
à donner à la personne qui écrit le client : elle n'a pas besoin de lire
le moteur.

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
- **X1–X7** : `experiment` tourne (X1 vérifié sur 1 graine × 2 bras),
  mais aucun protocole complet (≥ 5 graines) n'a été exécuté.
- **Le suivi d'agent** vise la position du meneur au moment de la
  décision, pas en continu.
- **La fermeture d'issue** redirige vers un point d'arrêt, ce n'est pas
  une barrière physique.
- **6 visiteurs restent piégés** dans le scénario `e2e` : c'est voulu
  (ils ne connaissent que A), mais cela signifie que le run consomme
  `max_ticks` et que le filet périodique les fait redécider jusqu'au
  bout. À surveiller côté coût LLM.
