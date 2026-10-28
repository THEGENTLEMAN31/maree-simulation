.PHONY: help up up-demo down logs build pull-models ingest run replay test fmt lint report test-godot editor e2e e2e-async e2e-e4b eval-rag experiments experiments-dry corpus c8 c7 b3

SHELL := /bin/bash
COMPOSE := docker compose

help: ## Affiche l'aide
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Démarre la stack complète (headless, CI)
	$(COMPOSE) up --build

up-demo: ## Démarre la stack avec visaulisation Godot VNC (navigateur :6080)
	$(COMPOSE) -f docker-compose.yml -f docker-compose.demo.yml up --build

down: ## Arrête tout
	$(COMPOSE) down
	$(COMPOSE) -f docker-compose.yml -f docker-compose.demo.yml down

logs: ## Suit les logs
	$(COMPOSE) logs -f

build: ## Rebuild les images
	$(COMPOSE) build

pull-models: ## Télécharge les modèles GGUF (host, une fois)
	./scripts/download_models.sh

ingest: ## Ingère le corpus RAG dans LanceDB
	$(COMPOSE) run --rm python-sim python -m src.cli ingest

run: ## Lance un run de simulation unique
	$(COMPOSE) run --rm python-sim python -m src.cli run --run-id run_demo

replay: ## Rejoue un run depuis le journal (E3)
	$(COMPOSE) run --rm python-sim python -m src.cli replay --run-id run_demo

test: ## Lance les tests Python
	$(COMPOSE) run --rm python-sim python -m pytest tests/ -q

fmt: ## Formate le code
	cd python-sim && uvx ruff format src tests scripts

lint: ## Lint le code
	cd python-sim && uvx ruff check src tests scripts

report: ## Génère le rapport (tableaux, tests, F2, F5)
	$(COMPOSE) run --rm python-sim python -m src.cli report \
	  --log-dir /logs --out /logs/report.md --rag-eval /logs/rag_eval.json

eval-rag: ## Évalue la récupération sémantique (F2) sur le corpus réel
	$(COMPOSE) run --rm python-sim python -m src.experiments.rag_eval \
	  /world_corpus http://llama-cpp:8081/v1

experiments: ## Exécute X1–X7 (5 runs × 14 configurations)
	$(COMPOSE) run --rm python-sim python -m src.cli experiments \
	  -c config/experiments.yaml --runs-per-config 5 \
	  --log-dir /logs --corpus /world_corpus --llm-url http://llama-cpp:8081/v1

experiments-dry: ## Répétition générale du protocole sans appel LLM
	$(COMPOSE) run --rm python-sim python -m src.cli experiments \
	  -c config/experiments.yaml --runs-per-config 2 --dry-run \
	  --log-dir /logs --corpus /world_corpus

corpus: ## Régénère le corpus synthétique structuré (209 passages)
	python3 scripts/generate_corpus.py
	python3 scripts/generate_corpus.py --check

test-godot: ## Tests des composants Godot (headless, hors ligne)
	docker run --rm -v "$$PWD/godot/project:/godot/project" \
	  --entrypoint /usr/local/bin/godot maree-simulation-godot-headless \
	  --path /godot/project --headless --script res://tests/run_tests.gd

editor: ## Éditeur Godot dans le navigateur (:6081) — projet monté depuis l'hôte
	$(COMPOSE) -f docker-compose.yml -f docker-compose.demo.yml --profile editor up godot-editor

e2e: ## Test de bout en bout de la chaîne réelle (Redpanda + LLM + Godot + rejeu)
	./scripts/run_e2e.sh

e2e-async: ## Idem en mode asynchrone
	E2E_CONFIG=e2e-godot-async.yaml E2E_RUN_ID=e2e_godot_async ./scripts/run_e2e.sh

e2e-e4b: ## Idem avec le grand modèle (E4B, offload partiel)
	E2E_CONFIG=e2e-godot-e4b.yaml E2E_RUN_ID=e2e_godot_e4b ./scripts/run_e2e.sh

c8: ## Deux populations 20/60, rejeu comparé (C8)
	$(COMPOSE) run --rm python-sim python -m src.experiments.c8 --ticks 30 --out /logs/c8_summary.json

c7: ## Latence LLM -> ticks + rafale (C7)
	$(COMPOSE) run --rm python-sim python -m src.experiments.c7 --ticks 30 --out /logs/c7_summary.json

b3: ## Contrôles négatifs B3 (20 runs, embeddings réels)
	$(COMPOSE) run --rm python-sim python -m src.cli experiments \
	  -c config/experiments.yaml --runs-per-config 5 --only B3 \
	  --log-dir /logs/b3 --corpus /world_corpus --llm-url http://llama-cpp:8081/v1
