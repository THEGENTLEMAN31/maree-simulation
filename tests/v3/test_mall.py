"""M-05 — le WorldSpec mall_aubel (deux niveaux) : chargeable et simulable.

Le monde réel du projet vise un bâtiment ; ce fichier vérifie que le plan
YAML multi-étages (``configs/world/mall_aubel.yaml``) est :

- **chargeable** par le code existant (``world.loader.load`` : YAML →
  ``from_dict`` → validation bloquante) — niveaux, espaces, portiques,
  sorties, liens verticaux ;
- **structurellement correct** : sans les liens verticaux, L0 et L1 ne
  communiquent plus (les escalators et l'escalier sont l'unique passage) ;
- **simulable** : un run court par niveau (JuPedSim) fait circuler les
  agents et les évacue par les sorties de leur niveau.

Limite documentée (monde-et-rendu §7) : la simulation v3.0 est mono-étage ;
la circulation inter-niveaux attend le ``LevelCoordinator`` (v3.1).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.world.loader import load
from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.simartifact import build_sim_artifact
from maree.v3.world.validate import validate
from maree.v3.world.worldspec import WorldSpec, from_dict

WORLD_PATH = Path("configs/world/mall_aubel.yaml")
TICK_SECONDS = 2.0
STEPS_PER_TICK = 40
N_TICKS = 15  # 15 × 2 s = 30 s de temps simulé


@pytest.fixture(scope="module")
def mall() -> WorldSpec:
    return load(WORLD_PATH)


# ------------------------------------------------------------------
# chargeable : le YAML passe la validation et porte la structure attendue
# ------------------------------------------------------------------
def test_le_yaml_mall_aubel_se_charge_et_passe_la_validation(mall: WorldSpec) -> None:
    assert mall.id == "mall_aubel"
    assert mall.schema == "3.0.0"
    assert [lv.id for lv in mall.levels] == ["L0", "L1"]

    print(f"\nmonde {mall.id} — {mall.schema}, unités {mall.units}, "
          f"repère {mall.coordinate_system}")
    for lv in mall.levels:
        print(f"  niveau {lv.id} ({lv.name}, élévation {lv.elevation} m, "
              f"{len(lv.holes)} trémie(s))")
        for s in lv.spaces:
            print(f"    espace   {s.id:<18} {s.kind}")
        for p in lv.portals:
            print(f"    portique {p.id:<18} {p.between[0]} ↔ {p.between[1]} "
                  f"({p.width} m)")
        for e in lv.exits:
            print(f"    sortie   {e.id:<18} {e.width} m → {e.to}")
    for v in mall.vertical:
        print(f"  vertical {v.id:<10} {v.kind:<9} {v.from_level}→{v.to_level} "
              f"({v.capacity_p_s} pers/s)")
    for h in mall.hazards:
        print(f"  danger {h.id} ({h.kind}) niveau {h.level} position {h.position}")

    # deux niveaux, la trémie sur la galerie
    l0, l1 = mall.levels
    assert l0.holes == ()
    assert len(l1.holes) == 1, "la trémie de l'atrium est un trou du contour L1"
    # des espaces et des portiques des deux côtés
    assert {s.kind for s in l0.spaces} == {"hall", "passage"}
    assert {s.kind for s in l1.spaces} == {"galerie"}
    assert len(l0.portals) >= 1 and len(l1.portals) >= 1
    # trois sorties d'évacuation de largeurs inégales au rez-de-chaussée
    assert {e.id: e.width for e in l0.exits} == {"A": 6.0, "B": 3.0, "C": 1.5}
    # deux escalators et un escalier
    kinds = sorted(v.kind for v in mall.vertical)
    assert kinds == ["escalator", "escalator", "stair"]
    # boutiques en obstacles, aux deux niveaux
    assert sum(1 for o in l0.obstacles if o.kind == "boutique") >= 3
    assert sum(1 for o in l1.obstacles if o.kind == "boutique") >= 3
    # les dangers déclarent une origine de fumée par niveau
    assert {h.level for h in mall.hazards} == {"L0", "L1"}


def test_la_trémie_est_hors_des_espaces_et_hors_du_marchable(mall: WorldSpec) -> None:
    l1 = mall.level("L1")
    hole = l1.holes[0]
    centre = (
        sum(p[0] for p in hole) / len(hole),
        sum(p[1] for p in hole) / len(hole),
    )
    g = NavigationGraph(mall)
    assert g.space_at(centre, "L1") is None, "la trémie n'appartient à aucun espace"
    art = build_sim_artifact(mall, g, np.random.default_rng(1))
    from shapely.geometry import Point as ShapelyPoint

    assert not art.levels["L1"].walkable.covers(ShapelyPoint(centre))
    # et le rez-de-chaussée, lui, se marche sous l'atrium
    assert art.levels["L0"].walkable.covers(ShapelyPoint(centre))


def test_les_liens_verticaux_sont_l_unique_passage_entre_niveaux(
    mall: WorldSpec,
) -> None:
    data = yaml.safe_load(WORLD_PATH.read_text(encoding="utf-8"))
    data["vertical"] = []
    errors = validate(from_dict(data))
    assert errors, "sans liens verticaux, la validation doit refuser le plan"
    joined = "\n".join(errors)
    assert "S_GALERIE_OUEST" in joined and "S_HALL" in joined, (
        "les deux niveaux doivent être mutuellement inatteignables"
    )
    # avec les liens, le même plan passe
    assert validate(mall) == []


def test_le_graphe_de_navigation_lit_les_deux_niveaux(mall: WorldSpec) -> None:
    g = NavigationGraph(mall)
    assert g.space_at((10, 10), "L0") == "S_HALL"
    assert g.space_at((40, 10), "L0") == "S_PASSAGE"
    assert g.space_at((10, 10), "L1") == "S_GALERIE_OUEST"
    assert g.space_at((40, 10), "L1") == "S_GALERIE_EST"
    # les sorties connues de chaque niveau
    assert g.reachable_exits((10, 10), "L0") == ["A", "B"]
    assert g.reachable_exits((40, 10), "L0") == ["C"]
    assert g.reachable_exits((10, 10), "L1") == ["D"]
    assert g.reachable_exits((40, 10), "L1") == ["E"]
    # les largeurs (capacités) suivent le plan
    assert g.capacity("A") == pytest.approx(6.0)
    assert g.capacity("C") == pytest.approx(1.5)
    # un étage inconnu ne renvoie rien
    assert g.space_at((10, 10), "L9") is None


def test_spawn_accepte_le_niveau_demande(mall: WorldSpec) -> None:
    bus = MemoryBus()
    sim = Simulation(seed=3, policy=PolicyName.RULES, bus=bus).build(mall)
    sim.spawn("visiteur", 2, frozenset({"D", "E"}), level="L1")
    levels = {
        sim.scene.navgraph.level_of_space(i.space_id)
        for i in sim.scene.instances.values()
    }
    assert levels == {"L1"}, "le spawn respecte l'étage demandé"
    # et le défaut reste le premier étage (comportement historique)
    sim2 = Simulation(seed=3, policy=PolicyName.RULES, bus=MemoryBus()).build(mall)
    sim2.spawn("visiteur", 2, frozenset({"A", "B", "C"}))
    levels2 = {
        sim2.scene.navgraph.level_of_space(i.space_id)
        for i in sim2.scene.instances.values()
    }
    assert levels2 == {"L0"}


# ------------------------------------------------------------------
# simulable : un run court par niveau fait circuler et évacuer
# ------------------------------------------------------------------
def _physics_for(mall: WorldSpec, level_id: str, seed: int):
    from maree.v3.adapters.physics import JuPedSimCrowd

    g = NavigationGraph(mall)
    art = build_sim_artifact(mall, g, np.random.default_rng(seed), spawn_per_space=6)
    la = art.levels[level_id]
    exits = {e.id: e.segment for e in mall.level(level_id).exits}
    return JuPedSimCrowd(walkable=la.walkable, exits=exits, seed=seed)


def _run_level(mall: WorldSpec, level_id: str, n_agents: int, seed: int):
    bus = MemoryBus()
    sim = Simulation(
        seed=seed,
        policy=PolicyName.RULES,
        bus=bus,
        run_id=f"mall_{level_id.lower()}_test",
        physics=_physics_for(mall, level_id, seed),
        physics_steps_per_tick=STEPS_PER_TICK,
        tick_seconds=TICK_SECONDS,
        speaking=False,
    ).build(mall)
    exits = tuple(e.id for e in mall.level(level_id).exits)
    sim.spawn("visiteur", n_agents, frozenset(exits), level=level_id)
    origin = next(h.position for h in mall.hazards if h.level == level_id)
    timeline = [
        Timestep(1, smoke=True, hazard_origin=origin),
        *[Timestep(t) for t in range(2, N_TICKS + 1)],
    ]
    sim.run(timeline)
    return sim, bus


def test_20_agents_circulent_30s_sur_le_rez_de_chaussee(mall: WorldSpec) -> None:
    sim, bus = _run_level(mall, "L0", 20, seed=1)
    # les agents ont perçu la fumée et décidé (un front = une décision)
    assert len(sim.log.rows) >= 20
    assert any(r.action.startswith("évacuer") for r in sim.log.rows)
    # le corps bouge : les deux espaces du niveau sont visités, des agents
    # atteignent une sortie en 30 s de temps simulé
    assert {i.space_id for i in sim.scene.instances.values()} == {"S_HALL", "S_PASSAGE"}
    assert len(sim._evacuated) >= 10, f"evacués : {len(sim._evacuated)}/20"
    # le journal est la source de vérité : fumée, décisions, snapshots
    types = {e.type for e in bus.envelopes}
    assert {"world.smoke", "agent.decision", "world.snapshot",
            "agent.evacuated"} <= types


def test_20_agents_circulent_30s_sur_la_galerie(mall: WorldSpec) -> None:
    sim, _bus = _run_level(mall, "L1", 20, seed=1)
    assert {i.space_id for i in sim.scene.instances.values()} == {
        "S_GALERIE_OUEST", "S_GALERIE_EST",
    }
    # la galerie est plus longue : une partie de la foule sort en 30 s
    assert len(sim._evacuated) >= 5, f"evacués : {len(sim._evacuated)}/20"
    assert any(r.action.startswith("évacuer") for r in sim.log.rows)


def test_le_run_mall_est_reproductible(mall: WorldSpec) -> None:
    """Même graine ⇒ mêmes évacuations (le monde ne tire rien tout seul)."""
    sim_a, _ = _run_level(mall, "L0", 20, seed=7)
    sim_b, _ = _run_level(mall, "L0", 20, seed=7)
    assert sim_a._evacuated == sim_b._evacuated
    assert [r.action for r in sim_a.log.rows] == [r.action for r in sim_b.log.rows]
