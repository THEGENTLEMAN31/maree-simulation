# HANDOFF — reprendre MARÉE v3 sans son auteur

_Écrit le 2026-11-22, complété le 2026-11-24. À lire avec `AGENTS.md` (les
pièges) et `docs/v3/rapport-v3.md` (les résultats). Ce fichier dit **où l'on en
est**, **comment rejouer chaque affirmation**, et **ce qui reste ouvert**._

---

## 1. En trente secondes

Simulation d'évacuation de foule : 60 agents, une salle calibrée, JuPedSim
pour le corps, cinq façons de décider (règles / générateur grand / petit /
hybride / classifieur System 1), un journal qui est la source de vérité.
L'objet d'étude est **ce qu'un modèle apporte à une décision de foule**,
mesuré, pas raconté.

État : moteur réparé (C1–C7), campagne à 10 graines, cinquième bras ajouté.
Le résultat central n'est pas « LLM ou règles » mais **quelle nature de
modèle** : sur 10 graines, les décisions visant une porte crue bloquée tombent
de **0,41** (règles) à **0,20** (Gemma 4 E2B, générateur) et **0,03** (Kev-4B,
classifieur) — p = 0,002, 10/10 graines.

---

## 2. Ce qui tourne, et comment

```bash
uv sync --all-extras
uv run pytest                 # 422 tests, aucun GPU
make lint type                # ruff + mypy

# les affirmations du rapport, une commande chacune (aucun GPU, ~1 min) :
make v3-twins                 # mission n°1 : la mémoire fait diverger les jumeaux
make v3-worlds                # cinq salles : le goulot tient-il ?
make v3-denial                # H5 : un démenti tardif, qui atteint-il ?
make v3-speech                # parole ou rumeur ? (none / guards / all)

# campagnes (serveurs requis, voir plus bas) :
make v3-crowd                 # 4 bras × 2 scénarios × 5 graines (~1 h)
make v3-crowd-null            # le null de B3 (sans émission, sans LLM)
make v3-tables                # régénère docs/v3/resultats-c6.md
uv run python scripts/v3_stats.py runs/v3/campaign_crowd_10seeds.json
uv run python scripts/v3_bands.py 1 2          # deux tiers + courbe ε
```

### Les serveurs locaux (RTX 3050, 4 Go) — **toujours avec `setsid`**

`nohup … &` seul se fait tuer par le nettoyage de groupe de processus du shell
au bout de ~30 s, **en silence** (« cleaning up before exit » dans son
journal). `setsid` est obligatoire.

```bash
S=/mnt/data/llama.cpp/build/bin/llama-server
M=/mnt/data/maree-models

# grand (générateur) : 8081 — 1,9 Go
setsid nohup $S --model $M/gemma-4-E2B-it-Q4_K_M.gguf --alias gemma4-e2b \
  --port 8081 --ctx-size 4096 --parallel 1 --n-gpu-layers 99 --flash-attn on \
  --threads 4 --no-webui --jinja --reasoning off >/tmp/llama_big.log 2>&1 </dev/null &

# petit : 8082 — 0,4 Go
setsid nohup $S --model $M/Qwen3-0.6B-Q4_K_M.gguf --alias qwen3-0-6b \
  --port 8082 --ctx-size 2048 --parallel 1 --n-gpu-layers 99 --flash-attn on \
  --threads 4 --no-webui --jinja --reasoning off >/tmp/llama_small.log 2>&1 </dev/null &

# classifieur de décision (bras decision_head) : 8083 — 3,03 Go
setsid nohup $S --model $M/Kev-4B-Q4_K_M.gguf --alias kev \
  --port 8083 --ctx-size 1024 --parallel 1 --n-gpu-layers 16 \
  --threads 4 --no-webui >/tmp/llama_kev.log 2>&1 </dev/null &

# générateur plus gros (sonde seulement) : 8084 — 4,97 Go, 20 couches GPU + RAM
setsid nohup $S --model $M/gemma-4-E4B-it-Q4_K_M.gguf --alias gemma4-e4b \
  --port 8084 --ctx-size 2048 --parallel 1 --n-gpu-layers 20 \
  --threads 6 --no-webui >/tmp/llama_e4b.log 2>&1 </dev/null &
```

La VRAM ne permet pas tout en même temps : 8081+8082 = 2,4 Go ; 8083 seul
= 3,6 Go ; 8084 seul = 3,4 Go. **Arrêter un serveur avant d'en démarrer un
autre**, par PID (`pgrep -af Kev-4B`, puis `kill <pid>`), jamais `pkill -f`
avec un motif large : il tue aussi le shell qui l'exécute. Le port 8080
appartient à `llama-stack.service` — ne pas y toucher.

Variables lues par le code : `MAREE_LLM_URL` (8081), `MAREE_LLM_SMALL_URL`
(8082), `MAREE_HEAD_URL` (8083), `MAREE_HEAD_MODEL` (`kev`).

---

## 3. Où sont les choses

| quoi | où |
|---|---|
| le journal, les runs, les JSON de campagne | `runs/v3/` (archives : `avant_correctif/`, `archive/`) |
| le moteur | `src/maree/v3/` — `sim/` (orchestrateur, scène, physique), `agents/` (perception, calendrier, politiques, parole, policy_head), `verify/` (mesure) |
| les mondes de mesure | `world.generate.preset` (`crowd_hall`), `verify/worlds.py` (famille) |
| les scénarios | `verify/scenario_blocked.py` (micro), `verify/scenario_crowd.py` (foule : plain, split, contradiction, closure, denial, two_tier) |
| les tables du rapport | `docs/v3/resultats-c6.md`, régénérables par `scripts/rapport_crowd.py` |
| les décisions | `docs/v3/decisions.md` (ADR-014 → 019) |
| le protocole et les critères | `docs/v3/preregistrements.md` |
| le journal des décisions prises seul | `docs/v3/plan-autonomie.md` |
| le brouillon d'article | `docs/v3/article-v3.md` (non publié) |

---

## 4. Les quatre chiffres à connaître

0. **En foule, 10 graines** : décisions vers une porte crue bloquée —
   `regles` 0,41, `hybride` 0,26, `llm_grand` 0,20, `decision_head` **0,03**
   (p = 0,002, 10/10). Fautes par run : 52 / 71 / 104 / **18**. Jetons :
   0 / 125 k / 337 k / 100 k.

1. **Mission n°1** : deux jumeaux, même archétype, mémoires opposées →
   accord **0,00** (chacun prend sa porte) ; mémoire coupée → accord **1,00**.
   En foule : **1,00** des agents ignorent la porte qu'ils croient bloquée,
   **0,00** sans mémoire.
2. **Une fermeture d'issue** (A ferme à t4) : I6 monte à **0,43** puis
   retombe à 0,04 ; la foule se rabat sur B ; 60/60 sortis ; I5 1,75.
3. **Un démenti tardif** : il atteint **toutes** les personnes encore dans la
   salle (changement immédiat), mais à t8 il n'en reste que 29 sur 60 — et I7
   passe de 26 à 38 s. H5 (« le démenti corrige la croyance, pas l'action »)
   est **falsifiée** : ce qui limite un démenti tardif, c'est l'audience.

---

## 5. Ce qui reste ouvert

- **Énergie** : chiffres v2, non remesurés après refonte (script
  `scripts/v3_energy.py`, jamais relancé).
- **Ablation des critères d'escalade** : on sait que l'hybride escalade
  ~200 fois par run, pas quel critère porte quoi.
- **Modèle de frontière** : la sonde E4B (`runs/v3/big_model_probe.json`)
  montre qu'on ne peut pas acheter le jugement avec des paramètres sur ce
  dispositif ; la question reste ouverte pour un 30 B+.
- **Cadence du générateur** : il décide 4× plus souvent que les règles et perd
  sur le total. Un bras « générateur contraint à la cadence des règles »
  trancherait si le problème est le calendrier ou la lecture.
- **Godot et les assets** : chantier volontairement non ouvert (à faire à
  deux, avec des assets téléchargés).
- **Géographie statique** : un message ne fait pas apprendre une sortie
  inconnue (garde C3, choix assumé).

---

## 6. Trois règles à ne pas casser

1. **Le journal est la source de vérité.** Rien n'existe s'il n'est pas
   journalisé, y compris ce qui a été décidé de ne pas faire.
2. **Une affirmation = une commande rejouable.** Si un chiffre du rapport ne
   se régénère pas, c'est le rapport qui a tort.
3. **Le null doit être un run**, pas un raisonnement — et avec le même code.
