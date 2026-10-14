"""Journal d'événements (JSONL) et moteur de rejeu (E3, décisions 1-3).

- Le journal est la SOURCE DE VÉRITÉ : un run passé se rejoue à l'identique
  à partir des seules données enregistrées, sans nouvel appel LLM.
- Déterminisme : l'ordre des événements dans le journal est l'ordre canonique ;
  le rejeu produit la même visualisation et les mêmes indicateurs.
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .events import EventEnvelope


class RunLogger:
    """Écrit les événements d'un run dans un fichier JSONL (append-only).

    Décision 3 : attribue une séquence globale monotone (seq) à chaque
    événement — l'ordre canonique du journal, rejouable à l'identique.
    """

    def __init__(self, run_id: str, log_dir: str | Path = "/logs") -> None:
        self.run_id = run_id
        self.path = Path(log_dir) / f"{run_id}.events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")
        self._seq = 0

    def log(self, envelope: EventEnvelope) -> None:
        self._seq += 1
        envelope.seq = self._seq
        self._fh.write(envelope.model_dump_json() + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


@dataclass
class ReplayResult:
    run_id: str
    events: list[EventEnvelope]
    n_events: int
    indicator_hash: str


class ReplayEngine:
    """Rejoue un run depuis son journal (E3) — aucun appel LLM."""

    @staticmethod
    def load(run_id: str, log_dir: str | Path) -> list[EventEnvelope]:
        path = Path(log_dir) / f"{run_id}.events.jsonl"
        events: list[EventEnvelope] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(EventEnvelope.model_validate_json(line))
        return events

    @staticmethod
    def replay(run_id: str, log_dir: str | Path) -> ReplayResult:
        """Rejoue : re-lit le journal, vérifie l'ordre, calcule un hash des
        indicateurs pour attester l'identité du rejeu."""
        events = ReplayEngine.load(run_id, log_dir)
        # Vérifie l'ordre canonique (décision 3) : la séquence est monotone.
        for prev, cur in zip(events, events[1:]):
            if cur.seq < prev.seq:
                raise RuntimeError("ordre du journal non canonique")
        indicators = [
            e for e in events if e.type == "metrics.indicators"
        ]
        import hashlib

        h = hashlib.sha256()
        for ind in indicators:
            h.update(ind.data.get("tick", 0).to_bytes(8, "big"))
            h.update(str(ind.data.get("I1_consensus", "")).encode())
        return ReplayResult(
            run_id=run_id,
            events=events,
            n_events=len(events),
            indicator_hash=h.hexdigest()[:16],
        )