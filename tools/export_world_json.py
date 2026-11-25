#!/usr/bin/env python3
"""Exporte un WorldSpec v3 (YAML) en JSON pour le client Godot isométrique.

Le client Godot ne lit pas de YAML (pas de parseur intégré) et ne doit pas
recalculer la géométrie : il reçoit une **image figée** du monde versionné.
Ce script lit `configs/world/mall_aubel.yaml` via le chargeur officiel
(`maree.v3.world.loader.load`, qui valide au passage) et écrit un JSON que
`godot/project/scripts/iso.gd` charge au démarrage.

    uv run python tools/export_world_json.py \
        --in configs/world/mall_aubel.yaml \
        --out godot/project/assets/world/mall_aubel.json

Le JSON est un **asset dérivé** (comme un PNG pré-rendu) : il porte l'empreinte
du fichier source et se régénère, il ne s'édite pas à la main.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from maree.v3.world.loader import load


def _ring(ring) -> list[list[float]]:
    return [[round(float(x), 3), round(float(y), 3)] for (x, y) in ring]


def _segment(seg) -> list[list[float]]:
    return [[round(float(p[0]), 3), round(float(p[1]), 3)] for p in seg]


def world_to_json(world) -> dict:
    levels = []
    for lv in world.levels:
        levels.append(
            {
                "id": lv.id,
                "name": lv.name,
                "elevation": round(float(lv.elevation), 3),
                "height": round(float(lv.height), 3),
                "outline": _ring(lv.outline),
                "holes": [_ring(h) for h in lv.holes],
                "spaces": [
                    {
                        "id": s.id,
                        "kind": s.kind,
                        "polygon": _ring(s.polygon),
                        "occupancy": s.occupancy,
                    }
                    for s in lv.spaces
                ],
                "portals": [
                    {
                        "id": p.id,
                        "between": list(p.between),
                        "segment": _segment(p.segment),
                        "width": p.width,
                    }
                    for p in lv.portals
                ],
                "exits": [
                    {
                        "id": e.id,
                        "segment": _segment(e.segment),
                        "width": e.width,
                        "to": e.to,
                    }
                    for e in lv.exits
                ],
                "obstacles": [
                    {
                        "id": o.id,
                        "polygon": _ring(o.polygon),
                        "height": o.height,
                        "kind": o.kind,
                    }
                    for o in lv.obstacles
                ],
            }
        )
    vertical = [
        {
            "id": v.id,
            "kind": v.kind,
            "from": v.from_level,
            "to": v.to_level,
            "polygon": _ring(v.polygon),
            "width": v.width,
        }
        for v in world.vertical
    ]
    hazards = [
        {
            "id": h.id,
            "kind": h.kind,
            "level": h.level,
            "position": [round(float(h.position[0]), 3), round(float(h.position[1]), 3)],
        }
        for h in world.hazards
    ]
    return {
        "id": world.id,
        "version": world.version,
        "schema": world.schema,
        "units": world.units,
        "levels": levels,
        "vertical": vertical,
        "hazards": hazards,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default="configs/world/mall_aubel.yaml")
    ap.add_argument("--out", dest="out", default="godot/project/assets/world/mall_aubel.json")
    args = ap.parse_args()

    world = load(args.src)
    data = world_to_json(world)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    n_levels = len(data["levels"])
    n_spaces = sum(len(l["spaces"]) for l in data["levels"])
    n_exits = sum(len(l["exits"]) for l in data["levels"])
    print(
        f"monde {data['id']!r} : {n_levels} niveaux, {n_spaces} espaces, "
        f"{n_exits} sorties, {len(data['vertical'])} liens verticaux -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())