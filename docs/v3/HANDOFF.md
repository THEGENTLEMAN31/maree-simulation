# HANDOFF — reprendre MARÉE v3 sans son auteur

_Écrit le 2026-11-22. À lire avec `AGENTS.md` (les pièges) et
`docs/v3/rapport-v3.md` (les résultats). Ce fichier dit **où l'on en est**,
**comment rejouer chaque affirmation**, et **ce qui reste ouvert**._

---

## 1. En trente secondes

Simulation d'évacuation de foule : 60 agents, une salle calibrée, JuPedSim
pour le corps, trois façons de décider (règles / modèle / hybride), un
journal qui est la source de vérité. L'objet d'étude est **ce qu'un LLM
apporte à une décision de foule**, mesuré, pas raconté.

État : moteur réparé (C1–C7), campagne macro à 10 graines, cinquième bras
ajouté (classifieur de décision). Le résultat central n'est pas « LLM ou
règles » mais **quelle nature de modèle** : sur 10 graines, les décisions
visant une porte crue bloquée tombent de **0,41** (règles) à **0,20** (Gemma 4
E2B, générateur) et **0,03** (Kev-4B, classifieur) — p = 0,002, 10/10 graines.

---

## 2. Ce qui tourne, et comment

```bash
uv sync --all-extras
uv run pytest                 # 411 tests, aucun GPU
make lint type                # ruff + mypy

# les affirmations du rapport, une commande chacune (aucun GPU) :
make v3-twins                 # mission n°1 : la mémoire fait diverger les jumeaux
make v3-worlds                # cinq salles : le goulot tient-il ?
make v3-denial                # H5 : un démenti tardif, qui atteint-il ?

# campagnes (serveurs 8081 grand / 8082 petit requis) :
make v3-crowd                 # 4 bras × 2 scénarios × 5 graines (~1 h)
make v3-crowd-null            # le null de B3 (sans émission)
make v3-tables                # régénère docs/v3/resultats-c6.md
```

Les serveurs locaux (RTX 3050, 4 Go) :

```bash
/mnt/data/llama.cpp/build/bin/llama-server \
  --model /mnt/data/maree-models/gemma-4-E2B-it-Q4_K_M.gguf \
  --alias gemma4-e2b --port 8081 --ctx-size 4096 --parallel 1 \
  --n-gpu-layers 99 --flash-attn on --threads 4 --no-webui --jinja --reasoning off
```

(même chose avec `Qwen3-0.6B-Q4_K_M.gguf --alias qwen3-0-6b --port 8082 --ctx-size 2048`.)

---

## 3. Où sont les choses

| quoi | où |
|---|---|
| le journal, les runs, les JSON de campagne | `runs/v3/` (archives : `runs/v3/avant_correctif/`) |
| le moteur | `src/maree/v3/` — `sim/` (orchestrateur, scène, physique), `agents/` (perception, calendrier, politiques, parole), `verify/` (mesure) |
| les mondes de mesure | `world.generate.preset` (`crowd_hall`), `verify/worlds.py` (famille) |
| les scénarios | `verify/scenario_blocked.py` (micro), `verify/scenario_crowd.py` (foule, 5 variantes) |
| les tables du rapport | `docs/v3/resultats-c6.md`, régénérables par `scripts/rapport_crowd.py` |
| les décisions | `docs/v3/decisions.md` (ADR-014 → 018) |
| le plan de travail autonome | `docs/v3/plan-autonomie.md` (phases, portes, journal) |

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

- **Généralisation hors des petits modèles** : la conclusion négative vaut
  pour gemma-4-E2B / qwen3-0.6B. Un modèle plus gros (E4B est téléchargé,
  4,97 Go) demande une expérience bornée en RAM.
- **Bras `decision_head`** : implémenté (Kev-4B sur `/v1/systemone`, port
  8083, `MAREE_HEAD_URL`). Reste : un modèle de décision plus gros, et la
  même mesure avec un état d'entrée plus riche (les options sont aujourd'hui
  « rester » + une sortie par sortie connue).
- **Deux tiers en foule** et **courbe ε** : préparés, pas mesurés.
- **Énergie** : chiffres v2, non remesurés après refonte.
- **Godot et les assets** : chantier volontairement non ouvert (travail
  visuel à faire à deux, avec des assets téléchargés).

---

## 6. Trois règles à ne pas casser

1. **Le journal est la source de vérité.** Rien n'existe s'il n'est pas
   journalisé, y compris ce qui a été décidé de ne pas faire.
2. **Une affirmation = une commande rejouable.** Si un chiffre du rapport ne
   se régénère pas, c'est le rapport qui a tort.
3. **Le null doit être un run**, pas un raisonnement — et avec le même code.
