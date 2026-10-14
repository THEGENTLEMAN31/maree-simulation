.PHONY: help up up-demo down logs build pull-models ingest run replay test fmt lint report

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

report: ## Génère le rapport (tableaux + figures, F5)
	$(COMPOSE) run --rm python-sim python -m src.cli report