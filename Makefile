# ============================================================
# MARÉE v2 — raccourcis de développement
# ============================================================
.DEFAULT_GOAL := help
SHELL := /bin/bash

# ------------------------------------------------------------
help:  ## liste les cibles
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------
# Installation
# ------------------------------------------------------------
install:  ## crée le venv et verrouille les dépendances
	uv sync --all-extras
	uv run pre-commit install || true

lock:  ## régénère uv.lock
	uv lock

# ------------------------------------------------------------
# Qualité
# ------------------------------------------------------------
test:  ## pytest (unitaires, sans GPU ni Docker)
	uv run pytest

test-all:  ## pytest y compris physique et LLM (lent)
	uv run pytest -m "slow or gpu"

lint:  ## ruff
	uv run ruff check src tests

fmt:  ## ruff format
	uv run ruff format src tests
	uv run ruff check --fix src tests

type:  ## mypy
	uv run mypy src

# ------------------------------------------------------------
# Corpus et modèles
# ------------------------------------------------------------
corpus:  ## régénère world_corpus/ (déterministe)
	uv run python scripts/generate_corpus.py

pull-models:  ## télécharge les GGUF sur l'hôte
	bash scripts/download_models.sh

# ------------------------------------------------------------
# Stack
# ------------------------------------------------------------
up:  ## Redpanda + llama.cpp + simulation (headless)
	docker compose up -d

down:  ## arrête la stack
	docker compose down

logs:  ## journaux de la simulation
	docker compose logs -f sim

topics:  ## crée les topics Redpanda
	docker compose exec redpanda rpk topic create \
		world.events agent.decisions agent.beliefs narrative.generated \
		metrics.indicators control.commands dlq.invalid --if-not-exists

# ------------------------------------------------------------
# Exécution
# ------------------------------------------------------------
run:  ## un run de démonstration
	uv run maree run run=demo

run-e2e:  ## le scénario du piège (A se ferme à t14)
	uv run maree run run=e2e

smoke:  ## run complet sans LLM ni GPU (60 agents à règles)
	uv run maree run population=rules_only bus.backend=memory narrative.enabled=false

replay:  ## rejeu E3 du dernier run
	uv run maree replay

replay-demo:  ## rejoue le run versionné sans aucun appel LLM (E3)
	uv run maree replay --run-id demo_replay

demo-pair:  ## régénère la paire versionnée 20 / 60 agents (C8)
	uv run maree run run_id=demo20 population=demo20 bus.backend=memory narrative.enabled=false
	uv run maree run run_id=demo60 population=demo60 bus.backend=memory narrative.enabled=false
	uv run maree replay --run-id demo20
	uv run maree replay --run-id demo60

replay-pair:  ## rejoue la paire 20 / 60 sans GPU (C8)
	uv run maree replay --run-id demo20
	uv run maree replay --run-id demo60

serve:  ## diffuse le dernier run en WebSocket (pour Godot)
	uv run maree serve

godot:  ## lance le client de visualisation
	godot --path godot/project

godot-test:  ## contrat d'affichage (D2/D3) sans serveur ni GPU
	godot --headless --path godot/project --script res://tests/test_client.gd

experiments:  ## protocole X1–X7 (par défaut X1, 3 graines)
	uv run maree experiment --name x1 --seeds 3

report:  ## rapport agrégé
	uv run maree report

report-v3:  ## rapport de divergence des jumeaux (semaine 3)
	uv run python scripts/v3_twins_report.py

report-v3-bench:  ## tableau comparatif des politiques (semaine 4)
	uv run python scripts/v3_bench_report.py

v3-pipeline:  ## lance la pipeline réelle (monde -> agents -> vrai LLM -> mémoire)
	MAREE_LLM_URL=$${MAREE_LLM_URL:-http://127.0.0.1:8081/v1} V3_SEED=42 \
		uv run python scripts/v3_pipeline.py

# Le LLM *projet* (jamais le serveur perso 8080). reasoning off = court et propre.
V3_GGUF=/mnt/data/maree-models/gemma-4-E2B-it-Q4_K_M.gguf
v3-llm-up:  ## démarre le llama-server projet sur 8081 (E2B, reasoning off)
	/mnt/data/llama.cpp/build/bin/llama-server -m $(V3_GGUF) --host 127.0.0.1 \
		--port 8081 --alias gemma4-e2b --ctx-size 4096 --parallel 1 \
		--n-gpu-layers 99 --flash-attn on --threads 4 --no-webui --reasoning off &

v3-llm-down:  ## arrête le llama-server projet (8081)
	-@pid=$$(ss -ltnp 2>/dev/null | grep ':8081' | grep -oP 'pid=\K[0-9]+' | head -1); \
		[ -n "$$pid" ] && kill $$pid && echo "8081 arrêté" || echo "8081 déjà absent"

# Kafka SANS Docker : vrai Apache Kafka KRaft sur l'hôte (C1). Le journal
# reste la source de vérité ; ce broker sert la preuve C1 et le flux live.
kafka-up:  ## télécharge (si besoin) + lance Kafka KRaft single-node sur 9092
	bash scripts/kafka_standalone.sh up

kafka-down:  ## arrête le broker Kafka
	bash scripts/kafka_standalone.sh down

kafka-topics:  ## crée les topics du projet
	K=$${KAFKA_DIR:-/mnt/data/kafka}/kafka/bin; \
	for t in mv.events mv.indicators mv.snapshots mv.control dlq.invalid; do \
		$$K/kafka-topics.sh --bootstrap-server 127.0.0.1:9092 --create \
			--if-not-exists --topic $$t >/dev/null 2>&1 && echo "topic $$t ok"; \
	done

v3-replay-demo:  ## rejoue le run versionné (E3) — sans LLM ni Kafka
	uv run python -c "from maree.v3.sim.replay import replay_jsonl; from pathlib import Path; r=replay_jsonl(Path('runs/v3/demo_replay_v3.jsonl')); print('run', r.run_id, '| digest', r.digest[:16], '|', r.summarize())"

v3-divergence:  ## la mission au vrai LLM : mémoire personnelle → choix opposés
	MAREE_LLM_URL=$${MAREE_LLM_URL:-http://127.0.0.1:8081/v1} uv run python scripts/v3_divergence.py

# Le scénario qui sépare les tailles : éviter la sortie crue bloquée.
# Le banc est testé sans GPU (tests/v3/test_scenario_blocked.py).
v3-blocked:  ## campagne « sortie bloquée » : grand vs petit vs ablation
	MAREE_LLM_URL=$${MAREE_LLM_URL:-http://127.0.0.1:8081/v1} \
	MAREE_LLM_SMALL_URL=$${MAREE_LLM_SMALL_URL:-http://127.0.0.1:8082/v1} \
		uv run python scripts/v3_campaign_blocked.py 1 2 3 4 5

v3-serve:  ## sert un run v3 en WS pour le client (P4) — 8766
	uv run python scripts/v3_serve.py --start-now

# ------------------------------------------------------------
# v3 — les affirmations du rapport, une commande chacune
# ------------------------------------------------------------
v3-twins:  ## mission n°1 : la mémoire fait diverger les jumeaux (aucun GPU)
	uv run python scripts/v3_twins.py 200 1 2 3 4 5

v3-worlds:  ## P1.2 : cinq salles, le goulot tient-il ? (aucun GPU)
	uv run python scripts/v3_worlds.py 5

v3-denial:  ## P2.2 / H5 : un démenti tardif, qui atteint-il ? (aucun GPU)
	uv run python scripts/v3_denial.py 1 2 3

v3-crowd:  ## campagne macro (serveurs 8081/8082 requis)
	MAREE_LLM_URL=$${MAREE_LLM_URL:-http://127.0.0.1:8081/v1} \
	MAREE_LLM_SMALL_URL=$${MAREE_LLM_SMALL_URL:-http://127.0.0.1:8082/v1} \
	LANGCHAIN_TRACING_V2=false \
		uv run python scripts/v3_crowd_campaign.py

v3-crowd-null:  ## le null de B3 : même monde, sans émission (aucun LLM requis)
	uv run python scripts/v3_crowd_campaign.py --silent --arms=regles

v3-tables:  ## régénère docs/v3/resultats-c6.md depuis les JSON
	uv run python scripts/rapport_crowd.py

# ------------------------------------------------------------
# Diagnostic
# ------------------------------------------------------------
spike:  ## vérifie JuPedSim / Mesa / registry
	uv run python scripts/spike.py

vram:  ## usage VRAM courant
	nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader

# ------------------------------------------------------------
# Navigation du code (Graphify, docs/v3/graphify.md)
# ------------------------------------------------------------
graph:  ## construit la carte du code (local, sans LLM)
	graphify extract . --code-only

graph-update:  ## met à jour la carte après modifications
	graphify update .

graph-report:  ## régénère le rapport et les communautés
	graphify cluster-only .
	@echo "rapport : graphify-out/GRAPH_REPORT.md"

graph-html:  ## exporte le call-flow en HTML/Mermaid
	graphify export callflow-html

graph-query:  ## interroge le graphe (ex. make graph-query Q="...")
	graphify query "$(Q)"

.PHONY: help install lock test test-all lint fmt type corpus pull-models up down logs topics run run-e2e smoke replay replay-demo serve godot experiments report report-v3 report-v3-bench v3-pipeline v3-llm-up v3-llm-down v3-replay-demo v3-divergence v3-blocked v3-serve v3-twins v3-worlds v3-denial v3-crowd v3-crowd-null v3-tables kafka-up kafka-down kafka-topics spike vram graph graph-update graph-report graph-html graph-query
