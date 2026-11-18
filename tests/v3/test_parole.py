"""C7 — les agents parlent (émission), et le null se joue pour de vrai.

Ce que l'on verrouille :

- un agent qui vient de décider et qui a de l'altruisme (ou un rôle de
  sécurité) **émet** un message vers ses voisins vus ;
- un agent qui n'a rien décidé ne parle pas (on parle de son intention, pas
  dans le vide) ;
- le contenu dit soit la sortie que l'on prend, soit un danger cru — jamais
  une sortie que l'on ne connaît pas ;
- le message émis à t est **perçu à t+1** : la barrière de tick tient ;
- `speaking=False` est un null réellement exécuté : plus aucun message, donc
  plus aucune croyance apprise par ouï-dire ;
- une annonce d'évacuation devient une croyance d'existence pondérée par
  `authority_trust` (D8).
"""

from __future__ import annotations

from dataclasses import replace

from maree.v3.agents.agent import make_agent
from maree.v3.agents.appraisal import Action
from maree.v3.agents.appraisal import Action as Act
from maree.v3.agents.knowledge import Belief, Source
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.policy import Decision
from maree.v3.agents.speech import ALTRIUM_THRESHOLD, MAX_LISTENERS, utterance
from maree.v3.agents.state import State
from maree.v3.core.ids import AgentId, ZoneId
from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.verify import scenario_crowd as sc
from maree.v3.world.sample import sample_worldspec


def _perc(seen: tuple[AgentId, ...] = (), tick: int = 10) -> Perception:
    return Perception(
        tick=tick,
        zone=ZoneId("z"),
        state=State(),
        seen_agents=seen,
        exits_visible=frozenset(),
    )


def _speaker(archetype: str = "visiteur", altruism: float | None = None) -> object:
    agent = make_agent(1, archetype, known_exits=frozenset({"A", "B"}))
    if altruism is not None:
        # JAMAIS `agent.traits.x = …` : les traits sont **partagés** entre
        # agents du même archétype (c'est une propriété du modèle, pas un
        # défaut). On remplace la référence de cet agent, pas l'objet partagé.
        agent.traits = replace(agent.traits, altruism=altruism)
    agent._last_decision = Decision(
        action=Act.EVACUER, tick=10, target="A", explanation="test"
    )
    return agent


def test_un_agent_qui_vient_de_decider_parle_a_ses_voisins() -> None:
    agent = _speaker()
    said = utterance(agent, _perc((AgentId(2), AgentId(3), AgentId(4), AgentId(5))))
    assert said is not None
    assert said.fact == "La sortie A est praticable"
    assert said.to == (2, 3, 4)          # borné : MAX_LISTENERS
    assert len(said.to) == MAX_LISTENERS


def test_un_agent_sans_voisin_ne_parle_pas() -> None:
    agent = _speaker()
    assert utterance(agent, _perc(())) is None


def test_un_agent_qui_n_a_rien_decide_ne_parle_pas() -> None:
    agent = make_agent(1, "visiteur", known_exits=frozenset({"A"}))
    assert utterance(agent, _perc((AgentId(2),))) is None


def test_l_altruisme_et_le_role_decident_de_parler() -> None:
    quiet = _speaker(altruism=ALTRIUM_THRESHOLD - 0.2)
    assert utterance(quiet, _perc((AgentId(2),))) is None
    garde = _speaker("agent_de_securite", altruism=0.0)
    assert utterance(garde, _perc((AgentId(2),))) is not None


def test_un_danger_cru_prime_sur_la_sortie_que_l_on_prend() -> None:
    agent = _speaker()
    agent.knowledge.beliefs["hazard:B"] = Belief("sortie bloquée", 0.8, Source.ENTENDU, 10)
    said = utterance(agent, _perc((AgentId(2),)))
    assert said is not None and said.kind == "bloquee"
    assert said.fact == "La sortie B est bloquée"


def test_on_ne_parle_pas_d_une_sortie_qu_on_ne_connait_pas() -> None:
    agent = _speaker()
    agent.knowledge.beliefs["hazard:C"] = Belief("sortie bloquée", 0.9, Source.ENTENDU, 10)
    said = utterance(agent, _perc((AgentId(2),)))
    assert said is not None and "C" not in said.fact  # C n'est pas dans known_exits


def test_le_message_est_percu_au_tick_suivant() -> None:
    bus = MemoryBus()
    sim = Simulation(seed=1, policy=PolicyName.RULES, bus=bus).build(sample_worldspec())
    sim.spawn("visiteur", 6, frozenset({"A", "B", "C"}))
    sim.run([Timestep(1), Timestep(5, smoke=True), Timestep(8)])
    said = bus.published("agent.message")
    assert said, "des agents doivent parler sous fumée"
    for env in said:
        assert env.data["fact"]
        assert env.data["to"]
    # un message émis à t est perçu à t+1 : jamais dans le même tick
    assert all(env.t_prod == env.t_trait for env in said)


def test_le_null_sans_parole_supprime_les_messages() -> None:
    bus = MemoryBus()
    sim = Simulation(
        seed=1, policy=PolicyName.RULES, bus=bus, speaking=False
    ).build(sample_worldspec())
    sim.spawn("visiteur", 6, frozenset({"A", "B", "C"}))
    sim.run([Timestep(1), Timestep(5, smoke=True), Timestep(8)])
    assert bus.published("agent.message") == []
    # et personne n'a rien appris par ouï-dire
    heard = [
        belief
        for inst in sim.scene.instances.values()
        for belief in inst.agent.knowledge.beliefs.values()
        if belief.source is Source.ENTENDU
    ]
    assert heard == []


def test_la_parole_cree_des_croyances_entendues() -> None:
    bus = MemoryBus()
    sim = Simulation(seed=1, policy=PolicyName.RULES, bus=bus).build(sample_worldspec())
    sim.spawn("visiteur", 6, frozenset({"A", "B", "C"}))
    sim.run([Timestep(1), Timestep(5, smoke=True), Timestep(8)])
    entendu = [
        belief
        for inst in sim.scene.instances.values()
        for belief in inst.agent.knowledge.beliefs.values()
        if belief.source is Source.ENTENDU
    ]
    assert entendu, "un message reçu doit laisser une croyance sourcée ENTENDU"


def test_une_annonce_devient_une_croyance_ponderee_par_la_confiance_en_l_autorite() -> None:
    """D8 : l'annonce n'est pas qu'un drapeau, c'est une croyance datée."""
    agent = make_agent(1, "visiteur", known_exits=frozenset({"A", "B"}))
    per = Perception(
        tick=10,
        zone=ZoneId("z"),
        state=State(),
        announcement="Veuillez évacuer par la sortie B",
    )
    agent._learn(per)
    belief = agent.knowledge.beliefs.get("exit:B")
    assert belief is not None and belief.source is Source.ANNONCE
    expected = 0.5 + 0.5 * agent.traits.authority_trust
    assert abs(belief.confidence - expected) < 1e-9


def test_la_foule_qui_parle_change_le_consensus() -> None:
    """Deux fois le même monde, une fois muet : l'accord n'est pas le même.

    Mesuré (graine 1, scénario clivé) : I1 = 0,81 avec la parole contre 0,63
    sans. La différence n'est pas la même décision — c'est la même politique
    des deux côtés — mais ce que les agents savent les uns des autres.
    """
    with_speech = sc.measure(seed=1, policy=PolicyName.RULES, split=True)
    silent = sc.measure(seed=1, policy=PolicyName.RULES, split=True, speak=False)
    assert with_speech["summary"]["I3_evacuated"] == 1.0
    assert silent["summary"]["I3_evacuated"] == 1.0
    assert (
        with_speech["summary"]["I1_consensus"]
        > silent["summary"]["I1_consensus"]
    )


def test_action_importe_pour_le_typage() -> None:
    # garde-fou de lisibilité : EVACUER est bien l'action qui fait parler
    assert Action.EVACUER.value.startswith("évacuer")
    assert Message("x", AgentId(1), 1).fact == "x"
