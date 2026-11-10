"""sim.journal — le journal append-only d'un run (convention n°1 v3).

Le journal est la **source de vérité** : il porte la config (monde, graine,
politique) et chaque décision, pour qu'un run soit rejouable et auditable.
Format JSONL léger et indépendant — rien à monter (pas de base). Un journal
plus riche (Parquet/DuckDB) pourra le remplacer sans changer la forme.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from maree.v3.core.ports import PolicyName
from maree.v3.sim.orchestrator import RunLog
from maree.v3.world.worldspec import WorldSpec


def world_hash(world: WorldSpec) -> str:
    """Hash déterministe du monde (identité de run : monde + graine + politique)."""
    payload = json.dumps(asdict(world), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def run_header(
    run_id: str,
    world: WorldSpec,
    seed: int,
    policy: PolicyName,
) -> dict[str, object]:
    meta = asdict(world)
    return {
        "run_id": run_id,
        "world": world.id,
        "world_hash": world_hash(world),
        "seed": seed,
        "policy": policy.value,
        "meta": meta,
    }


def write_jsonl(
    path: Path,
    header: dict[str, object],
    log: RunLog,
) -> Path:
    """Écrit l'en-tête puis une ligne JSON par décision (append-only)."""
    with path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "header", **header}, ensure_ascii=False) + "\n")
        for row in log.rows:
            fh.write(json.dumps({"type": "decision", **asdict(row)}, ensure_ascii=False) + "\n")
    return path


__all__ = ["run_header", "world_hash", "write_jsonl"]