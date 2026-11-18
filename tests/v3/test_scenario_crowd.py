"""G2 — le monde macro est calibré, et le goulot est mesuré, pas supposé.

Ce que l'on prouve (aucun GPU) :

- ``hall_3`` (120 × 80 m) ne fait **aucun** goulot à 60 agents : la densité
  reste à 0,000 pers/m². C'est la raison d'être de ``crowd_hall`` — sans cela
  on aurait mesuré la marche, pas l'évacuation ;
- dans ``crowd_hall`` (22 × 16 m, deux issues de 1,2 m), le bras ``règles``
  produit un pic de densité entre 0,8 et 1,6 pers/m², **pas au spawn** mais
  en marche (t6–t7), et la salle se vide complètement ;
- le vidage dure 20–30 s de temps simulé, donc plusieurs points de mesure :
  c'est pour cela que le tick de ce scénario vaut 2 s et non 10 s ;
- la variante « moitié croit A bloquée, moitié B » (C6) se joue et clive le
  consensus (I1 < 1) sans empêcher la sortie ;
- le run est déterministe à graine égale.
"""

from __future__ import annotations

import numpy as np

from maree.v3.adapters.physics import JuPedSimCrowd
from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.verify import scenario_crowd as sc
from maree.v3.verify.indicators import summarise
from maree.v3.world.generate import build
from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.simartifact import build_sim_artifact


def test_le_monde_calibre_a_deux_issues_de_1_2_m() -> None:
    w = sc.world()
    exits = w.level("L0").exits
    assert [e.id for e in exits] == ["A", "B"]
    assert all(abs(e.width - 1.2) < 1e-9 for e in exits)
    assert w.level("L0").outline  # la salle existe et reste un polygone


def test_hall_3_ne_fait_aucun_goulot_a_60_agents() -> None:
    """La justification du chantier : un grand hall ne contraint personne."""
    world = build("hall_3")
    graph = NavigationGraph(world)
    art = build_sim_artifact(
        world, graph, np.random.default_rng(1), spawn_per_space=6
    )
    level = art.levels["L0"]
    physics = JuPedSimCrowd(
        walkable=level.walkable,
        exits={e.id: e.segment for e in world.level("L0").exits},
        seed=1,
    )
    bus = MemoryBus()
    sim = Simulation(
        seed=1, policy=PolicyName.RULES, bus=bus, physics=physics,
        physics_steps_per_tick=sc.STEPS_PER_TICK, tick_seconds=sc.TICK_SECONDS,
    ).build(world)
    sim.spawn("visiteur", 60, frozenset({"A", "B", "C"}))
    sim.run([Timestep(1, smoke=True), *[Timestep(t) for t in range(2, 11)]])
    summary = summarise([e.data for e in bus.published("indicator.crowd")])
    assert summary["I5_max_density"] < 0.2      # mesuré 0,000 pers/m²


def test_le_goulot_est_visible_et_pas_au_spawn() -> None:
    result = sc.measure(seed=1)
    summary = result["summary"]
    assert 0.8 <= float(summary["I5_max_density"]) <= 1.6
    assert result["peak_tick"] >= 3            # la foule se forme en marchant
    assert result["peak_at_spawn"] is False
    assert float(summary["I3_evacuated"]) == 1.0
    assert result["evacuated"] == sc.N_AGENTS


def test_le_vidage_dure_assez_pour_plusieurs_points_de_mesure() -> None:
    result = sc.measure(seed=2)
    delay = float(result["summary"]["I7_delay_seconds"])
    assert 10.0 <= delay <= 40.0               # mesuré 22–24 s à tick de 2 s
    # au moins six ticks de mesure pendant l'évacuation
    assert len([s for s in result["series"]]) >= 10


def test_le_scenario_clive_les_croyances_sans_bloquer_la_sortie() -> None:
    result = sc.measure(seed=1, split=True)
    summary = result["summary"]
    # moitié « A bloquée », moitié « B bloquée » : le consensus n'est pas total.
    # Depuis C7 les agents se parlent, ce qui **remonte** l'accord (0,63 muet →
    # 0,81 avec parole, graine 1) : le seuil est donc « pas total », pas 0,8.
    assert float(summary["I1_consensus"]) < 1.0
    assert float(summary["I3_evacuated"]) == 1.0


def test_le_run_est_deterministe_a_graine_egale() -> None:
    a = sc.measure(seed=3)
    b = sc.measure(seed=3)
    assert a["summary"] == b["summary"]
    assert a["evacuated"] == b["evacuated"]
