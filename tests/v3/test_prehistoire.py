"""P0 — la mémoire personnelle existe enfin, et elle décide.

Trois choses étaient déclarées et mortes :

- la **mémoire J−3** n'était jamais amorcée en run (`prehistory=True` n'était
  passé nulle part) : la « mémoire personnelle » qui doit produire la
  divergence était vide au départ ;
- les **proches** n'étaient jamais assignés : `CHERCHER_PROCHE` ne pouvait pas
  se déclencher hors tests ;
- la préhistoire n'écrivait que des **reçus** (lus par le prompt du grand
  modèle), jamais de **croyances** : pour les règles, elle était décorative.

Ce que l'on vérifie ici : les faits J−3 deviennent des croyances sourcées et
datées (pour les sorties **connues** seulement), les paires de proches sont
placées ensemble et liées, et la divergence entre jumeaux apparaît — puis
disparaît quand on coupe la mémoire.
"""

from __future__ import annotations

import math

from maree.v3.agents.agent import make_agent
from maree.v3.agents.knowledge import Source
from maree.v3.agents.perception import Message
from maree.v3.agents.prehistory import J_3, prehistory_for, seed_knowledge
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import PolicyName
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.verify.twins import PublicEvent, TwinHistory, run_twins_experiment
from maree.v3.world.generate import build


# ---------------------------------------------------------------------------
# P0.2 — la préhistoire écrit des croyances
# ---------------------------------------------------------------------------
def test_la_prehistoire_ecrit_des_croyances_sourcees_et_datees() -> None:
    agent = make_agent(1, "famille", known_exits=frozenset({"A", "B"}))
    written = seed_knowledge(agent, prehistory_for("famille"))
    assert written >= 1
    hazard = agent.knowledge.beliefs.get("hazard:B")  # « B se bouche… »
    assert hazard is not None
    assert hazard.source is Source.GUIDE
    assert hazard.tick == J_3 + 8_640  # J−2 : daté, pas « maintenant »


def test_un_souvenir_ne_cree_pas_une_sortie_inconnue() -> None:
    """La géographie ne s'apprend pas par ouï-dire (garde C3, tenue ici)."""
    agent = make_agent(1, "visiteur", known_exits=frozenset({"A"}))
    seed_knowledge(agent, prehistory_for("visiteur"))  # parle de la sortie C
    assert "exit:C" not in agent.knowledge.beliefs
    assert "hazard:C" not in agent.knowledge.beliefs


def test_la_prehistoire_est_activee_par_le_moteur() -> None:
    sim = Simulation(seed=1, policy=PolicyName.RULES, prehistory=True).build(
        build("crowd_hall")
    )
    sim.spawn("famille", 2, frozenset({"A", "B"}))
    agent = next(iter(sim.scene.instances.values())).agent
    sources = {b.source for b in agent.knowledge.beliefs.values()}
    assert Source.GUIDE in sources or Source.RUMEUR in sources


# ---------------------------------------------------------------------------
# P0.3 — les proches existent
# ---------------------------------------------------------------------------
def test_les_proches_sont_lies_et_places_ensemble() -> None:
    sim = Simulation(seed=1, policy=PolicyName.RULES).build(build("crowd_hall"))
    sim.spawn("famille", 6, frozenset({"A", "B"}))
    agents = [i.agent for i in sim.scene.instances.values()]
    paired = [a for a in agents if a.social.kin]
    assert len(paired) == 6  # trois paires, personne d'orphelin
    for agent in agents:
        for kin in agent.social.kin:
            other = next(a for a in agents if a.uid == kin)
            assert agent.uid in other.social.kin  # lien symétrique
    inst = {i.agent.name: i.point for i in sim.scene.instances.values()}
    for agent in agents:
        for kin in agent.social.kin:
            other = next(a for a in agents if a.uid == kin)
            assert math.dist(inst[agent.name], inst[other.name]) < 2.5


def test_chercher_un_proche_devient_atteignable() -> None:
    sim = Simulation(seed=1, policy=PolicyName.RULES).build(build("crowd_hall"))
    sim.spawn("famille", 4, frozenset({"A", "B"}))
    sim.run([Timestep(1), Timestep(3)])
    actions = {row.action for row in sim.log.rows}
    assert actions, "les agents doivent décider"
    # sans proche assigné, cette action n'apparaissait jamais en run
    assert any("proche" in action for action in actions)


# ---------------------------------------------------------------------------
# P0.4 — la mission n°1 : la divergence vient de la mémoire
# ---------------------------------------------------------------------------
LEFT = TwinHistory(
    "A bloquée", [(1, Message("La sortie A est bloquée", AgentId(900), 1, 0.9))]
)
RIGHT = TwinHistory(
    "B bloquée", [(1, Message("La sortie B est bloquée", AgentId(900), 1, 0.9))]
)
TIMELINE = (PublicEvent(1), PublicEvent(5, smoke=True), PublicEvent(10, smoke=True))


def test_la_divergence_vient_de_la_memoire_et_disparait_sans_elle() -> None:
    with_memory = run_twins_experiment(
        timeline=TIMELINE,
        left_history=LEFT,
        right_history=RIGHT,
        archetype="visiteur",
        known_exits=frozenset({"A", "B"}),
        n_pairs=50,
        memory_on=True,
    )
    ablated = run_twins_experiment(
        timeline=TIMELINE,
        left_history=LEFT,
        right_history=RIGHT,
        archetype="visiteur",
        known_exits=frozenset({"A", "B"}),
        n_pairs=50,
        memory_on=False,
    )
    assert with_memory["agreement_ratio"] == 0.0        # 100 % divergent
    assert with_memory["left_distribution"] == {"A": 0.0, "B": 1.0}
    assert with_memory["right_distribution"] == {"A": 1.0, "B": 0.0}
    assert ablated["agreement_ratio"] == 1.0            # mémoire coupée : identiques
