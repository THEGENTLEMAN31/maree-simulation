"""P0 — réalisme : la distance au danger module la menace, et le déplacement est une caractéristique.

- plus l'agent est proche du danger, plus la menace monte (proximité) ;
- deux agents différents (mobility/âge) ont des vitesses différentes ;
- la fatigue et la densité réduisent la vitesse réelle (pas de téléportation).
"""

from __future__ import annotations

from maree.v3.agents.agent import make_agent
from maree.v3.agents.appraisal import appraise
from maree.v3.agents.perception import Perception
from maree.v3.agents.state import State
from maree.v3.core.ids import ZoneId


def _perc(distance: float | None, tick: int = 10) -> Perception:
    return Perception(
        tick=tick,
        zone=ZoneId("z1"),
        state=State(),
        distance_to_danger=distance,
        seen_agents=(),
        exits_visible=frozenset(),
    )


def _menace(agent, perc: Perception) -> float:
    ap = appraise(perception=perc, traits=agent.traits,
                  knowledge=agent.knowledge, social=agent.social, name=agent.name)
    return ap.menace


def test_la_proximite_mesure_la_distance() -> None:
    assert _perc(0).danger_proximity == 1.0
    assert _perc(20).danger_proximity == 0.5
    assert _perc(50).danger_proximity == 0.0
    assert _perc(None).danger_proximity == 0.0


def test_etre_plus_pres_du_danger_eleve_la_menace() -> None:
    agent = make_agent(1, archetype="visiteur", known_exits=frozenset({"A"}))
    loin = _menace(agent, _perc(45))
    proche = _menace(agent, _perc(5))
    assert proche > loin
    # à 5 m du danger, la menace est nettement sensible
    assert proche > 0.3


def test_loin_du_danger_on_reagit_moins() -> None:
    agent = make_agent(1, archetype="habitue", known_exits=frozenset({"A"}))
    # très loin (proximité 0) et sans autre signal, avoir la distance seule ne déclenche rien
    assert _menace(agent, _perc(45)) == 0.0


def test_chaque_agent_a_sa_vitesse_deplacement() -> None:
    lent = make_agent(1, archetype="famille", known_exits=frozenset({"A"}))
    rapide = make_agent(2, archetype="agent_de_securite", known_exits=frozenset({"A"}))
    assert rapide.speed_max > lent.speed_max
    assert 0.5 <= lent.speed_max <= 1.4
    assert 0.5 <= rapide.speed_max <= 1.4


def test_la_fatigue_et_la_foule_ralentissent() -> None:
    agent = make_agent(1, archetype="visiteur", known_exits=frozenset({"A"}))
    v0 = agent.current_speed()
    # fatigué
    agent.state = State(fatigue=0.8)
    v1 = agent.current_speed()
    assert v1 < v0
    # fatigué + foule dense
    agent.state = State(fatigue=0.8, crowding=4.0)
    v2 = agent.current_speed()
    assert v2 <= v1