"""world.render — RenderArtifact : manifeste + export glTF 2.0 (S6).

C'est le **contrat de rendu** remis au front (monde-et-rendu §5). Trois
sorties :
- ``manifest(world)`` : mapping IDs stables → sémantique (+ extrémas) ;
- ``to_gltf(world)`` : un document glTF 2.0 (JSON) avec un nœud/mesh par
  espace, sortie et obstacle, ``extras.id``/``extras.kind``, et une scène ;
- ``render_artifact(world)`` : le couple (manifeste, gltf) prêt à servir.

Règle (architecture.md §2) : le RenderArtifact est **dérivé**, jamais édité
à la main — si le rendu est faux, on corrige le WorldSpec ou l'export.
"""

from __future__ import annotations

import base64
import json
import struct
from dataclasses import dataclass, field
from typing import Any

from maree.v3.world.worldspec import WorldSpec


@dataclass(frozen=True, slots=True)
class RenderManifest:
    """Le manifeste : [id] -> {kind, level, node, extras}."""

    entries: dict[str, dict[str, object]] = field(default_factory=dict)

    def node_for(self, item_id: str) -> dict[str, object] | None:
        return self.entries.get(item_id)


def manifest(world: WorldSpec) -> RenderManifest:
    entries: dict[str, dict[str, object]] = {}
    for lv in world.levels:
        entries[lv.id] = {
            "kind": "level",
            "node": lv.id,
            "extras": {"id": lv.id, "kind": "level"},
        }
        for s in lv.spaces:
            entries[s.id] = {
                "kind": "space",
                "level": lv.id,
                "node": s.id,
                "extras": {"id": s.id, "kind": s.kind},
            }
        for e in lv.exits:
            entries[e.id] = {
                "kind": "exit",
                "level": lv.id,
                "node": e.id,
                "extras": {"id": e.id, "kind": "exit"},
            }
        for o in lv.obstacles:
            entries[o.id] = {
                "kind": "obstacle",
                "level": lv.id,
                "node": o.id,
                "extras": {"id": o.id, "kind": o.kind},
            }
    return RenderManifest(entries)


def _segment_quad(segment: Any, width: float) -> list[tuple[float, float]]:
    """Un segment (2 points) → un quad mince (4 points) pour le rendu."""
    (x1, y1), (x2, y2) = segment
    dx, dy = x2 - x1, y2 - y1
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return [(x1 - width / 2, y1 - width / 2), (x1 + width / 2, y1 - width / 2),
                (x1 + width / 2, y1 + width / 2), (x1 - width / 2, y1 + width / 2)]
    ux, uy = dx / length, dy / length
    ox, oy = -uy * width / 2, ux * width / 2
    return [
        (x1 + ox, y1 + oy),
        (x2 + ox, y2 + oy),
        (x2 - ox, y2 - oy),
        (x1 - ox, y1 - oy),
    ]


def to_gltf(world: WorldSpec) -> dict[str, object]:
    """Un document glTF 2.0 (JSON) minimal mais réel (positions, triangles).

    Émet en éventail un triangle par tranche du contour de chaque élément.
    """
    positions: list[float] = []
    accessors: list[dict[str, object]] = []
    buffer_views: list[dict[str, object]] = []
    meshes: list[dict[str, object]] = []
    nodes: list[dict[str, object]] = []

    def emit(item_id: str, kind: str, ring: Any) -> None:
        pts = [(float(x), float(y)) for x, y in ring]
        if len(pts) < 3:
            return
        start = len(positions) // 3  # en sommets
        for i in range(1, len(pts) - 1):
            positions.extend((*pts[0][:2], 0.0))
            positions.extend((*pts[i][:2], 0.0))
            positions.extend((*pts[i + 1][:2], 0.0))
        count = (len(pts) - 2) * 3
        byte_offset = start * 3 * 4
        bv = len(buffer_views)
        buffer_views.append(
            {
                "buffer": 0,
                "byteOffset": byte_offset,
                "byteLength": count * 3 * 4,
                "target": 34962,
            }
        )
        accessors.append(
            {
                "bufferView": bv,
                "componentType": 5126,
                "count": count,
                "type": "VEC3",
                "min": [min(p[0] for p in pts), min(p[1] for p in pts), 0.0],
                "max": [max(p[0] for p in pts), max(p[1] for p in pts), 0.0],
            }
        )
        mi = len(meshes)
        meshes.append({"primitives": [{"attributes": {"POSITION": len(accessors) - 1}, "mode": 4}]})
        nodes.append(
            {
                "name": item_id,
                "mesh": mi,
                "extras": {"id": item_id, "kind": kind},
            }
        )

    for lv in world.levels:
        for s in lv.spaces:
            emit(s.id, s.kind, s.polygon)
        for o in lv.obstacles:
            emit(o.id, o.kind, o.polygon)
        for e in lv.exits:
            emit(e.id, "exit", _segment_quad(e.segment, max(0.4, e.width * 0.05)))

    payload = struct.pack(f"<{len(positions)}f", *positions) if positions else b""
    gltf = {
        "asset": {"version": "2.0", "generator": "maree-v3"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "buffers": [
            {
                "byteLength": len(payload),
                "uri": "data:application/octet-stream;base64," + base64.b64encode(payload).decode(),
            }
        ],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }
    return gltf


@dataclass(frozen=True, slots=True)
class RenderArtifact:
    manifest: RenderManifest
    gltf: dict[str, object]

    def to_json(self) -> bytes:
        return json.dumps(
            {"manifest": self.manifest.entries, "gltf": self.gltf},
            ensure_ascii=False,
        ).encode("utf-8")


def render_artifact(world: WorldSpec) -> RenderArtifact:
    return RenderArtifact(manifest(world), to_gltf(world))


__all__ = ["RenderArtifact", "RenderManifest", "manifest", "render_artifact", "to_gltf"]