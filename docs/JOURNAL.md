# Journal de bord — MARÉE

> **But** : ne rien perdre. Chaque décision, test réel, découverte, correctif et
> choix de conception est consigné ici, daté. Ce journal est ma mémoire
> permanente ; il est versionné avec le projet et mis à jour à chaque étape.
>
> Convention : une section par grande étape. Chaque entrée commence par
> `[DATE — titre]`. On ne supprime jamais une entrée : on la corrige, on
> l'annoté (« corrigé le … ») pour garder l'historique.

---

## 2026-10-13 — Cadrage & choix du sujet

- **Sujet choisi** : MARÉE (Monde 02 — Foule et évacuation, Fête des
  Lanternes de Port-Aubel). Décision prise après analyse des 7 mondes et du
  cadrage `MARÉE — Cadrage du projet.md`.
- **Question de recherche** : une foule qui ne sait rien construit-elle une
  croyance partagée sur la sortie sûre, et cette croyance la sauve-t-elle ou
  la piège-t-elle ?
- **Contraintes matérielles réelles (vérifiées le 13 oct.)** :
  - GPU : NVIDIA RTX 3050 Laptop, 4 Go VRAM (3,7 libres), driver 610
  - RAM : 38 Go (25 disponibles)
  - CPU : 8 cœurs ; disque : 26 Go libres à 87 %
  - Ollama actif avec **2 modèles déjà téléchargés** : `gemma4:latest`
    (6,1 Go) et `qwen3:30b-a3b` (18 Go, MoE 3B actifs) — config **custom de
    l'utilisateur**, intouchable.
- **Architecture validée** : llama.cpp router dans Docker (Gemma 4 E2B +
  E4B), Redpanda (Kafka), python-sim asyncio, Godot consommateur pur.
  L'utilisateur a refusé l'offloading MoE d'Ollama (n'utilise pas Ollama pour
  la simu) et le re-téléchargement avait été validé au départ.

## 2026-10-13 — Socle livré (commit initial + complet)

- Code Python complet : orchestrateur, agents (LLM + règles), RAG, indicateurs
  I1–I5, oracle temporel, rejeu E3, CLI, expériences X1–X7.
- Infra Docker : compose (redpanda, llama-cpp, python-sim, godot), presets,
  script `download_models.sh`.
- Godot : scripts GDScript (client WS, rendu, inspection D2, courbes B2).
- Docs : `decisions.md`, `architecture.md`, `hypotheses.md` (préenregistrées),
  `correspondance-exigences.md` (32 exigences), README, AGENTS.md.
- Graphify : graphe de code versionné (339 nœuds, 730 arêtes, 11 communautés).
- **Tests** : 11/11 verts (unitaires, dry-run) — mais AUCUN test réel de bout
  en bout avec de vrais modèles à ce stade.

## 2026-10-14 — Remise en cause : pas de validation réelle

- **Critique légitime de l'utilisateur** : le socle compile et les tests
  unitaires passent, mais je n'ai ni téléchargé les modèles, ni testé les
  modes sync/async avec de vrais LLM, ni analysé les résultats. → Je repars
  de l'état réel de la machine.
- **CLARTÉ UTILISATEUR confirmée** : on reste sur **llama.cpp dans Docker +
  GGUF Gemma 4 E2B/E4B en volume** — la seule cible production est
  `docker compose up`. Le `config/test-ollama.yaml` est un **banc d'essai de
  dev transitoire** (valider l'intégration pendant le téléchargement), jamais
  la config de prod.
- `docs/JOURNAL.md` créé pour ne rien perdre (décision utilisateur).

### Mesures d'état réelles (14 oct.)

| Ressource | Valeur |
|-----------|--------|
| GPU libre | 3 736 MiB / 4 096 |
| RAM dispo | 25 Go |
| Disque libre | 26 Go (87 % plein) |
| ollama ps | 0 modèle chargé |
| /api/version | 0.33.2 |

### Découvertes sur le matériel réel

1. **`ollama run gemma4:latest "Réponds par OK"` fonctionne** (0,6 s).
2. **`/api/generate` (webhook direct) renvoie vide en HEAD** — l'endpoint
   OpenAI-compatible `/v1/chat/completions` fonctionne, c'est celui qu'on
   utilise.
3. **BUG CRITIQUE DÉCOUVERT** : Gemma 4 (mode thinking) place la réponse
   dans `message.reasoning` et `content` peut être **vide**. Sur un prompt
   agent réel, tout le JSON était dans `reasoning` (content='').
   → **Correctif** : `_extract_useful()` dans `llm_gateway.py` extrait le
   dernier objet JSON équilibré du reasoning. Testé : OK.
4. Le flag `think: false` **n'est pas honoré** par le Modelfile custom
   de l'utilisateur (TEMPLATE `{{ .Prompt }}`). Pour la config production
   llama.cpp, le chat template Gemma 4 standard contrôle le thinking — à
   valider une fois les GGUF téléchargés.
5. **Décision architecture** : la passerelle doit être **robuste aux deux
   cas** (content présent OU reasoning complet) — indépendant du backend.
   C'est le correctif actuel.
6. **PERF RÉELLE mesurée** : 1 décision LLM gemma4 (contexte 49152 user)
   ≈ **4,5 s**, usage = 208 tokens prompt / 150 completion. Les runs de
   validation doivent être dimensionnés : ~5 agents × 10 ticks ≈ plusieurs
   minutes → timeout à 300 s dépassé. À gérer dans la config de validation
   (max_ticks faible + population réduite).
7. **Integration Python testée** (Ollama, banc de dev) : passage du JSON par
   le agent — premiers bugs corrigés : `field()` dans classe non-dataclass
   (`drift_events`), base_url None dans LLMGateway.

### Docker / GPU vérifiés (14 oct.)

- `nvidia-container-cli` présent → conteneurs Docker peuvent accéder au GPU.
- Image `nvidia/cuda:12.4.0-runtime-ubuntu22.04` pullée et testée :
  **RTX 3050 visible dans le conteneur** (nvidia-smi OK).
- Le build llama.cpp CUDA peut donc tourner dans Docker sur ce poste.

### Modèles — état du téléchargement (14 oct.)

| Modèle | État | Taille |
|--------|------|--------|
| gemma-4-E4B-it-Q4_K_M.gguf | ✅ **COMPLET** | 4 977 171 584 o |
| gemma-4-E2B-it-Q4_K_M.gguf | ✅ **COMPLET** | 3 106 738 272 o |

> **Leçon apprise** : les tailles annoncées par l'API HF (2,96/4,75 Go) sont
> inférieures aux octets réellement téléchargés (3,10/4,97 Go). La première
> exécution a « refusé » un fichier pourtant à 100 % car ma taille attendue
> était fausse. → Tailles figées dans le script depuis les octets réels.
> Les DEUX modèles sont maintenant complets et vérifiés (7,6 Go).

### URLs des modèles vérifiées (HuggingFace, 14 oct.)

| Modèle | Source officielle | Quant | Taille |
|--------|-------------------|-------|--------|
| Gemma 4 E2B it | `unsloth/gemma-4-E2B-it-GGUF` | Q4_K_M | 2,96 Go |
| Gemma 4 E4B it | `unsloth/gemma-4-E4B-it-GGUF` | Q4_K_M | 4,75 Go |

- Mon premier guess `bartowski/...` → **401 (inexistant)**. Corrigé dans
  `scripts/download_models.sh` vers les vraies URLs unsloth.
- **Premier téléchargement coupé à 27 %** (curl erreur 92 = HTTP/2 reset
  serveur HF) → script réécrit avec **reprise `-C -`**, HTTP/1.1, 8 tentatives.
  Fichier partiel 811 Mo conservé pour reprise. **Relancé en arrière-plan.**
- `docs/JOURNAL.md` créé pour ne rien perdre (décision utilisateur).

## 2026-10-14 — Plan de validation réelle (en cours)

Étapes à exécuter, dans l'ordre :

1. [x] Mettre à jour `download_models.sh` (bonnes URLs) + lancer.
2. [x] Corriger `llm_gateway.py` (extraction reasoning Gemma 4).
3. [x] **Téléchargement VÉRIFIÉ** : E2B + E4B complets (7,6 Go).
4. [ ] **Compiler/obtenir llama.cpp** CUDA (Docker ou local) et lancer le
     router avec les 2 GGUF ; vérifier la VRAM.
5. [ ] **Tester le mode thinking** des GGUF llama.cpp (content vs reasoning).
6. [ ] **Run réel synchrone** : petite population LLM + règles, GPU réel,
     analyser : indicateurs I1–I5, cohérence temporelle I5=0, coût, dérives.
7. [ ] **Run réel asynchrone** : même scénario, mode async, comparer
     I1, I3, coût, répartition sorties (hypothèse H3).
8. [ ] **Analyser les résultats** : si un indicateur est bizarre (ex. I1
     sature, I2 ne bouge pas, aucune évacuation), corriger le modèle
     d'agents / le monde / les prompts.
9. [ ] Exécuter les expériences X1–X7 (au moins un run par config) et
     vérifier que les hypothèses H1–H7 sont testables.
10. [ ] Rejeu E3 réel : rejouer un run depuis son JSONL, hash identique.

### INTÉGRATION SUITE — run réel (14 oct.)

✅ **Run réel de bout en bout RÉUSSI** (banc Ollama, 2 agents LLM + 4 règles,
6 ticks, mode sync) :
`12 appels LLM, 4311→6009 tokens, 153.8s cumulées, 0 violations temporelles`.
La chaîne perception → décision LLM → événements → indicateurs → journal
fonctionne avec un vrai modèle. À reproduire avec llama.cpp (prod) ensuite.

**Points d'attention observés (Ollama banc de dev)** :
- Gemma 4 force le thinking (content vide, réponse dans reasoning) →
  correctif `_extract_useful` robuste.
- Prompts trop longs + contexte 49152 → thinking long → timeout. Solution :
  prompts courts + max_tokens 300-400.
- Visiteurs LLM restaient "stay" sans croyance : prompt à affiner pour
  les pousser à former une croyance (exiger exit_choice).
- I1/I2 peu discriminants sur mini-run (pop. réduite, pas de rumeur injectée).

### Config de validation créée

- `python-sim/config/test-ollama.yaml` : population réduite (2 sécurité
  + 3 visiteurs LLM + 8 foule règles), `mode` variable, base_url Ollama
  local :11434. Permet de valider l'intégration réelle sans attendre les
  GGUF llama.cpp.

### Bugs restants à surveiller (liste vivante)

- [ ] `_extract_useful` : vérifier sur Ollama réellement via un run python
      complet (pas seulement unit test du parser).
- [ ] Gestion du `reasoning` : s'assurer que `explanation` dans l'inspection
      (D2) montre le raisonnement Gemma 4 et non du texte brut.
- [ ] Le compose Docker `llama-cpp` : vérifier le build CUDA sur cette
      machine (driver 610, archi sm86 pour RTX 3050 laptop).

---

## 2026-10-14 — Build llama.cpp Docker

- Lancement `docker compose build llama-cpp` ~01:04 — **en cours**
  (clone git + cmake CUDA + build, ~20 min).
- Dockerfile corrigé : base `devel` (pour nvcc), `CUDA_ARCHS=86` (sm86
  pour RTX 3050), preset `maree.ini` avec 2 modèles, commande `llama-server`
  (depuis PATH).
- Image de base : `nvidia/cuda:12.4.0-devel-ubuntu22.04` (build stage) +
  `nvidia/cuda:12.4.0-runtime-ubuntu22.04` (runtime) — testée, RTX 3050
  visible dans le conteneur.
- **En cours** : build en arrière-plan (PID 321917), clone git + cmake CUDA.
  Attente fin de build pour test du router llama.cpp avec les 2 GGUF.

---

```bash
# état GPU / modèles
nvidia-smi
ollama list && ollama ps

# API Ollama (endpoint OpenAI-compatible)
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4:latest","messages":[{"role":"user","content":"OK"}],"stream":false}'

# HF
curl -s "https://huggingface.co/api/models?search=gemma-4-GGUF&limit=30"

# tests
cd python-sim && /tmp/maree-venv/bin/python -m pytest tests/ -q
```
---

## 2026-10-20 — Réparation Godot + chaîne réelle validée de bout en bout

### Godot : la scène était invalide (cause racine du plantage)

- Cause : `.tscn` malformé (`instance=ExtResource` sur un `Script`,
  `type="SceneTree"`). Ni Godot ni Docker ni la version n'étaient en faute.
- Scène réécrite en syntaxe texte Godot 4 valide :
  `Main(Node)` → `World(Node2D, ws_client.gd)` →
  `AgentsLayer(CanvasLayer)/AgentContainer(Control, agent_view.gd)`,
  + `IndicatorChart`, `InspectPanel`, `ControlPanel`.
- Scripts réécrits : `ws_client.gd` (routage `state`/`indicators`/`inspection`,
  URL par env, reconnexion, `send_command`/`request_inspect`),
  `agent_view.gd` (carte 0..100 → x5, couleur par croyance, clic → inspect),
  `indicators.gd` (I1/I2/I4), `inspector_panel.gd` (D2),
  `control_panel.gd` (D3 : annonce / fausse info / fermeture sortie).
- `project.godot` en `gl_compatibility` (+ mobile) pour tenir sous llvmpipe.

### Deux vrais bugs Python trouvés par les tests

1. `orchestrator._inspect` appelait `explanation(None)` → `AttributeError`
   pour un agent à règles (et `KeyError` pour un agent inconnu). Corrigé :
   perception reconstruite à l'instant courant, réponse `error=unknown_agent`
   pour un identifiant inconnu. **Test de non-régression ajouté** (D2).
2. `orchestrator._inspect` n'`await`ait pas `ws.broadcast` → **l'inspection
   n'était jamais envoyée**. Corrigé (les deux branches).

### llama.cpp : build source abandonné au profit des binaires officiels

- Le build source CUDA (`Dockerfile.cuda`, clone `master` + cmake) dépassait
  1 h et reconstruisait des binaires déjà validés. Les binaires officiels
  **b11609** (Ubuntu 24.04, CUDA 12.8) étaient déjà présents dans
  `models/llama-b11609/`.
- Nouveau `llama.cpp/Dockerfile.prebuilt` : base `ubuntu:24.04` (GLIBC 2.38
  requis par les binaires) + runtime CUDA 12.4 copié depuis l'image NVIDIA
  locale. Binaires montés en lecture seule sur `/opt/llama`.
- `presets/maree.ini` réaligné sur b11609 : `cache-type-k/v` (et non
  `kv-cache-type`), `flash-attn = on` (et non `true`), clés `mlock`/`no-mmap`
  retirées (non supportées).

### Bug de contexte (mode router) — le plus sournois

- `llama-server` **répartit `ctx-size` entre les `--parallel` slots**. Avec
  15 slots et `ctx-size 8192`, la fenêtre utile tombait à ~546 tokens : le
  serveur rejetait les prompts réels
  (`request (649 tokens) exceeds the available context size (512)`) et les
  agents LLM repliaient **silencieusement** sur la règle (`stay`).
- Corrigé : slots réduits (E2B `parallel=4`, E4B `parallel=1`) et `ctx-size`
  dimensionné en conséquence (8192 / 4096). Vérifié : le compteur de jetons
  passe de `0→0` (repli) à `5779→1707` (appels réels).

### VRAM : E2B tient, E4B non

- E2B (2,9 Go de poids) tient sur la RTX 3050 4 Go. E4B (4,7 Go) **ne tient
  pas** : OOM vérifié avec `n-gpu-layers = 99`. Le preset le passe en
  **offload partiel CPU** (`n-gpu-layers = 20`) et l'on garde
  `--models-max 1` (llama.cpp évince/recharge à la demande).
- Les deux modèles ne peuvent donc pas être résidents simultanément — c'est
  une limite matérielle documentée, pas un bug.

### Godot VNC / éditeur : bibliothèques X manquantes

- `libXcursor.so.1` absent → repli Wayland → « all display drivers failed »
  → SIGSEGV. Corrigé : `libxcursor1 libxinerama1 libxrandr2 libxi6 libxext6
  libxrender1 libasound2 libfontconfig1 libdbus-1-3` ajoutés à
  `Dockerfile.vnc`. Godot tourne désormais en OpenGL (llvmpipe) sous Xvfb.
- `godot-vnc` (jeu, noVNC :6080) et `godot-editor`
  (profil `editor`, noVNC :6081, projet monté depuis l'hôte) démarrent.

### Batterie de tests exécutée

| Suite | Résultat |
|---|---|
| pytest Python | **12 passed** |
| Godot composants (`run_tests.gd`) | **26 OK / 0 échec** |
| Godot chaîne WS vs mock (`run_ws_tests.gd`) | **8 OK / 0 échec** |
| Orchestrator → WSRelay réels (`test_orch_ws.py`) | **10 OK / 0 échec** |
| E2E complet sync (E2B réel) | **6 OK / 0 échec**, rejeu E3 : 49 événements |
| E2E complet async (E2B réel) | **6 OK / 0 échec**, rejeu E3 : 47 événements |
| E2E complet E4B (offload partiel) | **6 OK / 0 échec**, rejeu E3 : 16 événements |

- Le E2E vérifie : connexion WS, `state` → `agent_view` (D1),
  `indicators` → courbes (B2), `inspect` → `inspection` → panneau (D2),
  et les **trois** commandes D3 (annonce, fausse info, fermeture sortie).
- Rejeu E3 : journal rechargé, ordre canonique vérifié, hash d'indicateurs
  calculé (`make e2e` → `scripts/run_e2e.sh`).

### Commandes ajoutées

```bash
make test-godot     # composants Godot hors ligne
make editor         # éditeur Godot dans le navigateur :6081
make e2e            # chaîne réelle sync (Redpanda + LLM + Godot + rejeu)
make e2e-async      # idem en mode asynchrone
make e2e-e4b        # idem avec le grand modèle (offload partiel)
```

---

## 2026-10-21 — RAG sémantique réel, protocole X1–X7, rapport F5, e2e vert

> Session longue et autonome. Tout ce qui suit est **mesuré**, pas estimé.
> Les résultats négatifs sont conservés. Les bugs trouvés en route sont
> listés avec leur correctif, pour qu'on ne les réintroduise pas.

### 1. RAG : e5-small écarté après mesure, bge-m3 adopté

- **e5-small (q8) rejeté** : embeddings dégénérés — `cos("le chat dort",
  "voiture rouge") = 0,929`, `cos(textes sans rapport) = 0,956`. Le centrage
  sur la moyenne ne sauve rien : P@1 = 0,167. Fichier supprimé.
- **bge-m3 Q4_K_M adopté** (417 Mo, `gpustack/bge-m3-GGUF`), `pooling = cls`,
  ctx 1024, dim 1024. Mesure F2 sur **214 passages / 30 questions annotées** :
  **P@1 = 0,733 · P@3 = 0,867 · MRR = 0,794 · degraded = false**.
- **Pourquoi Q4 et pas Q8** : Q8 (605 Mo) ne cohabite pas avec E2B dans 4 Go.
  Q4 oui : E2B + bge-m3 = **3 692 Mio / 4 096**, 76 Mio libres, validé par un
  stress test (chat 200 tokens + 60 embeddings + chat).
- **Chemin unique** : tout embedding passe par `LLMGateway.embed()` (décision
  7). Un échec lève ; jamais de repli silencieux. Le repli lexical existe mais
  est signalé par `RagClient.degraded` — il n'a **pas** servi aux mesures.
- **Index** : FAISS `IndexFlatIP` + numpy (pas de torch), correction
  d'anisotropie par centrage sur la moyenne du corpus.

### 2. Corpus RAG

- `scripts/generate_corpus.py` → **214 passages** : annonces 43, consignes 40,
  plan_signalétique 44, savoir_profils 44, souvenirs_editions 43 ; ~103 mots
  par passage ; `available_tick` + `allowed_profiles` (C6).
- **Incident consigné** : un nettoyage trop large a supprimé 5 passages
  d'origine. Restaurés par `git checkout -- world_corpus/`. Le générateur ne
  réécrit jamais un fichier existant, donc pas de doublon après restauration.
- `test_corpus_f1_complet` verrouille : ≥ 200 passages, 5 collections,
  en-têtes complets.

### 3. Protocole X1–X7 (70 runs réels)

- `config/experiments.yaml` : 30 agents (5 LLM E2B + 25 règles), 60 ticks,
  `decision_period_sync = 5` (12 tours de décision).
- **14 configurations × 5 runs = 70 runs**, 17:02 → 19:29 (~2 min/run).
  `validate_experiments()` refuse toute paire identique.
- Résultats (médiane ± IQR) :

| Configuration | I1 (part maj.) | I2 | I3 évacués | I4 | cit. RAG | I5 |
|---|---|---|---|---|---|---|
| X1_clear_early | 0,467 ±0,217 | 0,600 ±0,208 | 0,933 ±0,033 | 0,795 ±0,349 | 1,000 | 0 |
| X1_ambig_late | 0,400 ±0,217 | 0,600 ±0,217 | 0,967 ±0,050 | 0,602 ±0,250 | 1,000 | 0 |
| X2_leaders | 0,476 ±0,125 | 0,600 ±0,148 | 0,533 ±0,150 | 0,316 ±0,148 | 1,000 | 0 |
| X2_noleaders | 0,476 ±0,125 | 0,600 ±0,178 | 0,567 ±0,150 | 0,620 ±0,304 | 1,000 | 0 |
| X3_sync | 0,383 ±0,108 | 0,617 ±0,133 | 0,933 ±0,033 | 0,598 ±0,183 | 1,000 | 0 |
| X3_async | 0,550 ±0,200 | 0,679 ±0,249 | 0,733 ±0,183 | 0,583 ±0,393 | 1,000 | 0 |
| X4_llm | 0,367 ±0,133 | 0,633 ±0,158 | 0,933 ±0,033 | 0,608 ±0,197 | 1,000 | 0 |
| X4_rules | 0,467 ±0,000 | 0,533 ±0,000 | 1,000 ±0,000 | 1,000 ±0,000 | 0,000 | 0 |
| X5_with_mem | 0,367 ±0,183 | 0,633 ±0,208 | 0,967 ±0,067 | 0,547 ±0,170 | 1,000 | 0 |
| X5_without_mem | 0,400 ±0,150 | 0,600 ±0,167 | 0,933 ±0,017 | 0,719 ±0,090 | 1,000 | 0 |
| X6_profiles_origin | 0,433 ±0,150 | 0,567 ±0,175 | 0,933 ±0,067 | 0,561 ±0,254 | 1,000 | 0 |
| X6_profiles_swapped | 0,400 ±0,150 | 0,567 ±0,175 | 0,967 ±0,050 | 0,498 ±0,196 | 1,000 | 0 |
| X7_rag_on | 0,367 ±0,108 | 0,600 ±0,167 | 0,933 ±0,050 | 0,633 ±0,239 | 1,000 | 0 |
| X7_rag_off | 0,400 ±0,108 | 0,600 ±0,167 | 0,900 ±0,000 | 0,598 ±0,187 | 0,000 | 0 |

- **Tests exacts de Mann-Whitney** (permutation, n = 5 vs 5, 252 partitions) :

| Exp. | Hypothèse | Métrique | p exacte | Lecture |
|---|---|---|---|---|
| X1 | H1 clarté/précoce | I2 | 0,984 | aucun effet |
| X2 | H2 meneurs | I4 | 0,056 | tendance, **non concluant** (direction opposée) |
| X3 | H3 sync/async | I3 | **0,0079** | **significatif** : 93,3 % vs 73,3 % évacués |
| X4 | H4 LLM ≠ règles | I2 | 0,127 | non concluant |
| X5 | H5 mémoire préalable | I2 | 0,746 | non concluant sur I2 (voir descriptif) |
| X6 | H6 profils échangés | I2 | 1,000 | aucun effet |
| X7 | H7 RAG | I2 | 0,889 | aucun effet |

- **X5 (descriptif, métrique = sortie choisie)** : avec mémoire,
  `securite_01` et `visiteur_01` se répartissent A×3 / C×1 (+1 non évacué) ;
  sans mémoire, quasi-unanimité A (A×5 et A×4/B×1). La mémoire préalable
  **diversifie** la décision (cohérent avec A1), non testable sur 5 runs
  catégoriels.
- **X6 (négatif conservé)** : distributions **identiques** entre profils
  d'origine et échangés. Le journal prouve pourtant que le swap a bien eu
  lieu (`profile: securite` sur `visiteur_01` et inversement). Sur ce corpus,
  le texte du profil ne suffit pas à déplacer la décision finale.
- **H3 est la seule hypothèse soutenue** ; H2/H4 non concluantes ;
  H1/H5/H6/H7 négatives. Aucune n'a été réécrite après coup.
- **I5 = 0 sur les 70 runs** ; 100 % des décisions LLM citent ≥ 1 passage
  quand le RAG est actif (0 % quand il est coupé) — le levier est réel.

### 4. Bugs trouvés et corrigés (ne pas réintroduire)

1. **X4 « règles »** utilisait `LLMAgent.fallback_intention()` → renvoyait
   toujours `stay` → I3 = 0, résultat artefactuel. Remplacé par un
   `RulesAgent` miroir (même id, même profil, graine `crc32(id)`), X4 relancé
   (10 runs) et fusionné. `X4_rules` évacue désormais 100 %.
2. **Traçabilité RAG absente du journal** (décision 12 non tenue) : ajout de
   `rag_doc_ids`, `profile`, `kind` dans `agent.decision`.
3. **Violations I5 seulement en mémoire** : journalisées (`oracle.violation`),
   donc vérifiables en SQL.
4. **Requêtes SQL du rapport** utilisaient `event_type` alors que le journal
   écrit `type` → corrigé et vérifié sur les 70 runs.
5. **`_samples` lisait `I2_median` au lieu de `I2`** → listes vides, tests
   `None` silencieux (« test impossible »). Mapping explicite ajouté.
6. **I1 composite illisible** (part majoritaire × homogénéité → 0,05) :
   recalculé en **part majoritaire** depuis les snapshots (conforme au
   cadrage) via une requête SQL versionnée. Valeurs 0,37–0,55.
7. **Client WS tardif** : un run court pouvait finir avant la connexion Godot
   → cache du dernier `state`/`indicators` et rejeu à la connexion.
8. **Course de démarrage e2e** : `wait_for_client` (activé uniquement en e2e)
   + `max_ticks: 20` ; le client Godot voit tout le run.
9. **Pydantic** : `experiment_flags: dict[str, bool]` alors que
   `swap_profiles` est une liste → `dict[str, Any]`, warning supprimé.
10. **Docker** : `duckdb` absent de la liste de dépendances dupliquée du
    `Dockerfile` (le `pyproject.toml` l'avait) → ajouté, image reconstruite,
    `duckdb 2.0.0` + `faiss` vérifiés dans le conteneur.

### 5. Validation finale (tout vert)

| Vérification | Résultat |
|---|---|
| pytest hôte | **20 OK / 0 échec** |
| pytest conteneur | **20 OK / 0 échec** (duckdb 2.0.0 + faiss importés) |
| Godot composants | **26 OK / 0 échec** |
| Godot WebSocket | **8 OK / 0 échec** |
| E2E réel sync (E2B + RAG GPU) | **6 OK / 0 échec**, 7 appels LLM, 0 violation |
| Rejeu E3 | 44 événements, hash d'indicateurs recalculé |
| F2 (214 passages) | P@1 0,733 · P@3 0,867 · MRR 0,794 · `degraded: false` |
| Rapport F5 | 7 tests Mann-Whitney, I1–I5, distributions, conclusion rédigée |

### 6. Reproduction (commandes exactes)

```bash
make corpus            # 214 passages, 5 collections
make eval-rag          # F2 : P@1/P@3/MRR sur 30 questions
make experiments       # X1–X7 : 14 configs × 5 runs, modèles réels
make report            # rapport F5 (SQL versionnées + Mann-Whitney)
make test-godot        # 26 tests composants
make e2e               # chaîne réelle Redpanda + E2B + Godot + rejeu
```

Les preuves sont versionnées : `docs/resultats/rapport-experiences.md`,
`docs/resultats/resume-experiences.json`, `docs/resultats/rag_eval.json`.

### 7. État du dépôt

- Commit `172dd39` : RAG GPU réel + corpus + protocole + rapport F5.
- Commit suivant : résultats mesurés, correctifs e2e/WS/Docker, journal.
- Reste à faire : push vers le dépôt distant ; éventuelles captures d'écran
  pour la soutenance (le fond est prêt).
