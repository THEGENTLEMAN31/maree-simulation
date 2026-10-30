# Sobriété (E4) — ce que chaque run coûte, et ce qu'il apporte

_Le cahier des charges demande de mesurer le coût de chaque run (appels
LLM, tokens, temps de calcul, énergie quand elle est mesurable) **et de
le mettre en regard de l'apport démontré**. Ce document fait les deux,
séparément, puis les confronte._

Date : 2026-10-30 · Matériel : RTX 3050 (4 Go), llama.cpp, deux modèles
résidents.

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
| hybride, communication **on** (X8 `avec`) | 77 | 32 906 | 3 704 | 26,1 s | 58/60 |
| hybride, communication **off** (X8 `sans`) | 131 | 56 438 | 5 993 | 47,6 s | 51/60 |
| hybride, deux tiers (A5, `w2_twotier`) | 99 | 42 662 | 4 695 | 35,5 s | 55/60 |
| run versionné E3 (`demo_replay`) | 49 | — | — | 18,0 s | 60/60 |

Deux choses à lire dans ce tableau, et une seule est une bonne nouvelle.

**La communication réduit le coût de 41 %.** Sans diffusion, un agent qui
n'a rien entendu redécide : 131 appels au lieu de 77, 47,6 s au lieu de
26,1 s. Ce n'est pas la diffusion qui coûte cher, c'est son absence. Un
système qui parle est un système qui pense moins souvent.

**Le LLM ne fait pas mieux évacuer, et il coûte.** 12 agents LLM + 48
règles sortent 55 à 58 agents sur 60 ; les règles seules sortent 60/60 en
0,8 s. Ce résultat est cohérent avec X4 (`llm_60` : 40/60 contre 55/60 en
règles) et il n'est pas maquillé : l'apport du LLM dans ce scénario n'est
**pas** la performance d'évacuation.

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

Mesuré avec `scripts/mesure_energie.sh`, qui échantillonne
`power.draw` toutes les 500 ms, mesure la puissance au repos, puis
intègre la différence sur la durée du run. Résultat brut :
`docs/resultats/sobriete-energie.json`.

| grandeur | valeur |
|---|---:|
| durée du run | 31,6 s |
| puissance au repos (médiane) | 6,5 W |
| puissance pendant le run (moyenne) | 59,0 W |
| **surcoût** | **52,5 W** |
| **énergie du run** | **1 658 J = 0,46 Wh** |

Un run hybride coûte donc **un demi-watt-heure** de GPU. Un run à règles
dure 0,8 s : plus court que la période d'échantillonnage, donc **non
mesurable** avec cette méthode — ce qui est en soi la réponse.

Ce n'est pas une mesure de laboratoire : `power.draw` est la puissance
instantanée de la carte, pas un compteur mural. L'ordre de grandeur
suffit pour une soutenance ; il ne suffirait pas pour un bilan carbone.

**Ce qui n'est pas mesuré** : la consommation du CPU et de la RAM (le
moteur JuPedSim et le client Godot), et l'énergie grise du matériel.
Les inclure demanderait un compteur mural, que cette machine n'a pas.
