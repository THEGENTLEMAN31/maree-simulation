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
    density_cells,
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


def test_densite_max_par_noyau() -> None:
    """I5 compte les voisins dans un rayon, pas dans une cellule.

    Trois agents serrés et un isolé : le maximum est 2 voisins (pour l'un
    des trois) sur l'aire du disque, et l'isolé ne compte pas.
    """
    agents = [
        _agent("A", (1.1, 1.1)),
        _agent("B", (1.4, 1.4)),
        _agent("C", (1.9, 1.9)),
        _agent("D", (8.0, 8.0)),
    ]
    assert max_density(agents, radius=1.0) == pytest.approx(2.0 / math.pi)


def test_densite_max_ne_sature_pas() -> None:
    """La grille valait 2,0 partout ; le noyau doit varier avec le nombre.

    Deux paquets de tailles différentes doivent donner deux valeurs
    différentes — c'est ce que la grille de 1 m ne savait pas faire.
    """
    serre = [_agent(str(i), (10.0 + 0.5 * i, 10.0)) for i in range(4)]
    dense = [_agent(str(i), (10.0 + 0.5 * i, 10.0)) for i in range(10)]
    assert max_density(serre, radius=3.0) < max_density(dense, radius=3.0)


def test_densite_ignore_les_evacues() -> None:
    agents = [_agent("A", evacuated=True), _agent("B", evacuated=True)]
    assert max_density(agents) == 0.0


def test_density_cells_donne_lorigine_de_chaque_cellule() -> None:
    """Le client dessine à partir de (x, y) en mètres, pas d'un index."""
    cells = density_cells([(1.1, 1.1), (1.4, 1.4), (8.0, 8.0)], cell=1.0)
    assert cells == [{"x": 1.0, "y": 1.0, "n": 2}, {"x": 8.0, "y": 8.0, "n": 1}]
    assert density_cells([], cell=1.0) == []


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
    assert ind.counts == {
        "agents": 3,
        "evacuated": 1,
        "remaining": 2,
        "by_belief": {"A": 2, "B": 0, "C": 0, "aucune": 0},
    }
    payload = ind.to_dict()
    assert payload["I4_seconds"] == 120.0
    assert payload["counts"]["by_belief"]["A"] == 2


def test_by_belief_compte_les_ignorants_a_part(plan: Plan) -> None:
    """Un agent sans croyance n'est pas un agent de plus sur une sortie."""
    agents = [_agent("1", best="A"), _agent("2"), _agent("3")]
    ind = compute(agents, plan, open_exits={"A", "B", "C"}, tick=1, elapsed_s=10.0)
    assert ind.counts["by_belief"] == {"A": 1, "B": 0, "C": 0, "aucune": 2}


def test_compute_sur_liste_vide_ne_divise_pas_par_zero(plan: Plan) -> None:
    ind = compute([], plan, open_exits={"A"}, tick=0, elapsed_s=0.0)
    assert ind.i3_evacuated == 0.0
    assert ind.i1_consensus == 0.0


def test_summarise_ignore_le_dernier_tick_degenere() -> None:
    """Quand tout le monde est sorti, I1/I2/I5/I6 valent 0 : ce n'est pas le résultat.

    Le résumé doit prendre le pic de I6 et la moyenne de I1, pas le
    dernier échantillon. Sinon toute expérience conclut « zéro ».
    """
    from maree.metrics.indicators import summarise

    series = [
        {"I1_consensus": 0.4, "I2_entropy": 0.9, "I3_evacuated": 0.0,
         "I4_seconds": 0.0, "I5_max_density": 2.0, "I6_belief_gap": 0.0},
        {"I1_consensus": 0.8, "I2_entropy": 0.4, "I3_evacuated": 0.5,
         "I4_seconds": 240.0, "I5_max_density": 3.5, "I6_belief_gap": 0.62},
        {"I1_consensus": 0.0, "I2_entropy": 0.0, "I3_evacuated": 1.0,
         "I4_seconds": 480.0, "I5_max_density": 0.0, "I6_belief_gap": 0.0},
    ]
    summary = summarise(series)
    assert summary["I6_belief_gap"] == pytest.approx(0.62)
    assert summary["I5_max_density"] == pytest.approx(3.5)
    assert summary["I1_consensus"] == pytest.approx((0.4 + 0.8) / 2)
    assert summary["I3_evacuated"] == pytest.approx(1.0)
    assert summary["I4_seconds"] == pytest.approx(480.0)


def test_summarise_ne_penalise_pas_les_runs_courts() -> None:
    """Deux runs d'état actif identique doivent résumer identiquement.

    Constaté en X1 : `clair` sort en 19 ticks, `ambigu` en 55. Le tick
    dégénéré (tout sorti, I1 = 0) pesait 1/19 dans l'un et 1/55 dans
    l'autre — le bras court était pénalisé par la durée, pas par la
    cognition.
    """
    from maree.metrics.indicators import summarise

    def tick(i1: float, evac: float) -> dict[str, float]:
        return {"I1_consensus": i1, "I2_entropy": 0.5, "I3_evacuated": evac,
                "I4_seconds": 0.0, "I5_max_density": 2.0, "I6_belief_gap": 0.0}

    court = [tick(0.9, 0.0), tick(0.9, 0.5), tick(0.0, 1.0)]
    long = [tick(0.9, 0.0)] * 20 + [tick(0.9, 0.5)] * 4 + [tick(0.0, 1.0)]
    assert summarise(court)["I1_consensus"] == pytest.approx(0.9)
    assert summarise(long)["I1_consensus"] == pytest.approx(0.9)


def test_summarise_serie_vide() -> None:
    from maree.metrics.indicators import summarise

    assert summarise([])["I6_belief_gap"] == 0.0
