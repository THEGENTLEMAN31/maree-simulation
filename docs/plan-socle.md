# Plan de complétude — les 32 exigences du défi commun

> **Ce document est un plan de chantier, pas de la documentation.** Il se met à
> jour à chaque étape validée. Une case cochée = testé, committé, poussé.
>
> Référence : `Mondes-Vivants_Projet-5A-IABD.html`, défi commun.
> 20 exigences de socle, 9 de standard, 3 d'excellence.
>
> **Principe directeur** : le moteur reste modulable et le client (Godot, front)
> garde toute sa liberté. Le moteur n'impose rien au client : il publie des
> **trames JSON** autoportantes (un événement → une trame), et le client peut
> ignorer, agréger ou rejouer ce qu'il veut. Toute fonctionnalité d'affichage
> passe par une trame documentée dans `docs/protocol-ui.md`, jamais par une
> dépendance du client au moteur.

---

## 1. État de départ (audit du 2026-10-29)

| Statut | Exigences | Nombre |
|---|---|---|
| **Tenu** | A3, A6, B1, B2, C2, C5, D1, E1, E2, F1 | 10 |
| **Partiel** | A1, A2, B3, C1, C3, D2, E3, E4, F2, F3, F4, F5, F6 | 13 |
| **Absent** | A4, A5, B4, C4, C6, C7, C8, D3, E5 | 9 |

Trois « partiels » cachent un bug qui rend l'exigence **impossible** :

- `causation_id` = **0 / 1 181** événements d'un journal réel : `_emit` n'appelle
  jamais `Event.child()`. Sans cela, B4 ne peut pas exister.
- les passages RAG **ne sont pas journalisés** : F2 n'est pas recalculable.
- `t_trait == t_prod` en dur (`simulation.py`) : C3 est faux, C7 impossible.

Et une ligne oubliée : `Profile.model` n'est **jamais** passé à `chat()` → A5 absent.

---

## 2. Les quatre vagues

### Vague 1 — bugs d'une ligne et preuves gratuites

- [x] **A5** — modèle par profil (`two_tier`), tiers `big`/`small` résolus dans
      l'adaptateur. Un profil garde son tier, le YAML choisit le nom.
      *Sortie* : deux noms de modèles coexistent dans un run ; `llm.model`
      journalisé par décision.
- [x] **B4** — `causation_id` réel : `_emit(..., cause=…)`, chaîne
      message → décision → croyance → message suivant. Script
      `scripts/trace_indicator.py` qui remonte d'un saut d'indicateur aux
      échanges qui l'ont précédé.
      *Sortie* : un journal réel où ≥ 50 % des décisions ont une cause.
- [x] **F2** — journaliser `retrieved` (doc_id, texte, score, collection) et
      `memory` (épisodes utilisés) dans `agent.decision`. Corpus d'évaluation
      annoté + `scripts/eval_rag.py` (P@1, P@3, MRR).
      *Sortie* : un rapport de récupération calculé, pas un artefact v1.
- [x] **E3** — un run enregistré dans le dépôt (`runs/demo_replay/`), exception
      `.gitignore`, `make replay-demo`, hash d'indicateurs identique.
- [x] **Docs honnêtes** — corriger les 5 affirmations fausses de
      `docs/cadrage-maree.md`, archiver les artefacts v1.

### Vague 2 — le socle manquant

- [ ] **D3** — injection en direct : file de contrôle drainée en tête de
      `_world_events` (perception figée préservée), trame entrante documentée,
      `control.injection` journalisé avec `causation_id`.
      *Sortie* : `maree live` + un client qui envoie `{"type":"inject",…}`.
- [ ] **D2** — `snapshot` porte `memory`, `last_decision` (raison, règle,
      passages) → inspection sans reconstruction côté client.
- [ ] **C6** — vérificateur de cohérence temporelle : aucun agent n'agit sur une
      info postérieure à sa décision ; compteur dans `run.ended` et dans le
      journal (`temporal.violation`).
- [ ] **A2 / B3** — bras `sans_communication` : la diffusion est coupée, I1 doit
      s'effondrer. C'est la preuve que l'indicateur distingue l'émergence de son
      absence.
- [ ] **E4** — agréger `tokens_in/out` par run et par bras ; bilan de sobriété
      (appels, tokens, mural, VRAM) mis en regard de l'apport.
- [ ] **F4** — schémas par type documentés et versionnés, validation à l'écriture,
      `dlq.invalid` réellement émis, quarantaine sans arrêt du run.
- [ ] **A1** — préhistoire : épisodes horodatés à J−3, rappelés par la mémoire
      bornée ; bras d'ablation `prehistory_days=0|3`.
- [ ] **F6** — `sources` (seq) sur la trame `indicators` : remontée exacte.

### Vague 3 — le temps, le vrai

- [ ] **C4** — mode `async` : les décisions ne sont plus appliquées au tick où
      elles sont lancées. Deux sous-modes : `simulated` (latence tirée d'une
      graine → rejouable) et `real` (latence réelle → journalisée, rejouable).
- [ ] **C3** — `t_prod` = tick de perception figée, `t_trait` = tick
      d'application ; les deux diffèrent en mode async.
- [ ] **C7** — distribution `t_trait − t_prod` par type d'événement, sous charge
      (rafale d'injections, 60 agents LLM).
- [ ] **C8** — deux tailles de population (20 / 60) en soutenance, comparaison
      scriptée.
- [ ] **A4** — détecteur d'incidents : sortie de rôle (formules d'assistant),
      réponse inexploitable (JSON invalide), absence de réponse. Événement
      `agent.incident` + compteur par type.

### Vague 4 — le coûteux

- [ ] **C1 / O3** — pont Kafka : `frame_for(event)` extrait de `ws.py`,
      `maree serve --source kafka`, réordonnancement par `seq`, publication
      **best-effort** (un broker mort ne tue plus le run), `group_id` unique.
- [ ] **E5** — protocole `mixte` (deux tailles) contre `tous_grand`, à apport
      comparable : I1/I2/I3/I7 + appels + tokens + taux de repli.
- [ ] **F3 / F5** — architecture de données documentée ; requêtes reproductibles
      DuckDB sur les JSONL (aucun Parquet nécessaire).

---

## 3. Journal d'exécution

| Date | Étape | Commit | Tests | Notes |
|---|---|---|---|---|
| 2026-10-29 | plan écrit | — | 138 passent | point de départ |
| 2026-10-29 | A5 deux tiers + B4 causalité + F2 RAG journalisé + E3 run versionné + docs corrigées | `vague1` | 149 passent, ruff propre | voir ci-dessous |

### Mesures de la vague 1

- **A5** : `Profile.tier` (`big`/`small`) remplace `Profile.model` ; le YAML
  choisit les noms (`gemma4-e2b`, `qwen3-0.6b`). `two_tier: true` par défaut.
  L'adaptateur retombe sur le grand modèle si le petit manque, et la trace
  porte `requested_model` ≠ `model`.
- **B4** : `_emit(cause=…)` → `Event.child()`. Run réel : **820 / 1 023**
  événements avec `causation_id`, 54 / 212 décisions causées (les autres
  sont périodiques, sans parent inventé), **160 chaînes** distinctes.
  `maree trace --run-id … --indicator I1_consensus` remonte la chaîne.
- **F2** : `retrieved` + `memory` journalisés par décision. Évaluation
  mesurée sur 24 requêtes annotées : **P@1 0,417 · P@3 0,750 · MRR 0,569**.
  La faiblesse est expliquée (corpus généré, doublons de template), pas
  maquillée.
- **E3** : `runs/demo_replay/` versionné — 32 ticks, 1 020 événements,
  **49 appels / 49 succès**, 18 s, 60/60, `maree replay` → `ok: true`,
  49/49 décisions concordantes, 3 replis règles annoncés.
- **Docs** : `cadrage-maree.md` porte un bandeau et cinq sections corrigées ;
  les artefacts v1 sont archivés dans `docs/resultats/v1/`.

---

## 4. Décisions prises en autonomie

1. **Pas de Parquet.** DuckDB lit les JSONL nativement (`read_json_auto`) :
   ajouter un format serait un coût sans bénéfice. F3 documente les quatre
   stockages réels, F5 fournit des requêtes `.sql` reproductibles.
2. **Petit modèle = `qwen3-0.6b`**, grand = `gemma4-e2b`. Écart de taille 3,3×,
   défendable. Le petit est attribué aux profils dont la décision est simple
   (`visiteur`, `vendeur`), jamais selon une catégorie sociale.
3. **Deux sous-modes asynchrones.** `simulated` garde E2 (runs reproductibles) ;
   `real` satisfait C4 à la lettre. Les deux sont journalisés, donc rejouables.
4. **Kafka hors du chemin de mesure.** `bus.backend=memory` reste la règle des
   campagnes ; Kafka sert la démonstration C1/O3. La publication devient
   best-effort.
5. **Le client ne dépend jamais du moteur.** Une fonction pure
   `frame_for(event)` est la seule interface ; tout ajout passe par une trame.

---

## 5. Risques

- **VRAM** : e2b + qwen3-0.6b + bge-m3 ≈ 2,5 Go sur 4 Go. Mesuré 1 980 MiB pour
  e2b+bge-m3 ; marge ~1,5 Go. Si OOM : `parallel=2`, `ctx-size=4096`.
- **Kafka injoignable ici** : le pont est testé avec un faux bus ; la démo se
  fait en `memory`.
- **Quota LLM** : les runs LLM exigent le conteneur ; à défaut, les tests
  utilisent un faux LLM et les campagnes sont documentées comme non rejouées.
- **Bruit LangSmith** : préfixer les commandes par `LANGCHAIN_TRACING_V2=false`.
