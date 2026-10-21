# ============================================================
# MARÉE — simulation Python (orchestrateur, agents, RAG, metrics)
# ============================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Paquets système minimaux (librdkafka fourni par confluent-kafka wheel)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# Dépendances (pyproject ; pas de lockfile versionné)
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
    "aiokafka>=0.10,<0.12" \
    "websockets>=12,<14" \
    "httpx>=0.27" \
    "pydantic>=2.7,<3" \
    "pyyaml>=6.0" \
    "click>=8.1" \
    "faiss-cpu>=1.8" \
    "numpy>=1.26" \
    "pytest>=8.0" \
    "pytest-asyncio>=0.23"

# Code applicatif
COPY src/ ./src/
COPY config/ ./config/

RUN python -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('src').rglob('*.py')]"

EXPOSE 8000 8765

# Défaut : lancer un run (--config passé par le compose)
CMD ["python", "-m", "src.cli", "run", "--config", "/config/simulation.yaml"]