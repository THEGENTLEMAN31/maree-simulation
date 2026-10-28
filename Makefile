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

run-e2e:  ## le scénario du piège (A se ferme à t40)
	uv run maree run run=e2e

smoke:  ## run complet sans LLM ni GPU (60 agents à règles)
	uv run maree run population=rules_only bus.backend=memory narrative.enabled=false

replay:  ## rejeu E3 du dernier run
	uv run maree replay

serve:  ## diffuse le dernier run en WebSocket (pour Godot)
	uv run maree serve

godot:  ## lance le client de visualisation
	godot --path godot/project

experiments:  ## protocole X1–X7 (par défaut X1, 3 graines)
	uv run maree experiment --name x1 --seeds 3

report:  ## rapport agrégé
	uv run maree report

# ------------------------------------------------------------
# Diagnostic
# ------------------------------------------------------------
spike:  ## vérifie JuPedSim / Mesa / registry
	uv run python scripts/spike.py

vram:  ## usage VRAM courant
	nvidia-smi --query-gpu=memory.used,memory.total --format=csv

.PHONY: help install lock test test-all lint fmt type corpus pull-models up down logs topics run run-e2e smoke replay serve godot experiments report spike vram
