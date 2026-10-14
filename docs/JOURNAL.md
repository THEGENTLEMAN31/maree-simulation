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