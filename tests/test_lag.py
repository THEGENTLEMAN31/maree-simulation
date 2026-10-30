"""C7 — le décalage entre le monde, la cognition et la mesure.

Un test sur des événements fabriqués, pas sur un run : ce qui est vérifié
ici est la **lecture** du journal, pas le moteur. Si la lecture est fausse,
toutes les mesures de campagne le sont aussi.
"""

from __future__ import annotations

from maree.domain.events import Event, EventType
from maree.metrics.lag import lags, summary


def _ev(
    seq: int,
    type_: EventType,
    *,
    t_prod: int,
    t_trait: int | None = None,
    cause: Event | None = None,
    data: dict | None = None,
) -> Event:
    return Event(
        seq=seq,
        run_id="test",
        type=type_,
        t_prod=t_prod,
        t_trait=t_prod if t_trait is None else t_trait,
        t_real=float(seq),
        causation_id=cause.id if cause else None,
        correlation_id=(cause.correlation_id or cause.id) if cause else None,
        data=data or {},
    )


def _smoke_then_crowd() -> list[Event]:
    smoke = _ev(1, EventType.WORLD_SMOKE, t_prod=5, data={"radius": 15.0})
    # Un agent à règles réagit au tick même : « le monde a été perçu ».
    rules = _ev(
        2,
        EventType.DECISION,
        t_prod=5,
        cause=smoke,
        data={"agent_id": "A01", "kind": "rules"},
    )
    # Un agent LLM met sept ticks : c'est la latence réelle.
    llm = _ev(
        3,
        EventType.DECISION,
        t_prod=12,
        t_trait=12,
        cause=smoke,
        data={"agent_id": "A02", "kind": "llm"},
    )
    blocks = [
        _ev(4, EventType.INDICATORS, t_prod=5, data={"I2_entropy": 0.5, "I3_evacuated": 0.0}),
        _ev(5, EventType.INDICATORS, t_prod=6, data={"I2_entropy": 0.5, "I3_evacuated": 0.0}),
        _ev(6, EventType.INDICATORS, t_prod=7, data={"I2_entropy": 0.7, "I3_evacuated": 0.0}),
    ]
    return [smoke, rules, llm, *blocks]


def test_c7_trois_decalages_distincts() -> None:
    """Percevoir, comprendre et mesurer ne sont pas le même instant."""
    found = lags(_smoke_then_crowd())
    assert len(found) == 1
    lag = found[0]
    assert lag.tick == 5
    # Le monde est perçu tout de suite (agent à règles).
    assert lag.effect_ticks == 0
    # Il est compris quand le LLM a répondu.
    assert lag.llm_ticks == 7
    # Il est mesuré quand l'agrégat bouge — ici I2 à t7.
    assert lag.indicator_ticks == 2
    assert lag.agents == 2


def test_c7_un_evenement_jamais_mesure_est_un_resultat() -> None:
    """Un indicateur qui ne bouge pas n'est pas une mesure manquante."""
    smoke = _ev(1, EventType.WORLD_SMOKE, t_prod=5, data={})
    flat = [
        _ev(2, EventType.INDICATORS, t_prod=5, data={"I2_entropy": 0.5, "I3_evacuated": 0.0}),
        _ev(3, EventType.INDICATORS, t_prod=6, data={"I2_entropy": 0.5, "I3_evacuated": 0.0}),
    ]
    found = lags([smoke, *flat])
    assert found[0].indicator_ticks is None
    assert summary(found)["never_measured"] == 1


def test_c7_l_arbre_causal_ne_confond_pas_deux_evenements() -> None:
    """Deux fumées, deux chaînes : la corrélation est la racine, pas le type."""
    first = _ev(1, EventType.WORLD_SMOKE, t_prod=5, data={})
    second = _ev(2, EventType.WORLD_SMOKE, t_prod=20, data={})
    early = _ev(
        3,
        EventType.DECISION,
        t_prod=5,
        cause=first,
        data={"agent_id": "A01", "kind": "rules"},
    )
    late = _ev(
        4,
        EventType.DECISION,
        t_prod=21,
        cause=second,
        data={"agent_id": "A01", "kind": "rules"},
    )
    found = lags([first, second, early, late])
    assert [lag.effect_ticks for lag in found] == [0, 1]
    assert found[0].event_id == first.id
    assert found[1].event_id == second.id
