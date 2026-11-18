"""C2 — la perception porte ce que les agents reçoivent réellement.

Preuves attendues (aucune ne demande de GPU) :

- seul, on ne voit personne et la densité est nulle ;
- la densité locale monte avec les voisins (noyau de 2 m, pas une grille) ;
- près d'un danger, la visibilité baisse et l'état se charge (stress, CO) ;
- la perception est **déterministe** (même ordre de voisins) ;
- `SUIVRE` est atteignable pour un visiteur qui ne connaît aucune sortie ;
- l'état **évolue** (la fatigue suit la distance parcourue) au lieu d'être
  réinitialisé à chaque tick.
"""

from __future__ import annotations

import math

from maree.v3.agents.agent import make_agent
from maree.v3.agents.appraisal import Action, appraise
from maree.v3.agents.policy import rules_decide
from maree.v3.core.ids import AgentId
from maree.v3.sim.scene import DENSITY_RADIUS, Scene
from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.sample import sample_worldspec

SPACE = "S_HALL"
AREA = math.pi * DENSITY_RADIUS * DENSITY_RADIUS


def _scene(points: list[tuple[float, float]], *, known=("A", "B", "C")) -> Scene:
    scene = Scene(navgraph=NavigationGraph(sample_worldspec()))
    for i, point in enumerate(points):
        agent = make_agent(i + 1, "visiteur", known_exits=frozenset(known))
        scene.add(agent, SPACE, point)
    scene.update_positions({i + 1: point for i, point in enumerate(points)})
    return scene


def test_seul_on_ne_voit_personne_et_la_densite_est_nulle() -> None:
    scene = _scene([(60.0, 40.0)])
    per = scene.perception_for(AgentId(1))
    assert per.seen_agents == ()
    assert per.crowding == 0.0
    assert per.state.stress == 0.0
    assert per.distance_to_danger is None


def test_la_densite_monte_avec_les_voisins() -> None:
    """Noyau de 2 m : un voisin proche vaut 1/(π·2²), trois en valent trois fois plus."""
    alone = _scene([(10.0, 10.0)])
    assert alone.perception_for(AgentId(1)).crowding == 0.0

    one = _scene([(10.0, 10.0), (11.0, 10.0)])
    assert one.perception_for(AgentId(1)).crowding == 1 / AREA

    three = _scene(
        [(10.0, 10.0), (11.0, 10.0), (10.0, 11.0), (11.0, 11.0)]
    )
    assert three.perception_for(AgentId(1)).crowding > one.perception_for(
        AgentId(1)
    ).crowding
    assert three.perception_for(AgentId(1)).crowding == 3 / AREA


def test_un_voisin_lointain_ne_compte_pas_dans_la_densite() -> None:
    scene = _scene([(10.0, 10.0), (20.0, 10.0)])
    per = scene.perception_for(AgentId(1))
    assert per.crowding == 0.0
    assert per.seen_agents == (AgentId(2),)  # vu, mais hors du noyau


def test_pres_du_danger_baisse_la_visibilite_et_charge_l_etat() -> None:
    calm = _scene([(10.0, 10.0)])
    calm_per = calm.perception_for(AgentId(1))
    assert calm_per.state.visibility == 50.0
    assert calm_per.distance_to_danger is None

    danger = _scene([(10.0, 10.0)])
    danger.smoke = True
    danger.hazard_origin = (0.0, 0.0)
    per = danger.perception_for(AgentId(1))
    assert per.distance_to_danger == math.dist((10.0, 10.0), (0.0, 0.0))
    assert per.threat > 0.6           # la fumée seule vaut 0,6 ; la proximité ajoute
    assert per.state.visibility < 50.0
    assert per.state.co_exposure > 0.0
    assert per.state.stress > 0.0


def test_la_perception_est_deterministe() -> None:
    points = [(30.0, 30.0), (31.0, 30.0), (30.0, 31.0), (45.0, 45.0)]
    a = _scene(points).perception_for(AgentId(1))
    b = _scene(points).perception_for(AgentId(1))
    assert a.seen_agents == b.seen_agents == (AgentId(2), AgentId(3), AgentId(4))
    assert a.crowding == b.crowding
    assert a.exits_visible == b.exits_visible


def test_les_sorties_visibles_sont_bornees_par_la_vue() -> None:
    """À 50 m on voit A et C ; B est à 60 m : il n'est pas « visible »."""
    per = _scene([(60.0, 40.0)]).perception_for(AgentId(1))
    assert per.exits_visible == frozenset({"A", "C"})


def test_suivre_est_atteignable_pour_un_visiteur() -> None:
    """Un visiteur sans sortie connue, qui voit quatre personnes : il suit.

    Avant C2, ``seen_agents`` était vide : la preuve sociale valait au mieux
    0,4 et ``SUIVRE`` était structurellement inatteignable.
    """
    scene = _scene([(10.0, 10.0), (11.0, 10.0), (10.0, 11.0), (11.0, 11.0), (9.0, 10.0)])
    agent = scene.instances[AgentId(1)].agent
    per = scene.perception_for(AgentId(1))
    assert len(per.seen_agents) == 4
    ap = appraise(
        perception=per,
        traits=agent.traits,
        knowledge=agent.knowledge,
        social=agent.social,
        name=agent.name,
    )
    assert ap.preuve_sociale >= 0.6
    decision = rules_decide(
        perception=per,
        knowledge=agent.knowledge,
        social=agent.social,
        traits=agent.traits,
        appraisal=ap,
        known_exits=frozenset(),
        name=agent.name,
    )
    assert decision.action is Action.SUIVRE


def test_l_etat_evolue_avec_le_deplacement() -> None:
    """La fatigue suit la distance parcourue : l'état n'est pas remis à zéro."""
    scene = _scene([(0.0, 0.0)])
    scene.tick = 0
    first = scene.perception_for(AgentId(1))
    assert first.state.fatigue == 0.0

    scene.tick = 1
    scene.update_positions({1: (10.0, 0.0)})
    second = scene.perception_for(AgentId(1))
    assert second.state.fatigue == 10.0 * 0.0015

    scene.tick = 2
    scene.update_positions({1: (20.0, 0.0)})
    third = scene.perception_for(AgentId(1))
    assert third.state.fatigue > second.state.fatigue


def test_la_perception_est_idempotente_dans_un_meme_tick() -> None:
    """Deux lectures au même tick renvoient le même état (pas de double montée)."""
    scene = _scene([(10.0, 10.0)])
    scene.smoke = True
    scene.hazard_origin = (10.0, 10.0)
    first = scene.perception_for(AgentId(1))
    second = scene.perception_for(AgentId(1))
    assert first.state == second.state
