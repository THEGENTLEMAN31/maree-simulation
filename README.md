# MARÉE — simulation multi-agents d'évacuation de foule

> Projet 5A — Option IA & Big Data · EIGSI Casablanca · 2026
> Monde 02 du catalogue « Mondes Vivants » : **Foule et évacuation**

Une foule qui ne sait rien construit-elle une croyance partagée sur la sortie
sûre, et cette croyance la sauve-t-elle ou la piège-t-elle ? MARÉE simule la
Fête des Lanternes de **Port-Aubel** (ville fictive) où, vers 22 h, une fumée
apparaît côté sud. Des agents LLM et à règles doivent évacuer une esplanade à
trois sorties inégales, en se parlant, en se souvenant, et en déformant ou
non l'information.

**Promesse technique** : un journal d'événements Kafka comme source de vérité,
un rejeu à l'identique **sans appel LLM**, une visualisation Godot qui ne
fait que lire le flux.

---

## ⚡ Démarrage rapide (5 commandes)

```bash
# 1. Télécharge les modèles GGUF sur l'hôte (une fois)
make pull-models

# 2. Lance la stack (Redpanda + llama.cpp + simulation + Godot headless)
make up

# 3. Tests (le rejeu E3 doit rester vert)
make test

# 4. Démo avec interface graphique dans le navigateur
make up-demo        # → http://localhost:6080 (noVNC)

# 5. Rejoue un run depuis le journal (E3, zéro appel LLM)
make replay RUN_ID=run_demo
```

Protocole scientifique complet (reproductible) :

```bash
make corpus          # 209 passages RAG (5 collections, datés, profilés)
make eval-rag        # F2 : précision@1/@3 + MRR sur 30 questions annotées
make experiments     # X1–X7 : 5 runs × 14 configurations, modèles réels
make report          # F5 : tableaux, Mann-Whitney exact, conclusion rédigée
```

Prérequis : Docker + Compose, GPU NVIDIA (4 Go VRAM suffisent), `make`.

---

## 🎯 Question de recherche et hypothèses

**B1 — le « contexte commun » en termes observables** : la part des agents qui
partagent la même croyance sur deux points — *où est le danger* et *quelle
sortie est sûre* — comparée à la vérité terrain que le moteur connaît et que
les agents ne connaissent jamais.

Hypothèses préenregistrées (datées, avant toute mesure) : `docs/hypotheses.md`.

| Expérience | Levier | Configurations | Indicateurs |
|------------|--------|----------------|-------------|
| X1 Annonce | Clarté / moment | claire avant 3 min vs ambiguë après 6 min | I2, I3 |
| X2 Fermeture sortie | Sortie A fermée | avec / sans meneur | I3, I4 |
| X3 Temps | Mode d'exécution | synchrone vs asynchrone | I1, I3, coût |
| X4 Apport LLM | Type d'agent | LLM vs baseline à règles | I1–I4 |
| X5 Mémoire (A1) | Échanges J-3..J-1 | avec / sans | sortie choisie |
| X6 Profils (A3) | Profil | origine vs échangé | décision |
| X7 RAG (F1) | Base de connaissances | activé vs désactivé | I2 |

Règles statistiques (E2) : ≥ 5 runs par configuration, ≥ 2 configurations,
médiane + écart interquartile (les moyennes sont trompeuses à petit n).

---

## 📊 Résultats mesurés (70 runs réels)

Protocole complet exécuté sur GPU (Gemma 4 E2B + bge-m3), 30 agents
(5 LLM + 25 règles), 60 ticks, **14 configurations × 5 runs = 70 runs**.
Rapport complet, tests et limites : `docs/resultats/rapport-experiences.md`.

| Expérience | Ce qui change | Résultat mesuré | Lecture |
|---|---|---|---|
| X1 | annonce claire précoce vs ambiguë tardive | I2 = 0,60 vs 0,60 (p = 0,98) | aucun effet détectable |
| X2 | meneurs (suivi 0,6) vs sans meneurs | évacués 53,3 % vs 56,7 % ; I4 0,32 vs 0,62 (p = 0,056) | tendance, non concluant |
| X3 | décision synchrone vs asynchrone | évacués **93,3 % vs 73,3 %** (p = 0,0079) | **effet significatif** |
| X4 | agents LLM vs agents à règles | I2 0,63 vs 0,53 (p = 0,13) | différence non concluante |
| X5 | mémoire préalable vs sans mémoire | sorties suivies A×3/C×1 vs A×5 | la mémoire diversifie (descriptif) |
| X6 | profils échangés entre deux agents | distributions identiques | résultat négatif conservé |
| X7 | RAG actif vs RAG coupé | I2 = 0,60 vs 0,60 (p = 0,89) | aucun effet détectable |

- **I5 = 0** sur les 70 runs : aucune décision n'a cité une information future.
- **RAG** : 214 passages, P@1 = 0,733, P@3 = 0,867, MRR = 0,794 ; le repli
  lexical n'a jamais été utilisé.
- **Coût** : ~1,9 min/run ; E2B + bge-m3 cohabitent dans 4 Go
  (3 692 Mio mesurés, chat + lot de 60 embeddings + chat validé).

Lecture honnête : un seul effet franchit le seuil de signification avec 5 runs
par bras. Les autres sont rapportés comme non concluants ou négatifs — ils ne
sont pas retirés. Le rapport automatique donne les tests exacts de
Mann-Whitney, les distributions de sorties et les limites assumées.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│ redpanda (Kafka) · llama.cpp (gemma4-e2b + bge-m3 + e4b à la demande)    │
│ python-sim (asyncio : orchestration, agents, RAG, indicateurs, rejeu)    │
│ godot (consommateur pur — headless CI / VNC démo)                        │
└──────────────────────────────────────────────────────────────────────────┘
```

- **16 décisions d'architecture figées au jour 1** → `docs/decisions.md`.
- **32 exigences du cahier des charges → preuve par exigence** →
  `docs/correspondance-exigences.md`.
- Détails → `docs/architecture.md`.

### Population (60 agents)

| Profil | Nb | Modèle | Priorité |
|--------|----|--------|----------|
| Famille (enfant) | 3 | gemma4-e2b | retrouver l'enfant |
| Agent de sécurité | 2 | gemma4-e4b | guider, sa parole pèse |
| Habitués | 3 | gemma4-e4b | partir vite par C |
| Visiteurs | 5 | gemma4-e2b | comprendre avant d'agir |
| Groupe d'amis | 2 | gemma4-e2b | filmer plutôt que partir |
| Foule (baseline) | 45 | règles | suivre le flux |

### Base de connaissances (RAG, F1)

`world_corpus/` — **209 passages** (~103 mots/passage), générés de façon
déterministe par `scripts/generate_corpus.py`, accès contrôlé par profil +
date de disponibilité simulée (C6) :

| Collection | Contenu | Accessible à |
|------------|---------|--------------|
| `plan_signalétique` | zones, sorties, capacités, panneaux | tous |
| `consignes_securite` | protocole d'évacuation | sécurité |
| `annonces` | claire / ambiguë / fausse | tous après diffusion |
| `souvenirs_editions` | incidents passés, rumeurs | habitués et familles |
| `savoir_profils` | ce que chaque profil sait au départ | le profil |

La récupération est **sémantique et réelle** : embeddings `bge-m3` (Q4) sur
GPU via llama.cpp, index FAISS, correction d'anisotropie par centrage sur la
moyenne du corpus. Qualité mesurée (F2, 30 questions annotées) :
**précision@1 = 0,733 · précision@3 = 0,867 · MRR = 0,79**. Un repli lexical
existe, mais il est signalé par `RagClient.degraded` : il n'est jamais
présenté comme du sémantique.

---

## 🧪 Ce qui est prouvé par les tests (19 Python + 26 Godot + 8 WS)

- **Déterminisme** : même config + graine → même hash d'indicateurs au rejeu
  (`test_rejeu_identique_meme_config`).
- **Horloge / ordonnanceur** : sync (latence 0) et async (délai propre).
- **Indicateurs I1–I5** : forment les courbes de l'émergence.
- **RAG** : un passage réservé à `securite` n'est pas retrouvé par un
  visiteur ; un passage du futur n'est pas retrouvé à T (C6).
- **Baseline E1** : un agent à règles répond depuis sa seule perception.
- **Protocole (E2)** : `validate_experiments()` refuse toute paire de
  configurations identiques — chaque expérience change un levier câblé.
- **Statistiques (E2/F5)** : test exact de Mann-Whitney (permutation,
  n = 5 vs 5) vérifié sur des cas connus ; le rapport ne contient plus de
  conclusion « à rédiger ».
- **Rapport (F5)** : généré depuis les journaux, contrôlé par des requêtes
  SQL versionnées (DuckDB).

---

## 🧭 Pour les agents IA qui contribuent

Lis **`AGENTS.md`** : c'est le fil conducteur — les 16 décisions à ne jamais
violer, l'arborescence, les commandes, l'état d'avancement.

## 📁 Structure

```
docs/          décisions, architecture, hypothèses, correspondance exige.
python-sim/    simulation Python (src + tests + config)
godot/         projet Godot (scènes + scripts) + Dockerfiles
world_corpus/  corpus RAG de Port-Aubel (209 passages, 5 collections)
presets/       config llama.cpp router
scripts/       téléchargement modèles
llama.cpp/     Dockerfile d'inférence CUDA
```

## 📜 Note méthodologique

Ce monde est **fictif** : la simulation n'est pas un modèle prédictif validé
sur données réelles, ni une étude en sciences sociales. Elle démontre un
mécanisme — et mesure l'apport du LLM contre une baseline à règles. Un
résultat « le LLM n'apporte rien » y est recevable s'il est démontré.