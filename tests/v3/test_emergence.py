"""P2 — indicateurs d'émergence : consensus, couplage, E_social (B2/B3).

Ce que l'on verrouille, après le correctif C4 :

- un accord total sur la même sortie → consensus = 1 ;
- un accord **imposé** (source CONNU) → couplage 0 : ce n'est pas une
  émergence construite ;
- un ouï-dire qui **confirme** la sortie déjà préférée n'est pas du
  couplage : c'est de la diffusion. Seul un message qui **change** la
  préférence compte ;
- E_social = consensus observé − consensus du null (mémoires permutées),
  calculé, pas postulé.
"""

from __future__ import annotations

from maree.v3.agents.agent import make_agent
from maree.v3.agents.knowledge import Belief, Source
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.state import State
from maree.v3.core.ids import AgentId, ZoneId
from maree.v3.verify.emergence import (
    consensus,
    consensus_without_hearsay,
    emergence_report,
    social_excess,
)


def _agents(exit_sources: list[tuple[str, Source]]) -> list:
    out = []
    for i, (label, src) in enumerate(exit_sources):
        a = make_agent(i + 1, "visiteur", known_exits=frozenset({label}))
        a.knowledge.beliefs[f"exit:{label}"] = Belief(label, 0.8, src, 0)
        out.append(a)
    return out


def _perception(heard: tuple[Message, ...]) -> Perception:
    return Perception(
        tick=10,
        zone=ZoneId("z1"),
        state=State(),
        heard=heard,
        seen_agents=(),
        exits_visible=frozenset(),
    )


def test_consensus_total_et_partage() -> None:
    same = _agents([("A", Source.CONNU)] * 3)
    c, dist = consensus(same)
    assert c == 1.0 and dist["A"] == 1.0
    split = _agents([("A", Source.CONNU), ("A", Source.CONNU), ("B", Source.CONNU)])
    c2, _ = consensus(split)
    assert 0.0 < c2 < 1.0  # partagé, pas total


def test_une_diffusion_imposee_nest_pas_de_lemergence() -> None:
    # tout le monde « préfère A » mais personne ne l'a appris des autres
    agents = _agents([("A", Source.CONNU)] * 4)
    report = emergence_report(agents)
    assert report["consensus"] == 1.0
    assert report["couplage"] == 0.0
    assert report["emergence"] is False


def test_un_oui_dire_qui_confirme_nest_pas_du_couplage() -> None:
    """La croyance vient d'un ENTENDU, mais elle n'a rien changé : diffusion."""
    agents = _agents([("A", Source.ENTENDU)] * 4)
    report = emergence_report(agents)
    assert report["consensus"] == 1.0
    assert report["couplage"] == 0.0
    assert report["emergence"] is False


def test_un_oui_dire_qui_change_la_preference_est_du_couplage() -> None:
    """Un message « B est praticable » fait basculer A → B : là, il y a couplage."""
    agents = []
    for i in range(4):
        agent = make_agent(i + 1, "visiteur", known_exits=frozenset({"A", "B"}))
        agent.knowledge.beliefs["exit:A"] = Belief("A", 0.45, Source.CONNU, 0)
        agent.react(_perception((Message("la sortie B est praticable", AgentId(9), 10, 1.0),)))
        agents.append(agent)
    report = emergence_report(agents)
    assert report["consensus"] == 1.0
    assert report["couplage"] == 1.0
    assert report["emergence"] is True


def test_social_excess_petit_sur_mondes_brouilles() -> None:
    e = social_excess(1.0, 0.35)   # accord total construit vs mémoires brouillées
    assert e > 0.3
    assert social_excess(0.8, 0.78) < 0.1  # artefact : excès ≈ 0


def test_le_null_retire_ce_qui_vient_des_autres() -> None:
    """Le null n'est pas une permutation (invariante) : il coupe l'ouï-dire."""
    agents = []
    for i in range(6):
        agent = make_agent(i + 1, "visiteur", known_exits=frozenset({"A", "B"}))
        # tout le monde connaît A et B, mais tous n'ont entendu que B
        agent.knowledge.beliefs["exit:A"] = Belief("A", 0.3, Source.CONNU, 0)
        agent.knowledge.beliefs["exit:B"] = Belief("B", 0.9, Source.ENTENDU, 10)
        agents.append(agent)
    # observé : tout le monde préfère B (consensus 1,0)
    assert consensus(agents)[0] == 1.0
    # sans l'ouï-dire, la préférence retombe sur A (consensus 1,0 aussi mais
    # sur une autre sortie) : l'excès mesure l'accord *attribuable* à la rumeur
    assert consensus_without_hearsay(agents) == 1.0
    # avec des croyances initiales divergentes, le null casse l'accord
    divergent = []
    for i in range(6):
        agent = make_agent(i + 1, "visiteur", known_exits=frozenset({"A", "B", "C"}))
        prior = "A" if i % 2 == 0 else "C"
        agent.knowledge.beliefs[f"exit:{prior}"] = Belief(prior, 0.8, Source.CONNU, 0)
        agent.knowledge.beliefs["exit:B"] = Belief("B", 0.9, Source.ENTENDU, 10)
        divergent.append(agent)
    assert consensus(divergent)[0] == 1.0
    # partagé en deux : l'accord normalisé tombe à 0 (entropie maximale)
    assert consensus_without_hearsay(divergent) == 0.0
