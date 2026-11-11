"""world.generate — le monde n'est pas figé : des configurations → des bâtiments.

On ne construit pas un moteur de CAD : on génère des **configurations de haut
niveau** (étages, sorties, obstacles) en WorldSpec **valide par construction**,
re-vérifié par le validateur. 2–3 presets suffisent pour « des bâtiments
différents » (nb d'étages, nombre/position des sorties) sans sur-ingénierie.
"""

from __future__ import annotations

from dataclasses import dataclass

from maree.v3.world.validate import validate_or_raise
from maree.v3.world.worldspec import WorldSpec, from_dict

Edge = str  # "top" | "bottom" | "left" | "right"


@dataclass(frozen=True, slots=True)
class ExitSpec:
    label: str
    edge: Edge
    center: float   # coordonnée le long de l'arête (x pour left/right, y pour top/bottom)
    width: float = 4.0


def _segment(edge: Edge, center: float, width: float, w: float, h: float):
    half = width / 2.0
    if edge == "top":
        return [[center - half, h], [center + half, h]]
    if edge == "bottom":
        return [[center - half, 0], [center + half, 0]]
    if edge == "right":
        return [[w, center - half], [w, center + half]]
    return [[0, center - half], [0, center + half]]


def hall_config(
    *,
    world_id: str = "hall",
    width: float = 120.0,
    height: float = 80.0,
    exits: tuple[ExitSpec, ...] = (ExitSpec("A", "top", 57.0),),
    obstacle: bool = False,
) -> dict[str, object]:
    """Un hall simple (1 espace, N sorties) — la base des bâtiments."""
    level: dict[str, object] = {
        "id": "L0",
        "outline": [[0, 0], [width, 0], [width, height], [0, height]],
        "spaces": [{"id": "S_HALL", "kind": "hall", "polygon": [[0, 0], [width, 0], [width, height], [0, height]]}],
        "exits": [
            {"id": ex.label, "segment": _segment(ex.edge, ex.center, ex.width, width, height), "width": ex.width}
            for ex in exits
        ],
        "obstacles": (
            [{"id": "O_STAND_12", "polygon": [[20, 20], [24, 20], [24, 24], [20, 24]], "height": 1.2, "kind": "stand"}]
            if obstacle else []
        ),
    }
    return {"id": world_id, "version": 3, "schema": "3.0.0", "units": "m",
            "coordinate_system": "Z_UP", "levels": [level], "vertical": [], "hazards": []}


@dataclass(frozen=True, slots=True)
class FloorConfig:
    level_id: str
    width: float
    height: float
    exits: tuple[ExitSpec, ...]
    y_offset: float = 0.0   # élévation en Y de l'étage (pour l'affichage)


def two_floor_config(
    *,
    lower: FloorConfig,
    upper: FloorConfig,
    stair_pos: tuple[float, float] = (30, 30),
    world_id: str = "two_floor",
) -> dict[str, object]:
    """Deux étages reliés par un escalier (WorldSpec multi-étages)."""
    levels: list[dict[str, object]] = []
    for f in (lower, upper):
        levels.append({
            "id": f.level_id,
            "outline": [[0, 0], [f.width, 0], [f.width, f.height], [0, f.height]],
            "elevation": f.y_offset,
            "spaces": [{"id": f"SP_{f.level_id}", "kind": "floor", "polygon": [[0, 0], [f.width, 0], [f.width, f.height], [0, f.height]]}],
            "exits": [
                {"id": ex.label, "segment": _segment(ex.edge, ex.center, ex.width, f.width, f.height), "width": ex.width}
                for ex in f.exits
            ],
            "obstacles": [],
        })
    return {
        "id": world_id,
        "version": 3,
        "schema": "3.0.0",
        "units": "m",
        "coordinate_system": "Z_UP",
        "levels": levels,
        "vertical": [
            {"id": "ST_MAIN", "kind": "stair", "from": lower.level_id, "to": upper.level_id,
             "polygon": [[stair_pos[0], stair_pos[1]], [stair_pos[0] + 3, stair_pos[1]], [stair_pos[0] + 3, stair_pos[1] + 4], [stair_pos[0], stair_pos[1] + 4]],
             "width": 2.0, "capacity_p_s": 1.1}
        ],
        "hazards": [],
    }


def preset(name: str) -> dict[str, object]:
    """2–3 bâtiments de base, générés *déterministement* de haut niveau."""
    return {
        "hall_1": hall_config(
            world_id="hall_1", width=100, height=60,
            exits=(ExitSpec("A", "top", 50.0),),
            obstacle=True,
        ),
        "hall_3": hall_config(
            world_id="hall_3", width=120, height=80,
            exits=(ExitSpec("A", "top", 57.0), ExitSpec("B", "right", 38.0), ExitSpec("C", "bottom", 44.0)),
        ),
        "two_floor": two_floor_config(
            lower=FloorConfig("L0", 100, 60, (ExitSpec("A", "bottom", 50),)),
            upper=FloorConfig("L1", 100, 60, (ExitSpec("B", "top", 50),), y_offset=4.5),
        ),
    }[name]


def build(name: str) -> WorldSpec:
    """Génère un WorldSpec **validé** (un bâtiment invalide est refusé)."""
    spec = preset(name)
    world = from_dict(spec)
    validate_or_raise(world)
    return world


#: les noms disponibles.
PRESETS = ("hall_1", "hall_3", "two_floor")

__all__ = ["PRESETS", "ExitSpec", "FloorConfig", "build", "hall_config", "preset", "two_floor_config"]