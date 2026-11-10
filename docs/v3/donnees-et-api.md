# Données et API

_Ce document décrit où vivent les données, comment elles sont exposées,
et comment le front peut configurer la fiche d'un individu._

---

## 1. Matrice de stockage

| Jeu de données | Volume cible | Nature | Stockage |
|---|---:|---|---|
| Bâtiments, scénarios, runs, agents | petit | jointures, intégrité | **PostgreSQL** |
| Corpus + embeddings | moyen | recherche filtrée | **pgvector** (ou Qdrant) |
| Faits (décisions, messages, croyances) | gros | colonnes, agrégats | **Parquet + DuckDB** |
| Métriques (I1–I7, par sortie, par étage) | moyen | série temporelle | **Parquet** partitionné |
| Snapshots, trajectoires, GLB, rapports | gros | objets | **S3 / MinIO** |
| Flux temps réel | — | diffusion | **Redpanda** |
| État courant | petit | clé-valeur | **Redis** ou table Postgres |

### 1.1 Pourquoi pas une seule base

- une décision se lit par run / agent / tick → colonnaire ;
- un scénario se joint → relationnel ;
- un snapshot se récupère par clé → objet ;
- un embedding se cherche par similarité → vectoriel.

Forcer un seul moteur, c'est payer 10× le stockage ou 100× la latence.

### 1.2 Le journal reste la source de vérité

- les faits sont écrits append-only, puis convertis en Parquet ;
- les snapshots sont des artefacts, pas la vérité ;
- le rejeu lit les faits, pas les agrégats.

---

## 2. Schémas

### 2.1 Run

```sql
run(
  id, world_id, world_hash, scenario_id,
  seed, config_hash, mode,
  started_at, ended_at, status,
  ticks, agents, evacuated,
  llm_calls, tokens_in, tokens_out
)
```

### 2.2 Agent (registre)

```sql
agent(
  run_id, agent_id, archetype, policy, model,
  seed, bio, traits_json, created_at
)
```

### 2.3 Événement (Parquet)

Colonnes communes :

```text
run_id, seq, type, t_prod, t_trait, t_real,
causation_id, correlation_id, schema_version
```

Colonnes spécifiques selon le type, dans des fichiers séparés :

```text
events/run_id=.../type=agent.decision/part-*.parquet
events/run_id=.../type=agent.message/part-*.parquet
events/run_id=.../type=metrics.indicators/part-*.parquet
```

Les gros textes (`prompt`, `raw_output`, `retrieved.text`) vont dans un
stockage objet, référencés par `blob_id`.

---

## 3. API REST

Base : `/v1`. OpenAPI généré par FastAPI.

### 3.1 Mondes

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/worlds` | liste |
| `GET` | `/worlds/{id}` | WorldSpec |
| `POST` | `/worlds/import` | import IFC |
| `POST` | `/worlds/generate` | génération procédurale |
| `POST` | `/worlds/{id}/validate` | validation |
| `GET` | `/worlds/{id}/render.glb` | GLB |
| `GET` | `/worlds/{id}/manifest.json` | manifeste IDs |

### 3.2 Scénarios et runs

| Méthode | Chemin | Rôle |
|---|---|---|
| `POST` | `/scenarios` | créer |
| `GET` | `/scenarios/{id}` | lire |
| `POST` | `/runs` | lancer |
| `GET` | `/runs` | lister |
| `GET` | `/runs/{id}` | résumé |
| `POST` | `/runs/{id}/cancel` | arrêter |
| `GET` | `/runs/{id}/metrics` | I1–I7 + par sortie + par étage |
| `GET` | `/runs/{id}/export?format=csv\|parquet\|json` | export |
| `GET` | `/runs/{id}/compare/{other}` | comparaison |

### 3.3 Agents

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/runs/{id}/agents` | liste, filtres |
| `GET` | `/runs/{id}/agents/{agent}` | **dossier** |
| `GET` | `/runs/{id}/agents/{agent}/comms` | communications |
| `GET` | `/runs/{id}/agents/{agent}/timeline` | historique |
| `GET` | `/runs/{id}/agents/{agent}/explain` | explication d'une décision |

### 3.4 Expériences

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/experiments` | liste |
| `GET` | `/experiments/{id}` | résultats |
| `GET` | `/experiments/{id}/report` | rapport |

### 3.5 Système

| Méthode | Chemin | Rôle |
|---|---|---|
| `GET` | `/health` | santé |
| `GET` | `/version` | versions |

---

## 4. Le dossier agent

### 4.1 Sections

| Section | Contenu | Nature |
|---|---|---|
| `identity` | id, nom, archétype, bio, rôle, apparence | statique |
| `traits` | risque, herding, altruisme, mobilité… | statique |
| `state` | stress, fatigue, CO, visibilité, densité | dynamique |
| `intention` | action, cible, raison, tick | dynamique |
| `appraisal` | menace, urgence, efficacité, preuve sociale, responsabilité | dynamique |
| `beliefs` | sorties : confiance, source, tick | dynamique |
| `memory` | épisodes récents | dynamique |
| `receipts` | faits appris, source, tick, confiance | dynamique |
| `comms` | messages envoyés/reçus | dynamique |
| `relations` | proches, groupe, leader, confiance | dynamique |
| `history` | décisions passées | dynamique |
| `docs` | passages RAG consultés | dynamique |
| `inner_monologue` | texte interne si LLM | **généré** |

### 4.2 Sélection des sections

```http
GET /v1/runs/{run}/agents/A19?include=identity,traits,state,intention,beliefs,memory,receipts,comms
```

Le front peut demander un sous-ensemble. Le serveur ne calcule que ce qui est
demandé.

### 4.3 Template configurable

```yaml
dossier:
  sections:
    identity:   { title: "Qui est-ce ?", fields: [name, bio, archetype] }
    intention:  { title: "Que fait-il ?", fields: [action, target, reason] }
    beliefs:    { title: "Ce qu'il croit", fields: [exit, confidence, source] }
    receipts:   { title: "Ce qu'il a appris", fields: [fact, source, tick] }
    comms:      { title: "À qui a-t-il parlé ?", fields: [sender, content, tick] }
  order: [identity, intention, beliefs, receipts, comms]
```

Le front peut ignorer ce template et composer ses propres panneaux : le serveur
expose un **superset**.

### 4.4 Distinction honnête

Trois étiquettes obligatoires :

- `measured` : croyance, état, reçu ;
- `derived` : appraisal, intention ;
- `generated` : monologue interne, justification LLM.

Le front doit afficher l'étiquette. Sinon, il laisse croire que le monologue
est la vérité du modèle.

### 4.5 Explication d'une décision

```http
GET /v1/runs/{run}/agents/A19/explain?decision_seq=412
```

Réponse :

```json
{
  "decision_seq": 412,
  "tick": 14,
  "trigger": "sortie_fermee",
  "appraisal": {"threat": 0.8, "urgency": 0.9, "efficacy": 0.3, "social": 0.6},
  "beliefs_at_time": {"A": 0.9, "B": 0.2},
  "receipts": [
    {"fact": "sortie A fermée", "source": "vu", "tick": 14, "confidence": 1.0}
  ],
  "causal_chain": ["world.exit_closed:120", "A19.agent.decision:412"],
  "policy": "hybrid",
  "model": "qwen3-0.6b"
}
```

---

## 5. WebSocket

### 5.1 Enveloppe

Chaque trame porte :

```json
{
  "v": 3,
  "type": "...",
  "run_id": "...",
  "seq": 123,
  "t_prod": 14,
  "t_trait": 14
}
```

### 5.2 Négociation

```json
{"type": "hello", "protocol_version": 3, "capabilities": ["delta", "seek"]}
```

### 5.3 TramES

| Trame | Contenu |
|---|---|
| `hello` | run, monde, hash, protocole, capacités |
| `snapshot` | tick, agents, sorties, dangers, densité |
| `delta` | changements depuis le dernier snapshot |
| `decision` | agent, intention, raison, politique |
| `belief` | croyances mises à jour |
| `message` | émetteur, destinataires, contenu |
| `heard` | réception |
| `evacuated` | agent, sortie, étage |
| `hazard` | source, niveau, visibilité |
| `indicators` | I1–I7 + par sortie + par étage |
| `narrative` | texte + validité |
| `incident` | cause |
| `end` | bilan |
| `trace` | chaîne causale |
| `error` | code, message, retryable |

### 5.4 Contrôle

```json
{"type": "subscribe", "agent": "A19", "fields": ["state", "intention", "beliefs"]}
{"type": "pause"}
{"type": "resume"}
{"type": "seek", "tick": 42}
{"type": "inject", "kind": "fire", "level": "L1", "position": [70, 40]}
```

### 5.5 Reprise

```json
{"type": "hello", "protocol_version": 3, "resume_from_seq": 812}
```

Le serveur renvoie les trames manquantes, ou un `snapshot` complet si la
rétention ne le permet pas.

---

## 6. Versioning

| Objet | Champ | Politique |
|---|---|---|
| REST | `/v1` | dépréciation annoncée |
| WS | `protocol_version` | négociation |
| Événement | `schema_version` | upcast ou refus |
| World | `schema` | migration explicite |
| Dossier | `dossier_schema` | sections additives |

---

## 7. Sécurité

| Sujet | Décision |
|---|---|
| Auth | token / OIDC, jamais anonyme en écriture |
| Origine WS | `Origin` vérifié |
| Limites | taille de trame, fréquence d'injection, nombre de clients |
| Injections | validation stricte, `command_id` idempotent |
| Rôles | `viewer`, `operator`, `analyst`, `admin` |
| Secrets | variables d'environnement, jamais dans le journal |

---

## 8. Erreurs

```json
{
  "error": {
    "code": "world_invalid",
    "message": "le portail P_HALL_CORR ne sépare aucun espace",
    "details": {"portal": "P_HALL_CORR"},
    "retryable": false,
    "request_id": "req_..."
  }
}
```

Codes : `world_invalid`, `run_not_found`, `agent_not_found`, `injection_invalid`,
`rate_limited`, `provider_unavailable`, `internal`.

---

## 9. Export

| Format | Contenu |
|---|---|
| `json` | run complet, agents, métriques |
| `csv` | métriques par tick, par sortie |
| `parquet` | faits et métriques |
| `glb` | monde |
| `png` / `mp4` | rendu (côté front) |
