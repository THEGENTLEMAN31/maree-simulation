"""P3 — le temps : sync (barrière) vs async (cadence), t_prod/t_trait, cohérence (C4/C3/C6).

- en SYNC, chaque décision est appliquée au tick où elle est perçue (lag = 0) ;
- en ASYNC, la décision est **appliquée plus tard** (t_trait > t_prod, lag > 0) :
  chacun réfléchit à son rythme, le monde continue ;
- aucune violation de cohérence temporelle (C6) dans les deux modes.
"""

from __future__ import annotations

from maree.v3.core.ports import ExecutionMode, PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.world.sample import sample_worldspec


def _sim(mode: ExecutionMode, policy=PolicyName.HYBRID, bus=None) -> Simulation:
    sim = Simulation(seed=3, policy=policy, bus=bus, mode=mode).build(sample_worldspec())
    sim.spawn("visiteur", 2, frozenset({"A", "B"}))
    sim.run([Timestep(1), Timestep(10, smoke=True)])
    return sim


def test_en_sync_pas_de_lag() -> None:
    sim = _sim(ExecutionMode.SYNC)
    assert sim.log.rows
    assert all(r.lag == 0 for r in sim.log.rows)
    assert sim.violations == 0


def test_en_async_le_monde_nattend_pas() -> None:
    sim = _sim(ExecutionMode.ASYNC)
    # au moins une décision appliquée plus tard que sa perception (lag > 0)
    assert any(r.lag > 0 for r in sim.log.rows)
    assert sim.violations == 0              # cohérence temporelle tenue


def test_les_enveloppes_portent_la_chronologie() -> None:
    bus = MemoryBus()
    _sim(ExecutionMode.ASYNC, bus=bus)
    decs = bus.published("agent.decision")
    assert decs
    assert any(e.t_prod != e.t_trait for e in decs)      # C3 : t_prod ≠ t_trait
    assert all(e.t_prod <= e.t_trait for e in decs)      # jamais d'info future


def test_le_mode_selectionnable_au_lancement() -> None:
    for mode in ExecutionMode:
        sim = _sim(mode)   # pas d'exception, les deux modes tournent
        assert sim.log.rows