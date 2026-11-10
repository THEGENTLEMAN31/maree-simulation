"""world.sample — un WorldSpec mono-étage de référence (semaine 5).

Un hall avec trois sorties (A nord, B est, C sud) et un couloir vers un
second espace. C'est le « plan actuel » à faire passer au validateur puis à
la navigation — la cible : trois sorties, cohérent avec la mission 1.
"""

from __future__ import annotations

from maree.v3.world.worldspec import WorldSpec, from_dict

#: Le plan de référence (mono-étage, unités en mètres). IDs stables.
SAMPLE_DICT: dict[str, object] = {
    "id": "mall_aubel",
    "version": 3,
    "schema": "3.0.0",
    "units": "m",
    "coordinate_system": "Z_UP",
    "levels": [
        {
            "id": "L0",
            "name": "Rez-de-chaussée",
            "elevation": 0.0,
            "height": 4.5,
            "outline": [[0, 0], [120, 0], [120, 80], [0, 80]],
            "spaces": [
                {
                    "id": "S_HALL",
                    "kind": "hall",
                    "polygon": [[0, 0], [120, 0], [120, 80], [0, 80]],
                    "occupancy": 180,
                }
            ],
            "exits": [
                {"id": "A", "segment": [[55, 80], [60, 80]], "width": 5.0},
                {"id": "B", "segment": [[120, 35], [120, 42]], "width": 7.0},
                {"id": "C", "segment": [[40, 0], [48, 0]], "width": 8.0},
            ],
            "obstacles": [
                {
                    "id": "O_STAND_12",
                    "polygon": [[20, 20], [24, 20], [24, 24], [20, 24]],
                    "height": 1.2,
                    "kind": "stand",
                }
            ],
        }
    ],
    "vertical": [],
    "hazards": [],
}


def sample_worldspec() -> WorldSpec:
    return from_dict(SAMPLE_DICT)


__all__ = ["SAMPLE_DICT", "sample_worldspec"]