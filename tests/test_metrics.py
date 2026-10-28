"""Indicateurs I1..I6 : des fonctions pures, donc faciles à prouver."""

from __future__ import annotations

import math

import pytest

from maree.domain.geometry import Plan
from maree.metrics.indicators import (
    AgentState,
    belief_gap,
    compute,
    consensus,
    max_density,
    mean_entropy,
)


def _agent(aid: str, pos=(10.0, 10.0), best=None, evacuated=False, entropy=0.0):
    return AgentState(
        agent_id=aid,
        profile="visiteur",
        position=pos,
        belief_best=best,
        belief_entropy=entropy,
        evacuated=evacuated,
    )


def test_consensus_parfait() -> None:
    assert consensus(["A", "A", "A"]) == pytest.approx(1.0)


def test_consensus_partage() -> None:
    assert consensus(["A", "A", "B", "B"]) == pytest.approx(0.5)


def test_consensus_ignore_les_ignorants() -> None:
    assert consensus([None, None, "A", "A"]) == pytest.approx(1.0)


def test_consensus_sans_croyance_vaut_zero() -> None:
    assert consensus([None, None]) == 0.0


def test_entropie_normalisee() -> None:
    assert mean_entropy([math.log(3)] * 4, n_exits=3) == pytest.approx(1.0)
    assert mean_entropy([0.0, 0.0], n_exits=3) == 0.0


def test_densite_max_compte_par_cellule() -> None:
    agents = [
        _agent("A", (1.1, 1.1)),
        _agent("B", (1.4, 1.4)),
        _agent("C", (1.9, 1.9)),
        _agent("D", (8.0, 8.0)),
    ]
    assert max_density(agents, cell=1.0) == pytest.approx(3.0)


def test_densite_ignore_les_evacues() -> None:
    agents = [_agent("A", evacuated=True), _agent("B", evacuated=True)]
    assert max_density(agents) == 0.0


def test_ecart_de_croyance_le_piege() -> None:
    """Trois agents croient en A, une seule en B : A vient de fermer."""
    agents = [_agent("1", best="A"), _agent("2", best="A"), _agent("3", best="A"), _agent("4", best="B")]
    assert belief_gap(agents, open_exits={"B", "C"}) == pytest.approx(0.75)


def test_compute_produit_les_six_indicateurs(plan: Plan) -> None:
    agents = [
        _agent("1", best="A"),
        _agent("2", best="A"),
        _agent("3", best="B", evacuated=True),
    ]
    ind = compute(agents, plan, open_exits={"A", "B", "C"}, tick=12, elapsed_s=120.0)
    assert ind.tick == 12
    assert ind.i3_evacuated == pytest.approx(1 / 3)
    assert ind.i1_consensus == pytest.approx(1.0)
    assert ind.counts == {"agents": 3, "evacuated": 1, "remaining": 2}
    payload = ind.to_dict()
    assert payload["I4_seconds"] == 120.0


def test_compute_sur_liste_vide_ne_divise_pas_par_zero(plan: Plan) -> None:
    ind = compute([], plan, open_exits={"A"}, tick=0, elapsed_s=0.0)
    assert ind.i3_evacuated == 0.0
    assert ind.i1_consensus == 0.0
