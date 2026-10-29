"""Rejeu (E3) — reconstruire un run depuis le journal seul.

Le journal doit contenir assez d'information pour :

  1. reconstruire chaque décision LLM (prompt, graine, sortie brute) et
     vérifier que l'intention appliquée est bien celle que le modèle a
     produite ;
  2. recalculer les indicateurs et retrouver exactement les mêmes valeurs ;
  3. réafficher le récit du chroniqueur sans rappeler le modèle.

Aucun appel réseau, aucun LLM, aucun Kafka : uniquement le JSONL.
C'est ce qui rend une expérience auditable — et c'est la partie que la
v1 avait fini par réussir, on la conserve à l'identique dans l'esprit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from maree.agents.parsing import parse_decision
from maree.domain.events import Event, EventType
from maree.domain.ids import RunId
from maree.ports import JournalPort


@dataclass(frozen=True, slots=True)
class DecisionCheck:
    total: int
    trace_complete: int
    reconstructed: int
    matching: int
    #: Décisions où le modèle a été appelé mais où les règles ont tranché.
    #: Ce n'est pas une divergence : c'est un repli journalisé.
    fallbacks: int = 0
    mismatches: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class ReplayResult:
    run_id: RunId
    events: int
    indicators_hash: str
    decisions: DecisionCheck
    narratives: int
    narratives_valid: int
    indicator_drift: float = 0.0
    problems: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.problems


def indicators_hash(events: list[Event]) -> str:
    """Empreinte de la série d'indicateurs : deux runs identiques => même hash."""
    series = [e.data for e in events if e.type is EventType.INDICATORS]
    payload = json.dumps(series, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


#: Actions dont la cible est effacée par la validation (graph._to_intention).
#: Ce n'est pas une divergence : c'est une normalisation documentée, et le
#: rejeu doit la connaître pour ne pas crier au loup.
_TARGETLESS = {"stay", "search"}


def _is_normalisation(parsed: dict, applied: dict) -> bool:
    """`applied` est-il le résultat légitime de `parsed` après validation ?"""
    action = str(parsed.get("action"))
    kind = str(applied.get("kind"))
    target = parsed.get("target")
    kept = applied.get("target")
    if action == kind:
        if target == kept:
            return True
        # `stay` et `search` perdent leur cible ; `"null"` (la chaîne) aussi.
        return kept is None and (action in _TARGETLESS or str(target).lower() == "null")
    # « follow la sortie C » est lu comme « go_exit C ».
    return action == "follow" and kind == "go_exit" and target == kept


def check_decisions(events: list[Event]) -> DecisionCheck:
    """Re-parse la sortie brute et vérifie que l'intention appliquée en découle.

    Deux contrôles distincts, parce qu'ils ne prouvent pas la même chose :

      1. `parse_decision(raw_output)` redonne le `parsed` journalisé — la
         lecture du modèle est reproductible ;
      2. `parsed` mène à `intention` par les seules normalisations connues
         (`stay`/`search` sans cible, `follow <sortie>` lu `go_exit`) — la
         validation ne réécrit pas la décision en douce.

    Confondre les deux faisait échouer le rejeu sur 20 décisions sur 49 :
    elles étaient *normalisées*, pas divergentes.
    """
    decisions = [
        e for e in events if e.type is EventType.DECISION and e.data.get("kind") == "llm"
    ]
    complete = reconstructed = matching = normalised = fallbacks = 0
    mismatches: list[dict[str, object]] = []
    for event in decisions:
        trace = event.data.get("llm") or {}
        raw = trace.get("raw_output")
        if raw is not None and trace.get("prompt") is not None and trace.get("seed") is not None:
            complete += 1
        parsed = parse_decision(raw or "")
        if parsed is None:
            mismatches.append({"seq": event.seq, "reason": "sortie non parsable"})
            continue
        reconstructed += 1
        recorded = trace.get("parsed")
        if recorded is not None and recorded != parsed:
            mismatches.append(
                {
                    "seq": event.seq,
                    "agent": event.data.get("agent_id"),
                    "reason": "re-parse différent du parse journalisé",
                    "now": parsed,
                    "recorded": recorded,
                }
            )
            continue
        applied = event.data.get("intention") or {}
        if trace.get("fallback"):
            # Le modèle a répondu, mais sa sortie a été rejetée : les règles
            # ont décidé. Le journal le dit (`fallback: true`) ; ce n'est une
            # divergence que si la sortie était pourtant utilisable.
            if _is_normalisation(parsed, applied):
                mismatches.append(
                    {
                        "seq": event.seq,
                        "agent": event.data.get("agent_id"),
                        "reason": "repli annoncé sur une sortie valide",
                        "parsed": parsed,
                        "applied": applied,
                    }
                )
            else:
                matching += 1
                fallbacks += 1
            continue
        if _is_normalisation(parsed, applied):
            matching += 1
            if parsed.get("target") != applied.get("target") or parsed.get("action") != applied.get("kind"):
                normalised += 1
        else:
            mismatches.append(
                {
                    "seq": event.seq,
                    "agent": event.data.get("agent_id"),
                    "parsed": {"action": parsed.get("action"), "target": parsed.get("target")},
                    "applied": {"action": applied.get("kind"), "target": applied.get("target")},
                }
            )
    return DecisionCheck(
        total=len(decisions),
        trace_complete=complete,
        reconstructed=reconstructed,
        matching=matching,
        fallbacks=fallbacks,
        mismatches=tuple(mismatches[:20]),
    )


def check_narratives(events: list[Event]) -> tuple[int, int]:
    narratives = [e for e in events if e.type is EventType.NARRATIVE]
    valid = sum(1 for e in narratives if e.data.get("valid"))
    return len(narratives), valid


def replay(run_id: RunId, journal: JournalPort) -> ReplayResult:
    events = sorted(journal.read(run_id), key=lambda e: e.seq)
    problems: list[str] = []
    if not events:
        problems.append("journal vide : run inconnu")
    if not any(e.type is EventType.RUN_STARTED for e in events):
        problems.append("événement run.started absent : journal incomplet")
    if not any(e.type is EventType.RUN_ENDED for e in events):
        problems.append("événement run.ended absent : run interrompu")

    decisions = check_decisions(events)
    if decisions.total and decisions.reconstructed < decisions.total:
        problems.append(
            f"{decisions.total - decisions.reconstructed} décision(s) non reconstructible(s)"
        )
    if decisions.mismatches:
        problems.append(f"{len(decisions.mismatches)} divergence(s) décision/application")

    n_narr, n_valid = check_narratives(events)
    return ReplayResult(
        run_id=run_id,
        events=len(events),
        indicators_hash=indicators_hash(events),
        decisions=decisions,
        narratives=n_narr,
        narratives_valid=n_valid,
        problems=tuple(problems),
    )


def narrate_from_journal(run_id: RunId, journal: JournalPort) -> list[dict[str, object]]:
    """Réaffiche le récit stocké — sans rappeler le modèle (E3)."""
    return [
        {"tick": e.t_prod, "text": e.data.get("text"), "valid": e.data.get("valid")}
        for e in sorted(journal.read(run_id), key=lambda e: e.seq)
        if e.type is EventType.NARRATIVE
    ]
