"""world.worldspec — la vérité sémantique du bâtiment (monde-et-rendu §1).

Le WorldSpec est versionné, hashé, journalisé en tête de run. On définit
ici les dataclasses et le parseur ``from_dict`` (YAML/JSON). La validation
vit dans ``validate.py`` ; la navigation dans ``navgraph.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

Point = tuple[float, float]
PolygonRing = tuple[Point, ...]
Segment = tuple[Point, Point]


@dataclass(frozen=True, slots=True)
class Space:
    id: str
    kind: str
    polygon: PolygonRing
    occupancy: float = 0.0


@dataclass(frozen=True, slots=True)
class Portal:
    id: str
    between: tuple[str, str]      # ids d'espaces, ou "outside"
    segment: Segment
    width: float
    state: str = "open"           # open | closed
    capacity_p_s: float = 1.3


@dataclass(frozen=True, slots=True)
class Exit:
    id: str
    level: str
    segment: Segment
    width: float
    to: str = "outside"


@dataclass(frozen=True, slots=True)
class Obstacle:
    id: str
    polygon: PolygonRing
    height: float = 1.0
    kind: str = "obstacle"


@dataclass(frozen=True, slots=True)
class Level:
    id: str
    outline: PolygonRing
    holes: tuple[PolygonRing, ...] = ()
    spaces: tuple[Space, ...] = ()
    portals: tuple[Portal, ...] = ()
    exits: tuple[Exit, ...] = ()
    obstacles: tuple[Obstacle, ...] = ()
    name: str = ""
    elevation: float = 0.0
    height: float = 4.5


@dataclass(frozen=True, slots=True)
class VerticalLink:
    id: str
    kind: str            # stair | escalator | elevator
    from_level: str
    to_level: str
    polygon: PolygonRing
    width: float = 2.0
    capacity_p_s: float = 1.1


@dataclass(frozen=True, slots=True)
class Hazard:
    id: str
    kind: str            # fire | smoke_source
    level: str
    position: Point
    hrr_kw: tuple[Point, ...] = ()
    soot_yield: float = 0.07


@dataclass(frozen=True, slots=True)
class WorldSpec:
    id: str
    version: int
    schema: str
    units: str = "m"
    coordinate_system: str = "Z_UP"
    levels: tuple[Level, ...] = ()
    vertical: tuple[VerticalLink, ...] = ()
    hazards: tuple[Hazard, ...] = ()

    def level(self, level_id: str) -> Level:
        for lv in self.levels:
            if lv.id == level_id:
                return lv
        raise KeyError(f"étage inconnu : {level_id!r}")


def _ring(data: object) -> PolygonRing:
    return tuple((float(x), float(y)) for (x, y) in data)  # type: ignore[misc]


def from_dict(data: dict[str, object]) -> WorldSpec:
    """Construit un WorldSpec depuis un dict (venu de YAML/JSON)."""
    levels: list[Level] = []
    for ld in data["levels"]:
        spaces = tuple(
            Space(
                id=str(s["id"]),
                kind=str(s.get("kind", "space")),
                polygon=_ring(s["polygon"]),
                occupancy=float(s.get("occupancy", 0.0)),
            )
            for s in ld.get("spaces", [])
        )
        portals = tuple(
            Portal(
                id=str(p["id"]),
                between=(str(p["between"][0]), str(p["between"][1])),
                segment=(tuple(map(float, p["segment"][0])), tuple(map(float, p["segment"][1]))),
                width=float(p.get("width", 1.0)),
                state=str(p.get("state", "open")),
                capacity_p_s=float(p.get("capacity_p_s", 1.3)),
            )
            for p in ld.get("portals", [])
        )
        exits = tuple(
            Exit(
                id=str(e["id"]),
                level=str(ld["id"]),
                segment=(tuple(map(float, e["segment"][0])), tuple(map(float, e["segment"][1]))),
                width=float(e.get("width", 1.0)),
                to=str(e.get("to", "outside")),
            )
            for e in ld.get("exits", [])
        )
        obstacles = tuple(
            Obstacle(
                id=str(o["id"]),
                polygon=_ring(o["polygon"]),
                height=float(o.get("height", 1.0)),
                kind=str(o.get("kind", "obstacle")),
            )
            for o in ld.get("obstacles", [])
        )
        levels.append(
            Level(
                id=str(ld["id"]),
                outline=_ring(ld["outline"]),
                holes=tuple(_ring(h) for h in ld.get("holes", [])),
                spaces=spaces,
                portals=portals,
                exits=exits,
                obstacles=obstacles,
                name=str(ld.get("name", "")),
                elevation=float(ld.get("elevation", 0.0)),
                height=float(ld.get("height", 4.5)),
            )
        )
    vertical = tuple(
        VerticalLink(
            id=str(v["id"]),
            kind=str(v.get("kind", "stair")),
            from_level=str(v["from"]),
            to_level=str(v["to"]),
            polygon=_ring(v["polygon"]),
            width=float(v.get("width", 2.0)),
            capacity_p_s=float(v.get("capacity_p_s", 1.1)),
        )
        for v in data.get("vertical", [])
    )
    hazards = tuple(
        Hazard(
            id=str(h["id"]),
            kind=str(h.get("kind", "fire")),
            level=str(h["level"]),
            position=(float(h["position"][0]), float(h["position"][1])),
            hrr_kw=tuple((float(x), float(y)) for (x, y) in h.get("hrr_kw", [])),
            soot_yield=float(h.get("soot_yield", 0.07)),
        )
        for h in data.get("hazards", [])
    )
    return WorldSpec(
        id=str(data["id"]),
        version=int(data["version"]),
        schema=str(data["schema"]),
        units=str(data.get("units", "m")),
        coordinate_system=str(data.get("coordinate_system", "Z_UP")),
        levels=tuple(levels),
        vertical=vertical,
        hazards=hazards,
    )


__all__ = [
    "Exit",
    "Hazard",
    "Level",
    "Obstacle",
    "Point",
    "Portal",
    "Space",
    "VerticalLink",
    "WorldSpec",
    "from_dict",
]