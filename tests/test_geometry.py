"""Géométrie : la seule source de vérité du monde."""

from __future__ import annotations

import math

import pytest

from maree.domain.geometry import (
    Plan,
    point_in_polygon,
    polygon_area,
    polygon_centroid,
)


def test_largeurs_de_sortie_sont_celles_du_scenario(plan: Plan) -> None:
    # 6,0 m / 1,5 m / 3,0 m : c'est la géométrie qui crée les goulots.
    assert plan.exit("A").width == pytest.approx(6.0)
    assert plan.exit("B").width == pytest.approx(1.5)
    assert plan.exit("C").width == pytest.approx(3.0)
    assert plan.total_exit_width == pytest.approx(10.5)


def test_point_in_polygon_carre() -> None:
    square = ((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0))
    assert point_in_polygon((1.0, 1.0), square)
    assert not point_in_polygon((3.0, 1.0), square)
    assert not point_in_polygon((-0.1, 1.0), square)


def test_centroide_et_aire() -> None:
    square = ((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0))
    assert polygon_area(square) == pytest.approx(16.0)
    cx, cy = polygon_centroid(square)
    assert (cx, cy) == pytest.approx((2.0, 2.0))


def test_zone_of_est_deterministe_et_partitionne(plan: Plan) -> None:
    assert plan.zone_of((12.0, 30.0)) == "Z7"   # fontaine
    assert plan.zone_of((27.0, 30.0)) == "Z1"   # place nord
    assert plan.zone_of((45.0, 30.0)) == "Z2"   # place est
    assert plan.zone_of((12.0, 18.0)) == "Z4"   # place ouest
    assert plan.zone_of((27.0, 18.0)) == "Z5"   # centre
    assert plan.zone_of((52.0, 18.0)) == "Z8"   # ruelle, déclarée avant Z6
    assert plan.zone_of((44.0, 8.0)) == "Z6"    # scène
    assert plan.zone_of((20.0, 8.0)) == "Z3"    # place sud


def test_zone_of_hors_domaine(plan: Plan) -> None:
    assert plan.zone_of((0.0, 0.0)) is None


def test_stage_polygon_rentre_dans_le_domaine(plan: Plan) -> None:
    """JuPedSim exige que l'issue soit DANS la zone marchable.

    La normale brute pointe vers l'extérieur pour B et C, vers l'intérieur
    pour A : sans réorientation, deux sorties sur trois seraient rejetées.
    """
    centroid = polygon_centroid(plan.walkable)
    for exit_id in ("A", "B", "C"):
        exit_ = plan.exit(exit_id)
        stage = exit_.stage_polygon(centroid)
        for point in stage:
            # Chaque sommet du rectangle doit être dans le domaine marchable.
            assert point_in_polygon(point, plan.walkable) or _on_boundary(point, plan.walkable), (
                f"sortie {exit_id} : {point} hors du domaine"
            )


def _on_boundary(point, polygon) -> bool:
    x, y = point
    return any(
        math.dist(point, vertex) < 1e-6 or
        abs(x - vertex[0]) < 1e-6 or abs(y - vertex[1]) < 1e-6
        for vertex in polygon
    )


def test_obstacles_ne_bloquent_pas_les_sorties(plan: Plan) -> None:
    """Aucun obstacle ne doit recouvrir le centre d'une sortie."""
    for exit_ in plan.exits.values():
        for obstacle in plan.obstacles:
            assert not point_in_polygon(exit_.center, obstacle.polygon)


def test_exit_inconnue_leve(plan: Plan) -> None:
    with pytest.raises(KeyError, match="sortie inconnue"):
        plan.exit("Z")
