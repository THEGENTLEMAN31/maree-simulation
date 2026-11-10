"""storage — persistance, requêtes, migrations.

Aucune règle métier. La matrice de stockage : Postgres + pgvector,
Parquet / DuckDB, objets, bus Redpanda. Voir `docs/v3/architecture.md` §3.
"""

from __future__ import annotations

RESPONSIBILITY = "persistance, requêtes, migrations (matrice de stockage)"

__all__ = ["RESPONSIBILITY"]