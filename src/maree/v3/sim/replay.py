"""sim.replay — le rejeu v3 (E3) : reconstruire un run depuis le journal seul.

Le journal JSONL est la **source de vérité** (convention n°1). Rejouer un
run = relire l'en-tête + les décisions enregistrées et vérifier que leur
empreinte est identique — **sans aucun appel LLM ni broker**. C'est le
filet de sécurité de la démonstration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ReplayResult:
    run_id: str
    header: dict[str, object]
    decisions: list[dict[str, object]]
    digest: str

    @property
    def n_decisions(self) -> int:
        return len(self.decisions)


def decisions_digest(decisions: list[dict[str, object]]) -> str:
    payload = json.dumps(decisions, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def replay_jsonl(path: Path) -> ReplayResult:
    """Relit un journal de run et reconstruit ses décisions + l'empreinte."""
    header: dict[str, object] = {}
    decisions: list[dict[str, object]] = []
    run_id = path.stem
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("type") == "header":
                header = record
                run_id = str(record.get("run_id", run_id))
            elif record.get("type") == "decision":
                record.pop("type", None)
                decisions.append(record)
    return ReplayResult(
        run_id=run_id,
        header=header,
        decisions=decisions,
        digest=decisions_digest(decisions),
    )


__all__ = ["ReplayResult", "decisions_digest", "replay_jsonl"]