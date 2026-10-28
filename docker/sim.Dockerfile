# ============================================================
# MARÉE v2 — image du moteur de simulation
#
# uv gère l'environnement (lockfile = décision 14). Aucun apt-get :
# toutes les dépendances sont des wheels (faiss-cpu, jupedsim, mesa).
# ============================================================
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

COPY --from=ghcr.io/astral-sh/uv:0.5.9 /uv /uvx /usr/local/bin/

WORKDIR /app

# 1) Dépendances seules : cette couche est mise en cache tant que
#    pyproject.toml et uv.lock ne changent pas.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

# 2) Code applicatif
COPY src ./src
COPY configs ./configs
COPY protos ./protos
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH"

RUN python -c "import maree; print('maree', maree.__version__)"

ENTRYPOINT ["maree"]
CMD ["--help"]
