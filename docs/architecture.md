# Architecture — vue d'ensemble

Copie du cadrage original (ref: `MARÉE — Cadrage du projet.md`), mise en forme
pour le dépôt. Le monde, la population, la mémoire, le RAG, le protocole
expérimental et le budget sont intégralement décrits dans le cadrage ; ce
fichier ajoute la **carte de l'implémentation**.

## Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        DOCKER COMPOSE (4 services)                        │
├──────────────────────────────────────────────────────────────────────────┤
│  redpanda:9092/8081      │  llama-cpp:8080 (router)                     │
│  (Kafka KRaft + schema)  │  gemma4-e2b + gemma4-e4b (GGUF locaux)        │
├──────────────────────────────────────────────────────────────────────────┤
│  python-sim: 8765 (WS) ──┤  godot-headless / godot-vnc (démo)          │
│  asyncio, agents, RAG,   │  consommateur pur (décision 9)                │
│  metrics, replay         │                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

## Les 5 topics Kafka (C1)

| Topic | Rôle | Partitionnement |
|-------|------|-----------------|
| `world.events` | événements du monde (fumée, annonces, sorties, instantanés) | 1 partition : ordre du registre |
| `agent.decisions` | intentions, justifications, messages, RAG, coût | par agent_id |
| `metrics.indicators` | I1–I5 recalculés en continu | 1 partition |
| `control.commands` | injections depuis Godot (D3) | 1 partition |
| `dlq.invalid` | événements non conformes (F4) | 1 partition |

## Granularité des événements (C1) — justification chiffrée

- **1 événement par fait** : perception, message entre agents, décision LLM
  (intention + justification + passages RAG), changement de croyance,
  arrivée en zone, sortie. Ordre du millier de messages par run.
- **Instantané agrégé des positions** : 1 message par tick pour tous les
  agents (~900 messages pour 15 min). Godot interpole entre deux instantanés.
- **Aucun fichier par agent et par pas** : à 10/s pour 60 agents cela ferait
  ~540 000 messages/run sans rien apporter aux indicateurs ni au rejeu.

## Boucle d'un run (orchestrateur)

```
pour chaque tick T (horloge simulée) :
  1. monde.tick_world(T)          → étend la fumée (loi déterministe)
  2. variantes expérimentales     → annonce (X1), fermeture sortie (X2)
  3. due = scheduler.due_agents(T)→ qui pense à T (sync : tous / async : rythme)
  4. pour chaque agent (ordre canonique seq) :
       perception figée à T        (décision 10)
       intention = decide(perception)   (LLM via gateway / règle)
       messages naturels → voisins (A2)
       moteur exécute l'intention  (décision 8)
  5. instantané agrégé → Godot + journal (C1, E3)
  6. tous les 10 ticks : I1–I5 → metrics + Godot
```

## Stockage justifié par besoin d'accès (F3)

| Donnée | Où | Pourquoi |
|--------|----|----------|
| Flux d'événements | Kafka (rétention courte) | Volume élevé, lecture séquentielle, faible latence |
| Journal de rejeu | JSONL (`/logs/<run_id>.events.jsonl`) | Append-only, source du rejeu E3 |
| Historique des runs | JSONL + Parquet interrogé par DuckDB (F5) | Volume modéré, requêtes reproductibles |
| Base de connaissances | `rag.py` en mémoire + `world_corpus/` | Quelques centaines de passages, accès par profil |

## Inférence LLM (2 modèles, 1 réserve VRAM 4 Go)

| Modèle | Rôle | Agents | Preset llama.cpp |
|--------|------|--------|------------------|
| `gemma4-e2b` | rapide, 9 profils (famille, visiteur, amis) | LLM `temperature=0.3` | `[gemma4-e2b]` |
| `gemma4-e4b` | raisonnement, 6 profils (sécurité, habitués) | LLM `temperature=0.2` | `[gemma4-e4b]` |

Configuration détaillée (n-gpu-layers, kv-cache q8_0, flash-attn) :
`presets/maree.ini`.

**Note de divergence sur le cadrage** : le cadrage prévoyait Chroma DB et
OpenRouter pour les « profils à expérience ». Le choix final :
- LLM 100 % locaux via llama.cpp (aucun quota) ;
- RAG en mémoire process (python-sim), corpus Markdown versionné.

C'est un choix documenté, pas un oubli : il supprime la dépendance à une API
et garde l'exigence A5 (deux tailles de modèle) satisfaite localement.