"""Croyances : la matière première de l'indicateur I6."""

from __future__ import annotations

import math

import pytest

from maree.domain.beliefs import BeliefTable, ExitBelief, entropy


def test_table_vide_est_ignorance_totale() -> None:
    table = BeliefTable()
    assert table.best() is None
    assert table.entropy(n_exits=3) == pytest.approx(math.log(3))


def test_best_choisit_la_confiance_maximale() -> None:
    table = BeliefTable()
    table.set("A", 0.4, "vu", 1)
    table.set("B", 0.7, "entendu:A03", 2)
    assert table.best() == "B"


def test_decay_fait_basculer_une_croyance() -> None:
    table = BeliefTable()
    table.set("A", 0.9, "vu", 1)
    table.set("B", 0.1, "rumeur", 1)
    for _ in range(20):
        table.decay(0.85)
    assert table.confidence("A") < 0.2


def test_decay_ne_descend_pas_sous_le_plancher() -> None:
    table = BeliefTable()
    table.set("A", 0.5, "vu", 1)
    table.decay(0.5, floor=0.3)
    assert table.confidence("A") == pytest.approx(0.3)


def test_confiance_bornee() -> None:
    table = BeliefTable()
    table.set("A", 5.0, "vu", 1)
    assert table.confidence("A") == 1.0
    table.set("B", -1.0, "vu", 1)
    assert table.confidence("B") == 0.0


def test_exit_belief_refuse_une_confiance_invalide() -> None:
    with pytest.raises(ValueError):
        ExitBelief(exit_id="A", confidence=1.5, source="x", tick=0)


def test_entropie_maximale_quand_distribution_uniforme() -> None:
    assert entropy([0.25, 0.25, 0.25, 0.25]) == pytest.approx(math.log(4))
    assert entropy([1.0]) == 0.0


def test_snapshot_est_serialisable() -> None:
    table = BeliefTable()
    table.set("A", 0.42, "rag:#7", 3)
    snap = table.snapshot()
    assert snap["A"]["confidence"] == 0.42
    assert snap["A"]["source"] == "rag:#7"
