# Sobriété (E4) — ce que chaque run coûte, et ce qu'il apporte

_Le cahier des charges demande de mesurer le coût de chaque run (appels
LLM, tokens, temps de calcul, énergie quand elle est mesurable) **et de
le mettre en regard de l'apport démontré**. Ce document fait les deux,
séparément, puis les confronte._

Date : 2026-11-01 (campagne rejouée, 260 runs) · Matériel : RTX 3050
(4 Go), llama.cpp, deux modèles résidents + bge-m3.

---

## 1. Ce qui est mesuré, et où

| grandeur | où elle vit | depuis quand |
|---|---|---|
| `llm_calls` / `llm_ok` | `run.ended`, `RunResult`, résumé CLI | v2 |
| `tokens_in` / `tokens_out` | `run.ended`, `RunResult`, résumé CLI | vague 2 (E4) |
| `duration_s` (mural) | `run.ended`, `RunResult` | v2 |
| VRAM | `nvidia-smi`, hors du run | — |
| énergie | `nvidia-smi --query-gpu=power.draw`, échantillonné pendant un run | vague 2 (E4) |

`tokens_in/out` agrègent **les décisions et le chroniqueur** : un run qui
génère quatre récits les paie, et le journal le dit. C'est une correction
par rapport à la v1, où seul le nombre d'appels était compté.

---

## 2. Le coût, par configuration

Médianes sur 5 graines (X8) sauf mention contraire. Population hybride :
12 agents LLM + 48 agents à règles, 60 agents.

| configuration | appels | tokens entrée | tokens sortie | mural | évacués |
|---|---:|---:|---:|---:|---:|
| tout-règles (`run_demo_02`) | 0 | 0 | 0 | **0,8 s** | 60/60 |
| hybride, communication **on** (X8 `avec`) | 45 | 12 819 | 882 | **14,4 s** | 60/60 |
| hybride, communication **off** (X8 `sans`) | 64 | 23 579 | 1 712 | 34,4 s | 60/60 |
| hybride, scénario piège (X4 `hybride_12`) | 78 | — | — | 24,7 s | 53/60 |
| tout-LLM, scénario piège (X4 `llm_60`) | 477 | — | — | 89,5 s | 42/60 |
| run versionné E3 (`demo_replay`) | 49 | — | — | 18,0 s | 60/60 |

Deux choses à lire dans ce tableau, et une seule est une bonne nouvelle.

**La communication réduit le coût.** Sans diffusion, un agent qui n'a rien
entendu redécide : 64 appels au lieu de 45 (−30 %), 23 579 jetons
d'entrée au lieu de 12 819 (−46 %), 34,4 s au lieu de 14,4 s (−58 %). Ce
n'est pas la diffusion qui coûte cher, c'est son absence. Un système qui
parle est un système qui pense moins souvent.

**Le LLM ne fait pas mieux évacuer, et il coûte.** 12 agents LLM + 48
règles sortent 60/60 en 14,4 s ; les règles seules font aussi 60/60, en
0,8 s. Et en tout-LLM, le bras est **pire** que les règles : 42/60 contre
55/60 en X4, pour 477 appels et 89,5 s. Ce n'est pas maquillé : l'apport
du LLM dans ce scénario n'est **pas** la performance d'évacuation.

---

## 3. L'apport, dit sans emphase

Ce que le LLM apporte, et qui est mesurable dans le journal :

| apport | preuve |
|---|---|
| une décision **justifiée** par une phrase, pas seulement par une règle | `agent.decision.llm.raw_output` + `reason` |
| un recours explicite au **savoir** (RAG) | `retrieved` journalisé, P@1 0,417 (F2) |
| une **mémoire** datée qui pèse sur la décision | préhistoire J−3, ablation X9 (A1) |
| des **échanges** en langage naturel qui modifient la croyance | `message.sent` / `heard`, X8 (A2) |
| des **profils** qui décident différemment dans la même situation | A3, `test_graph.py` |
| un **récit** lisible du run | chroniqueur, 4 récits/run, 0 repli |

Ce que le LLM n'apporte pas, et qu'il faut dire : de meilleures
évacuations, ni un coût plus bas. Le projet est un banc d'essai pour
**comparer des stratégies d'annonce**, pas un optimiseur d'évacuation.

---

## 4. VRAM et modèles résidents

Deux tiers (A5) tiennent sur 4 Go, mesuré le 2026-10-30 :

| modèle | rôle | résident |
|---|---|---:|
| `gemma4-e2b` Q4_K_M | décisions `big`, chroniqueur | 2,9 Go (fichier) |
| `qwen3-0-6b` Q4_K_M | décisions `small` | 0,4 Go (fichier) |
| `bge-m3` Q4_K_M | embeddings RAG | 0,42 Go (fichier) |
| **total mesuré** | | **2 691 MiB / 4 096** |

Le preset `parallel = 4` et `ctx-size = 8192` (= 4 × 2048) restent
nécessaires : un `ctx-size` de 4096 donnerait 1 024 tokens par slot, et
les prompts réels (~700 tokens + 256 de sortie) seraient rejetés.

`gemma4-e4b` (4,7 Go) **ne tient pas** avec les deux autres : il est
déclaré dans le preset mais `--models-max 3` l'empêche d'évincer un
modèle résident. C'est un choix assumé, pas un oubli.

---

## 5. Énergie

Mesuré avec `scripts/energie.py`, qui relit un échantillonnage
`nvidia-smi --query-gpu=power.draw` à 1 Hz (`/tmp/gpu_power.csv`), découpe
la fenêtre de chaque run (`run.started` → `run.ended`) et intègre la
puissance **au-dessus du repos** (6,5 W mesuré à l'arrêt, hors run). Le
détail par run est dans `docs/resultats/sobriete-energie.json`.

La première version ne mesurait **qu'un** run (0,46 Wh) ; celle-ci mesure
chaque bras de la campagne, parce que c'est la question que pose E5 :
le tiers « petit modèle » coûte-t-il moins de joules que le grand ?

| protocole | bras | n | Wh actifs (médiane [IQR]) | durée médiane |
|---|---|---:|---|---:|
| X4 | 60 règles | 5 | **0,163** [0,162–0,169] | 11,1 s |
| X4 | hybride 12 LLM | 5 | **0,397** [0,379–0,409] | 24,7 s |
| X4 | 60 LLM | 5 | **1,673** [1,431–1,814] | 89,5 s |
| X12 | `tiers_regles` | 5 | **0,217** [0,200–0,293] | 12,9 s |
| X12 | `deux_tiers` | 5 | 0,233 [0,217–0,236] | 13,9 s |
| X12 | `tous_grand` | 5 | **0,370** [0,355–0,424] | 20,5 s |
| X12 | `petit_json_ouvert` | 5 | 0,642 [0,583–0,702] | 39,8 s |
| X8 | communication on | 5 | 0,248 [0,236–0,248] | 14,4 s |
| X8 | communication off | 5 | 0,613 [0,461–0,618] | 34,4 s |
| X3M | synchrone | 5 | 0,291 [0,286–0,349] | 18,2 s |
| X3M | asynchrone | 5 | 0,247 [0,245–0,276] | 15,7 s |

L'ordre est net : **0,163 Wh** pour un run à 60 règles, **1,673 Wh** pour
60 LLM, facteur 10. Le tiers « petit modèle » coûte **0,217 Wh** contre
**0,370 Wh** pour le tout-grand, soit **−41 %** à qualité d'évacuation
égale (I3 1,00) : c'est le résultat utile d'E5, et il porte sur la
répartition des décisions, pas sur la taille du modèle.

Ce n'est pas une mesure de laboratoire : `power.draw` est la puissance
instantanée de la carte, échantillonnée à 1 Hz et intégrée par trapèzes —
pas un compteur mural. L'écart-type entre runs (IQR ci-dessus) dit la
précision. L'ordre de grandeur suffit pour une soutenance ; il ne
suffirait pas pour un bilan carbone.

**Ce qui n'est pas mesuré** : la consommation du CPU et de la RAM (le
moteur JuPedSim et le client Godot), et l'énergie grise du matériel.
Les inclure demanderait un compteur mural, que cette machine n'a pas.
