"""Semaine 4 — le banc d'évaluation de politiques (style OpenJev)."""

from __future__ import annotations

from maree.v3.verify.bench import (
    compare_policies,
    rules_decider,
    run_bench,
)


def test_le_banc_rules_resout_toujours() -> None:
    r = run_bench(rules_decider)
    assert r["n"] > 0
    # la politique règles ne replie jamais, et justesse > 0.5 sur le jeu
    assert r["taux_resolution"] == 1.0
    assert r["taux_justesse"] >= 0.5


def test_le_tableau_comparatif_couvre_trois_politiques() -> None:
    c = compare_policies()
    assert set(c) == {"rules", "llm", "hybrid"}
    # mêmes dimensions pour comparer
    health = [c[name]["taux_justesse"] for name in c]
    assert all(isinstance(h, float) for h in health)


def test_chaque_situation_est_documentee() -> None:
    from maree.v3.verify.bench import SITUATIONS

    for s in SITUATIONS:
        assert s.description, f"{s.name} sans description"