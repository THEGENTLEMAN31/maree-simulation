"""Géométrie du monde : plan, zones, sorties, obstacles.

Le plan est **la donnée**, pas le code (décision 11). Il est chargé depuis
`configs/world/port_aubel.yaml` et passé tel quel à JuPedSim. Godot le
reçoit dans l'instantané : plus de topologie dupliquée entre Python et
GDScript (c'était un défaut de la v1).

Le domaine reste sans dépendance : l'appartenance à un polygone est
calculée ici, en pur Python, pour que la perception soit testable sans
Shapely ni JuPedSim.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from maree.domain.ids import ExitId, Point, ZoneId


def point_in_polygon(p: Point, polygon: tuple[Point, ...]) -> bool:
    """Lancer de rayon (ray casting), arêtes exclues.

    Suffisant et déterministe pour des polygones simples (convexes ou non).
    """
    x, y = p
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < x_cross:
                inside = not inside
    return inside


def polygon_centroid(polygon: tuple[Point, ...]) -> Point:
    """Centroïde d'un polygone simple (formule des lacets)."""
    area = 0.0
    cx = 0.0
    cy = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(area) < 1e-12:  # polygone dégénéré : moyenne des sommets
        return (sum(p[0] for p in polygon) / n, sum(p[1] for p in polygon) / n)
    area *= 0.5
    return (cx / (6 * area), cy / (6 * area))


def polygon_area(polygon: tuple[Point, ...]) -> float:
    area = 0.0
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


@dataclass(frozen=True, slots=True)
class Exit:
    """Une issue : un segment sur la frontière du domaine marchable."""

    id: ExitId
    label: str
    a: Point
    b: Point

    @property
    def width(self) -> float:
        return math.dist(self.a, self.b)

    @property
    def center(self) -> Point:
        return ((self.a[0] + self.b[0]) / 2, (self.a[1] + self.b[1]) / 2)

    @property
    def normal(self) -> Point:
        """Normale sortante (unitaire) : sens de la fuite."""
        dx = self.b[0] - self.a[0]
        dy = self.b[1] - self.a[1]
        norm = math.hypot(dx, dy) or 1.0
        return (dy / norm, -dx / norm)

    def stage_polygon(self, towards: Point, depth: float = 0.4) -> tuple[Point, ...]:
        """Rectangle de l'issue, orienté vers l'INTÉRIEUR du domaine.

        JuPedSim exige que l'issue soit un polygone situé dans la zone
        marchable. `towards` (le centroïde de l'esplanade) sert à orienter
        la normale : sans cela, A rentrerait et B sortirait du domaine,
        selon le sens de parcours du segment.
        """
        nx, ny = self.normal
        cx, cy = self.center
        if (towards[0] - cx) * nx + (towards[1] - cy) * ny < 0:
            nx, ny = -nx, -ny
        (ax, ay), (bx, by) = self.a, self.b
        return (
            (ax, ay),
            (bx, by),
            (bx + nx * depth, by + ny * depth),
            (ax + nx * depth, ay + ny * depth),
        )


@dataclass(frozen=True, slots=True)
class Zone:
    """Une zone de perception — pas une maille de déplacement.

    Les agents se déplacent en continu (JuPedSim) ; les zones servent à
    décrire ce qu'ils *perçoivent* et ce dont ils *parlent*.
    """

    id: ZoneId
    label: str
    polygon: tuple[Point, ...]
    hidden: bool = False  # zone que seuls certains profils connaissent (ruelle B)

    @property
    def centroid(self) -> Point:
        return polygon_centroid(self.polygon)

    @property
    def area(self) -> float:
        return polygon_area(self.polygon)

    def contains(self, p: Point) -> bool:
        return point_in_polygon(p, self.polygon)


@dataclass(frozen=True, slots=True)
class Obstacle:
    id: str
    kind: str  # tour | fontaine | scene | stand | halle
    polygon: tuple[Point, ...]

    @property
    def centroid(self) -> Point:
        return polygon_centroid(self.polygon)


@dataclass(frozen=True, slots=True)
class Plan:
    """Le monde : une seule source de vérité géométrique."""

    name: str
    width: float
    height: float
    walkable: tuple[Point, ...]
    exits: dict[ExitId, Exit]
    zones: dict[ZoneId, Zone]
    obstacles: tuple[Obstacle, ...] = ()

    # ---- accès -------------------------------------------------
    def exit(self, exit_id: ExitId) -> Exit:
        try:
            return self.exits[exit_id]
        except KeyError as exc:
            raise KeyError(f"sortie inconnue : {exit_id!r}") from exc

    def zone_of(self, p: Point) -> ZoneId | None:
        for zone in self.zones.values():
            if zone.contains(p):
                return zone.id
        return None

    @property
    def total_exit_width(self) -> float:
        return sum(e.width for e in self.exits.values())

    # ---- construction ------------------------------------------
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Plan:
        exits = {
            e["id"]: Exit(
                id=e["id"],
                label=e.get("label", e["id"]),
                a=tuple(e["a"]),  # type: ignore[arg-type]
                b=tuple(e["b"]),  # type: ignore[arg-type]
            )
            for e in d["exits"]
        }
        zones = {
            z["id"]: Zone(
                id=z["id"],
                label=z.get("label", z["id"]),
                polygon=tuple(tuple(p) for p in z["polygon"]),  # type: ignore[misc]
                hidden=bool(z.get("hidden", False)),
            )
            for z in d["zones"]
        }
        obstacles = tuple(
            Obstacle(
                id=o["id"],
                kind=o.get("kind", "obstacle"),
                polygon=tuple(tuple(p) for p in o["polygon"]),  # type: ignore[misc]
            )
            for o in d.get("obstacles", ())
        )
        return cls(
            name=d["name"],
            width=float(d["width"]),
            height=float(d["height"]),
            walkable=tuple(tuple(p) for p in d["walkable"]),  # type: ignore[misc]
            exits=exits,
            zones=zones,
            obstacles=obstacles,
        )
