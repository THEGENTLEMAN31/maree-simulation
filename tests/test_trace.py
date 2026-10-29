"""B4 — la chaîne causale se remonte, et ne s'invente pas.

Un journal où `causation_id` est toujours nul ne permet pas de répondre à
« quel échange a fait basculer la foule ? ». Ces tests vérifient les deux
moitiés de l'exigence : les liens existent quand il y a une cause, et ils
restent vides quand il n'y en a pas (une décision périodique n'a pas de
parent).
"""

from __future__ import annotations

from maree.domain.events import Event, EventType
from maree.engine.trace import ancestors, describe, index, report, variation


def _event(seq: int, tick: int, type_: EventType, data: dict, parent: Event | None = None) -> Event:
    if parent is None:
        return Event(seq=seq, run_id="r", type=type_, t_prod=tick, t_trait=tick, t_real=0.0, data=data)
    return parent.child(seq=seq, type=type_, t_prod=tick, t_trait=tick, t_real=0.0, data=data)


def _chain() -> list[Event]:
    smoke = _event(1, 5, EventType.WORLD_SMOKE, {"position": [0, 0], "radius": 10})
    decision = _event(
        2,
        5,
        EventType.DECISION,
        {
            "agent_id": "A01",
            "trigger": "fumee_visible",
            "reason": "je sors",
            "intention": {"kind": "go_exit", "target": "B"},
        },
        smoke,
    )
    belief = _event(3, 5, EventType.BELIEF_UPDATED, {"agent_id": "A01", "beliefs": {"B": {"confidence": 0.8}}}, decision)
    sent = _event(4, 5, EventType.MESSAGE_SENT, {"from": "A01", "to": ["A02"], "content": "sors"}, decision)
    heard = _event(5, 5, EventType.MESSAGE_HEARD, {"agent_id": "A02", "from": "A01", "content": "sors"}, sent)
    return [smoke, decision, belief, sent, heard]


def test_la_chaine_remonte_de_la_cause_racine_a_l_effet() -> None:
    events = _chain()
    by_id = index(events)
    chain = ancestors(by_id, events[-1])
    assert [e.type for e in chain] == [
        EventType.WORLD_SMOKE,
        EventType.DECISION,
        EventType.MESSAGE_SENT,
        EventType.MESSAGE_HEARD,
    ]
    # `correlation_id` est la racine pour toute la chaîne.
    assert {e.correlation_id for e in events[1:]} == {events[0].id}
    assert events[0].causation_id is None


def test_une_decision_periodique_n_a_pas_de_parent() -> None:
    periodic = _event(
        9,
        12,
        EventType.DECISION,
        {"agent_id": "A03", "trigger": "periodique", "reason": "filet", "intention": {"kind": "stay"}},
    )
    assert periodic.causation_id is None
    assert ancestors(index([periodic]), periodic) == [periodic]


def test_describe_est_lisible_par_un_humain() -> None:
    events = _chain()
    assert "A01" in describe(events[1])
    assert "fumée" in describe(events[0])
    assert "A02 entend A01" in describe(events[-1])


def test_report_ignore_le_tick_degenere() -> None:
    """Le dernier tick (tout le monde sorti) n'est pas un basculement."""
    def ind(seq: int, tick: int, i1: float, evacuated: int) -> Event:
        return _event(
            seq,
            tick,
            EventType.INDICATORS,
            {"tick": tick, "I1_consensus": i1, "counts": {"agents": 10, "evacuated": evacuated}},
        )

    events = [ind(1, 1, 0.90, 0), ind(2, 2, 0.55, 0), ind(3, 3, 0.0, 10)]
    found = variation(events, "I1_consensus")
    assert found == (2, 0.90, 0.55)
    out = report(events, key="I1_consensus")
    assert out["found"] and out["tick"] == 2
