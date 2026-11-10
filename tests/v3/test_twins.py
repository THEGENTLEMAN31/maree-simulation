"""Semaine 3 — individualité : l'expérience des jumeaux et l'ablation.

Critère (roadmap S3) : la divergence est **mesurable** avec mémoire
(KL > seuil, désaccord > 0) et **nulle sans** (ablation ``memory_on=False``
→ KL ≈ 0, accord = 1). Déterminisme : un même run redonne le même rapport.
"""

from __future__ import annotations

import math

from maree.v3.agents.perception import Message
from maree.v3.core.ids import AgentId
from maree.v3.verify.metrics import (
    agreement_ratio,
    exit_distribution,
    kl_divergence,
)
from maree.v3.verify.twins import (
    PublicEvent,
    TwinHistory,
    run_twins_experiment,
)


# une histoire où l'une des sorties est dite bloquée
def _histoire(bloque: str) -> TwinHistory:
    return TwinHistory(
        name=f"bloque {bloque}",
        messages=[(2, Message(f"{bloque} est bloquée", AgentId(3), 2))],
    )


_SCENARIO = (PublicEvent(1), PublicEvent(10, smoke=True))


def test_kl_nulle_pour_des_distributions_identiques() -> None:
    assert kl_divergence({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5}) == 0.0


def test_kl_strictement_positive_sinon() -> None:
    assert kl_divergence({"A": 1.0}, {"A": 0.0, "B": 1.0}) > 0.0


def test_distribution_et_accord() -> None:
    left = ["A", "A", "B"]
    right = ["A", "B", "B"]
    d = exit_distribution(left, ("A", "B"))
    assert math.isclose(d["A"], 2 / 3)
    assert agreement_ratio(left, right) == 2 / 3


def test_les_jumeaux_divergent_avec_memoire() -> None:
    rapport = run_twins_experiment(
        timeline=_SCENARIO,
        left_history=_histoire("A"),
        right_history=_histoire("B"),
        n_pairs=6,
        memory_on=True,
    )
    assert rapport["kl_divergence"] > 0.0
    assert rapport["agreement_ratio"] < 1.0
    # l'un va vers B, l'autre vers A
    assert rapport["left_distribution"] != rapport["right_distribution"]


def test_ablation_memoire_gomme_la_divergence() -> None:
    rapport = run_twins_experiment(
        timeline=_SCENARIO,
        left_history=_histoire("A"),
        right_history=_histoire("B"),
        n_pairs=6,
        memory_on=False,
    )
    assert rapport["kl_divergence"] == 0.0
    assert rapport["agreement_ratio"] == 1.0


def test_le_run_est_deterministe() -> None:
    a = run_twins_experiment(
        timeline=_SCENARIO,
        left_history=_histoire("A"),
        right_history=_histoire("B"),
        n_pairs=6,
    )
    b = run_twins_experiment(
        timeline=_SCENARIO,
        left_history=_histoire("A"),
        right_history=_histoire("B"),
        n_pairs=6,
    )
    assert a == b