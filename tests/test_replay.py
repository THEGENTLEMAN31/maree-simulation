"""Rejeu E3 : reconstruire un run depuis le journal seul.

Aucun LLM, aucun Kafka : uniquement le JSONL. C'est ce qui rend une
expérience auditable après coup.
"""

from __future__ import annotations

from pathlib import Path

from maree.adapters.journal.jsonl import JsonlJournal
from maree.domain.events import Event, EventType
from maree.engine.replay import check_decisions, indicators_hash, replay

RUN = "run_test_replay"


def _event(seq: int, type_: EventType, data: dict, tick: int = 0) -> Event:
    return Event(
        seq=seq,
        run_id=RUN,
        type=type_,
        t_prod=tick,
        t_trait=tick,
        t_real=0.001 * seq,
        data=data,
    )


def _llm_decision(seq: int, raw: str, kind: str, target: str) -> Event:
    return _event(
        seq,
        EventType.DECISION,
        {
            "agent_id": "A01",
            "kind": "llm",
            "intention": {"kind": kind, "target": target, "reason": "test", "tick": 10},
            "llm": {"prompt": "…", "seed": 42, "raw_output": raw, "ok": True},
        },
        tick=10,
    )


def _write(path: Path, events: list[Event]) -> JsonlJournal:
    journal = JsonlJournal(path)
    for event in events:
        journal.append(event)
    return journal


def test_run_complet_est_rejouable(tmp_path: Path) -> None:
    events = [
        _event(1, EventType.RUN_STARTED, {"seed": 0}),
        _llm_decision(2, '{"action": "go_exit", "target": "A"}', "go_exit", "A"),
        _event(3, EventType.INDICATORS, {"tick": 1, "I1_consensus": 0.8}, tick=1),
        _event(4, EventType.NARRATIVE, {"text": "douze personnes", "valid": True}, tick=1),
        _event(5, EventType.RUN_ENDED, {"ticks": 1}),
    ]
    journal = _write(tmp_path, events)
    result = replay(RUN, journal)

    assert result.ok, result.problems
    assert result.events == 5
    assert result.decisions.total == 1
    assert result.decisions.reconstructed == 1
    assert result.decisions.matching == 1
    assert result.decisions.trace_complete == 1
    assert result.narratives == 1
    assert result.narratives_valid == 1


def test_hash_des_indicateurs_est_stable(tmp_path: Path) -> None:
    events = [
        _event(1, EventType.RUN_STARTED, {}),
        _event(2, EventType.INDICATORS, {"tick": 1, "I1_consensus": 0.5}),
        _event(3, EventType.RUN_ENDED, {}),
    ]
    journal = _write(tmp_path / "a", events)
    assert indicators_hash(events) == indicators_hash(journal.read(RUN))
    assert indicators_hash(events) == indicators_hash(list(reversed(events)))


def test_divergence_entre_sortie_brute_et_intention(tmp_path: Path) -> None:
    """Le modèle a dit B, l'intention appliquée dit A : c'est un incident."""
    events = [
        _event(1, EventType.RUN_STARTED, {}),
        _llm_decision(2, '{"action": "go_exit", "target": "B"}', "go_exit", "A"),
        _event(3, EventType.RUN_ENDED, {}),
    ]
    result = replay(RUN, _write(tmp_path, events))
    assert result.decisions.matching == 0
    assert result.decisions.mismatches
    assert not result.ok


def test_sortie_non_parsable_est_signalee(tmp_path: Path) -> None:
    events = [
        _event(1, EventType.RUN_STARTED, {}),
        _llm_decision(2, "je préfère la sortie A", "go_exit", "A"),
        _event(3, EventType.RUN_ENDED, {}),
    ]
    result = replay(RUN, _write(tmp_path, events))
    assert result.decisions.reconstructed == 0
    assert not result.ok


def test_journal_incomplet_est_refuse(tmp_path: Path) -> None:
    journal = _write(tmp_path, [_event(1, EventType.RUN_STARTED, {})])
    result = replay(RUN, journal)
    assert not result.ok
    assert any("run.ended" in p for p in result.problems)


def test_run_inconnu(tmp_path: Path) -> None:
    result = replay("run_absent", JsonlJournal(tmp_path))
    assert not result.ok
    assert any("journal vide" in p for p in result.problems)


def test_last_seq_et_liste_des_runs(tmp_path: Path) -> None:
    journal = _write(tmp_path, [_event(1, EventType.RUN_STARTED, {})])
    assert journal.last_seq(RUN) == 1
    assert journal.runs() == [RUN]


def test_decision_sans_trace_nest_pas_reconstructible() -> None:
    events = [
        _event(1, EventType.DECISION, {"kind": "llm", "intention": {"kind": "go_exit"}})
    ]
    check = check_decisions(events)
    assert check.total == 1
    assert check.trace_complete == 0
    assert check.reconstructed == 0
