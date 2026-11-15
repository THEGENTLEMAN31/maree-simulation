"""sim.replay — le rejeu v3 (E3) : reconstruire un run depuis le journal seul.

Le journal JSONL est la **source de vérité** (convention n°1). Rejouer un
run = relire l'en-tête + le **flux complet d'événements** (décisions,
positions, évacuations, signaux) enregistré par ``write_run``, et vérifier
que son empreinte est stable — **sans un seul appel LLM** (le lecteur
n'importe aucun port de chat). C'est le filet de sécurité de la démo.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class ReplayResult:
    run_id: str
    header: dict[str, object]
    events: list[dict[str, object]]
    digest: str

    @property
    def n_decisions(self) -> int:
        return sum(1 for e in self.events if e.get("type") == "agent.decision")

    def summarize(self) -> dict[str, object]:
        """Indicateurs recalculés depuis le flux (B2/F6) — sans rejouer le monde."""
        actions = Counter(
            cast("dict[str, object]", e["data"]).get("action")
            for e in self.events if e.get("type") == "agent.decision"
        )
        n_evac = sum(1 for e in self.events if e.get("type") == "agent.evacuated")
        last_snap = next(
            (e for e in reversed(self.events) if e.get("type") == "world.snapshot"), None
        )
        agents_data = cast("dict[str, object]", last_snap["data"]) if last_snap else {}
        positions = len(cast("list[object]", agents_data.get("agents", []))) if agents_data else 0
        lags = [
            int(cast("Any", e["t_trait"])) - int(cast("Any", e["t_prod"]))
            for e in self.events if e.get("type") == "agent.decision"
        ]
        return {
            "n_decisions": self.n_decisions,
            "n_evacuated": n_evac,
            "agents_restants": positions,
            "actions": {str(k): v for k, v in actions.items()},
            "lag_max": max(lags, default=0),
        }


def events_digest(events: list[dict[str, object]]) -> str:
    payload = json.dumps(events, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def replay_jsonl(path: Path) -> ReplayResult:
    """Relit un journal de run (décisions + événements) et son empreinte."""
    header: dict[str, object] = {}
    events: list[dict[str, object]] = []
    run_id = path.stem
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            kind = record.get("kind") or record.get("type")
            if kind == "header":
                header = record
                run_id = str(record.get("run_id", run_id))
            elif kind == "event":
                record.pop("kind", None)   # garde "type" = type d'événement
                events.append(record)
            elif kind == "decision":       # ancien format décisions-only
                record.pop("type", None)
                events.append(record)
    return ReplayResult(run_id=run_id, header=header, events=events,
                        digest=events_digest(events))


__all__ = ["ReplayResult", "events_digest", "replay_jsonl"]