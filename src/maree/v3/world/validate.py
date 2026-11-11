"""world.validate — validateur topologique et de connectivité (monde-et-rendu §1).

Un WorldSpec invalide est **refusé avec la raison**, jamais corrigé en
silence. Chaque règle bloquante renvoie un message ; ``validate`` collecte
tous les échecs, ``validate_or_raise`` lève si le monde est invalide.
"""

from __future__ import annotations

from typing import Any

import networkx as nx
from shapely.geometry import LineString, Polygon
from shapely.geometry import Point as ShapelyPoint

from maree.v3.world.worldspec import Level, WorldSpec


class ValidationError(ValueError):
    """Le WorldSpec est invalide ; ``errors`` porte les raisons."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Plan invalide :\n- " + "\n- ".join(errors))


def _poly(polygon: Any, holes: Any = ()) -> Polygon:
    ring = list(polygon)
    int_holes = [list(h) for h in holes]
    return Polygon(ring, int_holes)


def validate(world: WorldSpec) -> list[str]:
    errors: list[str] = []

    # --- 1. IDs uniques ---
    seen: dict[str, str] = {}
    for lv in world.levels:
        for obj in (lv.spaces, lv.portals, lv.exits, lv.obstacles):
            for item in obj:
                if item.id in seen:
                    errors.append(f"identifiant dupliqué : {item.id!r} ({seen[item.id]} et L0)")
                seen[item.id] = lv.id
    for v in world.vertical:
        if v.id in seen:
            errors.append(f"identifiant dupliqué (vertical) : {v.id!r}")
    for h in world.hazards:
        if h.id in seen:
            errors.append(f"identifiant dupliqué (danger) : {h.id!r}")

    for lv in world.levels:
        _validate_level(errors, world, lv)

    # --- 6. vertical : relie des étages existants ---
    level_ids = {lv.id for lv in world.levels}
    for v in world.vertical:
        if v.from_level not in level_ids or v.to_level not in level_ids:
            errors.append(f"vertical {v.id!r} relie un étage inconnu")

    # --- 7/8. connectivité : espaces atteignables, et chemin vers une sortie ---
    errors.extend(_connectivity_errors(world))

    return errors


def validate_or_raise(world: WorldSpec) -> None:
    errors = validate(world)
    if errors:
        raise ValidationError(errors)


def _validate_level(errors: list[str], world: WorldSpec, lv: Level) -> None:
    outline = _poly(lv.outline, lv.holes)
    # --- 2. contour simple et valide ---
    if not outline.is_valid or not outline.area > 0:
        errors.append(f"étage {lv.id} : contour non valide")
        return

    space_ids = {s.id for s in lv.spaces}
    for s in lv.spaces:
        sp = _poly(s.polygon)
        # --- 3. espace contenu dans l'étage ---
        if not outline.contains(sp) and not outline.covers(sp):
            errors.append(f"espace {s.id} hors de l'étage {lv.id}")
        if not sp.is_valid or not sp.area > 0:
            errors.append(f"espace {s.id} : polygone non valide")

    # --- 4. portails relient des espaces existants ---
    for p in lv.portals:
        a, b = p.between
        if a not in ("outside", *space_ids) or b not in ("outside", *space_ids):
            errors.append(f"portail {p.id} relie un espace inconnu : {(a, b)}")
        if a == "outside" and b == "outside":
            errors.append(f"portail {p.id} relie l'extérieur à l'extérieur")

    # --- 5. sorties sur la frontière ---
    for e in lv.exits:
        seg = LineString(e.segment)
        mid = ShapelyPoint(*seg.interpolate(0.5, normalized=True).coords[0])
        if outline.boundary.distance(mid) > 1e-6:
            errors.append(f"sortie {e.id} hors de la frontière de l'étage {lv.id}")
        if not (e.width > 0):
            errors.append(f"sortie {e.id} : largeur non positive")

    # --- 9/10. obstacles dans un espace, pas sur une porte ; coupures ---
    for o in lv.obstacles:
        op = _poly(o.polygon)
        in_any = any(_poly(s.polygon).contains(op) or _poly(s.polygon).covers(op) for s in lv.spaces)
        if not in_any:
            errors.append(f"obstacle {o.id} hors de tout espace")

    for p in lv.portals:
        seg = LineString(p.segment)
        for o in lv.obstacles:
            if seg.intersects(_poly(o.polygon)):
                errors.append(f"obstacle {o.id} coupe le portail {p.id}")
        if not (p.width > 0):
            errors.append(f"portail {p.id} : largeur non positive")


def _connectivity_errors(world: WorldSpec) -> list[str]:
    # graphe : nœuds = espaces ; arêtes = portails ouverts (+ escaliers inter-étages)
    g = nx.Graph()
    space_ids: set[str] = set()
    exit_by_space: dict[str, list[str]] = {}
    level_space: dict[str, str] = {}  # premier espace représentatif d'un étage

    for lv in world.levels:
        for sp in lv.spaces:
            g.add_node(sp.id)
            space_ids.add(sp.id)
            level_space.setdefault(lv.id, sp.id)
            for e in lv.exits:
                seg = LineString(e.segment)
                mid = ShapelyPoint(*seg.interpolate(0.5, normalized=True).coords[0])
                if _poly(sp.polygon).contains(mid) or _poly(sp.polygon).covers(mid):
                    exit_by_space.setdefault(sp.id, []).append(e.id)
    for lv in world.levels:
        for p in lv.portals:
            a, b = p.between
            if a != "outside" and b != "outside" and p.state == "open":
                g.add_edge(a, b)
    for v in world.vertical:
        if v.from_level in level_space and v.to_level in level_space:
            g.add_edge(level_space[v.from_level], level_space[v.to_level])
    # un espace isolé (aucune arête) doit quand même exister
    for sid in space_ids:
        g.add_node(sid)

    errors: list[str] = []
    # --- 8. chaque espace a un chemin vers une sortie ouverte ---
    for sid in space_ids:
        if sid not in exit_by_space:
            errors.append(f"espace {sid} n'a aucune sortie ouverte")
    # --- 7. tous les espaces atteignables entre eux via portails ouverts ---
    if space_ids:
        comps = list(nx.connected_components(g))
        if len(comps) > 1:
            for comp in comps:
                errors.append(
                    f"espace(s) {sorted(comp)} inatteignable(s) depuis "
                    f"{sorted(space_ids - comp)} (portails fermés ?)"
                )
    return errors


__all__ = ["ValidationError", "validate", "validate_or_raise"]