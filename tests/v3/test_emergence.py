"""P2 — indicateurs d'émergence : consensus, couplage, E_social (B2/B3).

- un accord total sur la même sortie → consensus = 1 ;
- un accord imposé par annonce (source CONNU) → couplage ≈ 0, donc pas
  d'« émergence construite » : le flag demeure faux (contrefactuel B3) ;
- E_social = consensus observé − consensus du monde aux croyances brouillées.
"""

from __future__ import annotations

from maree.v3.agents.agent import make_agent
from maree.v3.agents.knowledge import Belief, Source
from maree.v3.verify.emergence import (
    consensus,
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


def test_consensus_total_et_partage() -> None:
    same = _agents([("A", Source.CONNU)] * 3)
    c, dist = consensus(same)
    assert c == 1.0 and dist["A"] == 1.0
    split = _agents([("A", Source.CONNU), ("A", Source.CONNU), ("B", Source.CONNU)])
    c2, _ = consensus(split)
    assert 0.0 < c2 < 1.0  # partagé, pas total


def test_une_diffusion_imposee_nest_pas_de_lemergence() -> None:
    # tout le monde « préfère A » mais personne ne l'a entendu : couplage 0
    agents = _agents([("A", Source.CONNU)] * 4)
    report = emergence_report(agents)
    assert report["consensus"] == 1.0
    assert report["couplage"] == 0.0
    assert report["emergence"] is False


def test_lemergence_construite_passe() -> None:
    # tout le monde préfère A ET l'a entendu (reçu ENTENDU)
    agents = _agents([("A", Source.ENTENDU)] * 4)
    report = emergence_report(agents)
    assert report["consensus"] == 1.0
    assert report["couplage"] == 1.0
    assert report["emergence"] is True


def test_social_excess_petit_sur_mondes_brouilles() -> None:
    e = social_excess(1.0, 0.35)   # accord total construit vs mémoires brouillées
    assert e > 0.3
    assert social_excess(0.8, 0.78) < 0.1  # artefact : excès ≈ 0