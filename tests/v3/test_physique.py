"""P3 — le mouvement réel (JuPedSim) : déplacement, domaine, évacuation, déterminisme.

- les agents **se déplacent** (position qui change), sans téléportation ;
- ils restent dans le polygone marchable (on ne traverse pas les murs) ;
- atteindre l'issue = **évacué** (fait physique) ;
- même graine ⇒ mêmes positions (déterminisme) ;
- câblé dans l'orchestrateur : décision → intention → physique → snapshot.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

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

# --- correctif 2026-11-17 : les intentions qui ne sortent pas -----------------

def test_rester_reste_sur_place() -> None:
    """« Rester » ne déplace pas : l'ancien code envoyait l'agent au coin."""
    phys = _physics(_small_world())
    phys.spawn(1, (5.0, 5.0), desired_speed=1.2)
    phys.set_intention(1, Target.stay())
    phys.advance(200)  # 10 s simulées
    x, y = phys.positions()[1]
    assert abs(x - 5.0) < 0.3 and abs(y - 5.0) < 0.3, (x, y)


def test_aller_vers_un_point_y_va() -> None:
    """``Target.at`` est une intention réelle (le champ ``point`` servait à rien)."""
    phys = _physics(_small_world())
    phys.spawn(1, (10.0, 5.0), desired_speed=1.3)
    phys.set_intention(1, Target.at((10.0, 15.0)))
    phys.advance(200)
    _, y = phys.positions()[1]
    assert y > 12.0


def test_le_placement_ne_fait_pas_de_grappes() -> None:
    """Soixante agents ne se partagent plus six points d'artefact."""
    world = _small_world()
    sim = Simulation(seed=3).build(world)
    sim.spawn("visiteur", 20, frozenset({"A"}))
    pts = [i.point for i in sim.scene.instances.values()]
    assert len(set(pts)) == len(pts)
    for i, a in enumerate(pts):
        for b in pts[i + 1:]:
            assert math.dist(a, b) >= 0.44


class _Recorder:
    """Port physique minimal : enregistre les intentions, ne bouge personne."""

    def __init__(self) -> None:
        self.intentions: dict[int, Target] = {}

    def spawn(self, tag: int, position, desired_speed: float) -> None:
        return None

    def set_intention(self, tag: int, target: Target) -> None:
        self.intentions[tag] = target

    def advance(self, steps: int = 1) -> None:
        return None

    def positions(self) -> dict[int, tuple[float, float]]:
        return {1: (5.0, 5.0)}

    def evacuated(self) -> set[int]:
        return set()

    def close(self) -> None:
        return None


def test_chaque_action_a_une_intention_physique() -> None:
    """Évacuer → sortie ; chercher → point ; le reste tient la position."""
    from maree.v3.agents.appraisal import Action
    from maree.v3.agents.policy import Decision

    world = _small_world()
    phys = _Recorder()
    sim = Simulation(seed=1, physics=phys).build(world)
    sim.spawn("habitue", 1, frozenset({"A"}))
    agent = next(iter(sim.scene.instances.values())).agent

    def target(action: Action, tgt: str | None = None) -> Target:
        return sim._target_for(agent, Decision(action=action, tick=0, target=tgt))

    evac = target(Action.EVACUER, "A")
    assert (evac.kind, evac.exit_id) == ("exit", "A")

    assert target(Action.RESTER).kind == "stay"
    assert target(Action.SUIVRE).kind == "stay"

    search = target(Action.CHERCHER)
    assert search.kind == "point" and search.point is not None
    assert math.dist(search.point, (5.0, 5.0)) == pytest.approx(3.0, abs=1e-6)

    kin = target(Action.CHERCHER_PROCHE, agent.name)
    assert kin.kind == "point" and kin.point == (5.0, 5.0)
