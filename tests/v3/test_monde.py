"""Semaine 5 — le monde : WorldSpec, validation, navigation, SimArtifact.

Critère (roadmap S5) : un plan invalide est **refusé avec la raison** ; le
plan actuel (le sample) passe et se simule / se navigue.
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.sample import SAMPLE_DICT, sample_worldspec
from maree.v3.world.simartifact import build_sim_artifact
from maree.v3.world.validate import ValidationError, validate, validate_or_raise


def test_le_plan_de_reference_passe_la_validation() -> None:
    assert validate(sample_worldspec()) == []


def test_un_id_duplique_est_refuse() -> None:
    bad = copy.deepcopy(SAMPLE_DICT)
    bad["levels"][0]["exits"].append(dict(bad["levels"][0]["exits"][0]))
    sample_worldspec()
    # reconstruit avec le plan cassé
    from maree.v3.world.worldspec import from_dict

    errors = validate(from_dict(bad))
    assert errors, "un id dupliqué doit être refusé"
    assert any("dupliqué" in e for e in errors)


def test_une_sortie_hors_frontiere_est_refusee() -> None:
    bad = copy.deepcopy(SAMPLE_DICT)
    # sortie flottant au milieu du hall (hors frontière)
    bad["levels"][0]["exits"][0]["segment"] = [[60, 40], [65, 40]]
    from maree.v3.world.worldspec import from_dict

    errors = validate(from_dict(bad))
    assert errors
    assert any("frontière" in e for e in errors)


def test_validate_or_raise_leve_avec_les_raisons() -> None:
    bad = copy.deepcopy(SAMPLE_DICT)
    bad["levels"][0]["exits"][0]["segment"] = [[60, 40], [65, 40]]
    from maree.v3.world.worldspec import from_dict

    with pytest.raises(ValidationError) as exc:
        validate_or_raise(from_dict(bad))
    assert exc.value.errors


def test_navigation_identifie_les_espaces() -> None:
    g = NavigationGraph(sample_worldspec())
    assert g.space_at((60, 40), "L0") == "S_HALL"
    assert g.space_at((200, 200), "L0") is None  # hors du bâtiment


def test_les_sorties_reachables_depuis_le_hall() -> None:
    g = NavigationGraph(sample_worldspec())
    assert g.reachable_exits((60, 40), "L0") == ["A", "B", "C"]


def test_distance_graphe_et_ligne_de_vue() -> None:
    g = NavigationGraph(sample_worldspec())
    assert g.path_distance((10, 10), (50, 50), "L0") == 0.0
    assert g.line_of_sight((10, 10), (100, 10), "L0") is True
    # la ligne (10,10)-(30,30) traverse l'obstacle O_STAND_12 (20..24)
    assert g.line_of_sight((10, 10), (30, 30), "L0") is False


def test_capacites_des_sorties() -> None:
    g = NavigationGraph(sample_worldspec())
    assert g.capacity("A") == pytest.approx(5.0)
    assert g.capacity("B") == pytest.approx(7.0)
    assert g.capacity("C") == pytest.approx(8.0)


def test_simartifact_deterministe_et_dans_les_espaces() -> None:
    world = sample_worldspec()
    g = NavigationGraph(world)
    rng = np.random.default_rng(42)
    art = build_sim_artifact(world, g, rng, spawn_per_space=4)
    pts = art.spawn_points("S_HALL")
    assert len(pts) == 4
    for p in pts:
        assert g.space_at(p, "L0") == "S_HALL"
    rng2 = np.random.default_rng(42)
    art2 = build_sim_artifact(world, g, rng2, spawn_per_space=4)
    assert art2.spawn_points("S_HALL") == pts  # déterminisme
    assert art.capacity("C") == pytest.approx(8.0)