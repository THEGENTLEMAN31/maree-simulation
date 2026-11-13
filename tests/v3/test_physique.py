"""P3 — le mouvement réel (JuPedSim) : déplacement, domaine, évacuation, déterminisme.

- les agents **se déplacent** (position qui change), sans téléportation ;
- ils restent dans le polygone marchable (on ne traverse pas les murs) ;
- atteindre l'issue = **évacué** (fait physique) ;
- même graine ⇒ mêmes positions (déterminisme) ;
- câblé dans l'orchestrateur : décision → intention → physique → snapshot.
"""

from __future__ import annotations

import numpy as np

from maree.v3.adapters.physics import JuPedSimCrowd
from maree.v3.core.ports import PolicyName
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.sim.physics import Target
from maree.v3.world.generate import ExitSpec, hall_config
from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.simartifact import build_sim_artifact
from maree.v3.world.worldspec import WorldSpec, from_dict


def _small_world() -> WorldSpec:
    spec = hall_config(
        world_id="petit", width=20.0, height=20.0,
        exits=(ExitSpec("A", "top", 10.0, 6.0),),
    )
    return from_dict(spec)


def _physics(world: WorldSpec, seed: int = 1) -> JuPedSimCrowd:
    graph = NavigationGraph(world)
    art = build_sim_artifact(world, graph, np.random.default_rng(seed), spawn_per_space=3)
    lv0 = art.levels["L0"]
    exits = {e.id: e.segment for e in world.level("L0").exits}
    return JuPedSimCrowd(walkable=lv0.walkable, exits=exits, seed=seed)


def test_les_agents_se_deplacent_sans_teleportation() -> None:
    phys = _physics(_small_world())
    phys.spawn(1, (10.0, 5.0), desired_speed=1.2)
    p0 = phys.positions()[1]
    phys.set_intention(1, Target.exit("A"))
    phys.advance(60)                     # 3 s simulées
    p1 = phys.positions()[1]
    assert p1 != p0                      # il a bougé
    dy = p1[1] - p0[1]
    assert 0 < dy < 6                    # vers le haut, pas de téléportation


def test_on_ne_sort_jamais_du_domaine() -> None:
    phys = _physics(_small_world())
    phys.spawn(1, (10.0, 5.0), desired_speed=1.3)
    phys.set_intention(1, Target.exit("A"))
    for _ in range(12):
        phys.advance(60)
        x, y = phys.positions().get(1, (10.0, 5.0))
        assert -0.2 <= x <= 20.2
        assert -0.2 <= y <= 20.2


def test_atteindre_la_sortie_evacue() -> None:
    phys = _physics(_small_world(), seed=3)
    phys.spawn(1, (10.0, 3.0), desired_speed=1.4)
    phys.set_intention(1, Target.exit("A"))
    phys.advance(1000)                   # ~50 s simulées : franchit la sortie nord
    assert 1 in phys.evacuated()


def test_la_physique_est_deterministe() -> None:
    a = _physics(_small_world(), seed=7)
    b = _physics(_small_world(), seed=7)
    a.spawn(1, (10.0, 5.0), 1.2)
    b.spawn(1, (10.0, 5.0), 1.2)
    a.set_intention(1, Target.exit("A"))
    b.set_intention(1, Target.exit("A"))
    a.advance(80)
    b.advance(80)
    assert a.positions()[1] == b.positions()[1]


def test_lorchestrateur_fait_bouger_et_evacue() -> None:
    world = _small_world()
    phys = _physics(world, seed=2)
    sim = Simulation(seed=5, policy=PolicyName.RULES, physics=phys,
                     physics_steps_per_tick=120).build(world)
    sim.spawn("habitue", 1, frozenset({"A"}))
    sim.run([
        Timestep(0),
        Timestep(10, announcement="Veuillez évacuer par la sortie A"),
        Timestep(20),
        Timestep(40),
    ])
    # l'état des positions est diffusé (world.snapshot) et quelqu'un est sorti
    snapshots = sim.bus.published("world.snapshot")
    assert snapshots, "l'orchestrateur doit diffuser l'état des positions"
    assert len(sim._evacuated) >= 1
    evac = sim.bus.published("agent.evacuated")
    assert evac, "un agent physiquement sorti est annoncé"