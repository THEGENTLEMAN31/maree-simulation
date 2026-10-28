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

def _parse_raw_decision(text: str | None) -> dict | None:
    """Parse la sortie brute LLM sans appeler le modèle (E3)."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()[1:]
        cleaned = "\n".join(lines).strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        # Dernier objet JSON équilibré (Gemma peut entourer le JSON de texte).
        start = cleaned.find("{")
        while start != -1:
            depth = 0
            in_string = False
            for i in range(start, len(cleaned)):
                ch = cleaned[i]
                if ch == '"' and (i == 0 or cleaned[i - 1] != "\\"):
                    in_string = not in_string
                elif not in_string and ch in "{}":
                    depth += 1 if ch == "{" else -1
                    if depth == 0:
                        try:
                            value = json.loads(cleaned[start : i + 1])
                            return value if isinstance(value, dict) else None
                        except json.JSONDecodeError:
                            break
            start = cleaned.find("{", start + 1)
    return None


def reconstruct_decisions(run_id: str, log_dir: str | Path) -> dict:
    """E3 : reconstruit chaque décision LLM depuis le journal seul.

    Le journal doit contenir le prompt, la graine et la sortie brute. On
    re-parse la sortie brute et on compare l'action, la zone, la sortie et
    le message à ce que le moteur a réellement appliqué.
    """
    events = ReplayEngine.load(run_id, log_dir)
    decisions = [
        e for e in events
        if e.type == "agent.decision" and e.data.get("kind") == "llm"
    ]
    trace_complete = parsed = matching = 0
    mismatches: list[dict] = []
    for event in decisions:
        trace = event.data.get("llm") or {}
        raw = trace.get("raw_output")
        prompt = trace.get("prompt")
        seed = trace.get("seed")
        if raw is not None and prompt is not None and seed is not None:
            trace_complete += 1
        parsed_decision = _parse_raw_decision(raw)
        if parsed_decision is None:
            mismatches.append({
                "event_id": event.event_id,
                "reason": "raw_output_unparseable",
            })
            continue
        parsed += 1
        raw_action = parsed_decision.get("action", "stay")
        if raw_action not in {"move", "stay", "evacuate"}:
            raw_action = "stay"
        raw_target = parsed_decision.get("target_zone")
        raw_exit = parsed_decision.get("exit_choice")
        applied = event.data
        # Pour "stay", la zone cible n'est pas une information de décision :
        # le moteur la normalise sur la zone courante. On ne la compare donc
        # que pour un déplacement ou une évacuation.
        target_same = (
            raw_action == "stay"
            or (raw_target or None) == (applied.get("target_zone") or None)
        )
        exit_same = (raw_exit or None) == (applied.get("exit") or None)
        same = raw_action == applied.get("action") and target_same and exit_same
        applies_message = (
            (parsed_decision.get("message") or None)
            == (applied.get("message") or None)
        )
        if same and applies_message:
            matching += 1
        else:
            mismatches.append({
                "event_id": event.event_id,
                "raw": {
                    "action": raw_action,
                    "target_zone": raw_target,
                    "exit_choice": raw_exit,
                    "message": parsed_decision.get("message"),
                },
                "applied": {
                    "action": applied.get("action"),
                    "target_zone": applied.get("target_zone"),
                    "exit": applied.get("exit"),
                    "message": applied.get("message"),
                },
            })
    return {
        "run_id": run_id,
        "n_decisions": len(decisions),
        "trace_complete": trace_complete,
        "parsed": parsed,
        "matching": matching,
        "mismatches": mismatches,
    }
