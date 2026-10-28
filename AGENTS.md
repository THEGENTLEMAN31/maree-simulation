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
- Les obstacles sont passés en **trous** du polygone marchable. Sans eux,
  les agents traversent la scène.

### Docker

- La publication de ports est cassée dans cet environnement. Seul le
  relais sur **16080** fonctionne (`~/.local/share/maree-relay/`).
- `apt-get` n'a **pas** de réseau pendant les builds. PyPI fonctionne.
- Ne pas ajouter de service Godot dans `docker-compose.yml` : le rendu
  OpenGL en container exige X ou noVNC pour un gain nul. Godot tourne sur
  l'hôte.

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
| Run 60 agents à règles (v2) | 20 ticks, 924 événements, 4,6 s | `run_smoke_03` |

**Non mesuré en v2** : le run hybride 12 LLM + 48 règles de bout en bout.
Le chemin est câblé et testé unitairement, mais il faut un GPU pour le
confirmer.

---

## 5. Commandes

```bash
uv sync --all-extras          # venv + deps
uv run pytest                 # 86 tests, sans GPU
uv run maree run population=rules_only bus.backend=memory narrative.enabled=false
uv run maree serve            # WebSocket sur 8765
godot --path godot/project    # client
uv run maree replay           # rejeu du dernier run
uv run maree experiment --name x1 --seeds 3
```

`make smoke` enchaîne le run sans LLM. `make test` lance pytest.

---

## 6. Ce qui reste ouvert

- **Premier `make up`** : vérifier que le KV cache de 4 slots tient dans
  4 Go. Repli prévu : `parallel=2`.
- **Index RAG** : `maree index` n'a jamais tourné (pas de GPU ici).
  `FaissRetriever.build()` est écrit mais non exercé.
- **Godot** : le client n'a pas été ouvert dans l'éditeur. Il compile
  probablement, mais ce n'est pas vérifié.
- **X1–X7** : la commande `experiment` existe, aucun protocole complet
  n'a été exécuté (≥ 5 graines × 2 bras = long).
- **Le suivi d'agent** vise la position du meneur au moment de la
  décision, pas en continu.
- **La fermeture d'issue** redirige vers un point d'arrêt, ce n'est pas
  une barrière physique.
