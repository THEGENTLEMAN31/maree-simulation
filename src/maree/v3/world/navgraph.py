"""world.navgraph — NavigationGraph : Shapely + NetworkX (monde-et-rendu §2).

Remplace la distance euclidienne : une sortie derrière un mur n'est pas « la
plus proche », un agent ne naît pas dans un obstacle. Graphe espaces / portails
ouverts / sorties ; Dijkstra pour les distances et itinéraires.
"""

from __future__ import annotations

import networkx as nx
import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.geometry import Point as ShapelyPoint

from maree.v3.world.worldspec import Level, Point, Space, WorldSpec


class _Geometry:
    """Cache des polygones Shapely d'un étage."""

    def __init__(self, level: Level) -> None:
        self.outline = Polygon(list(level.outline), [list(h) for h in level.holes])
        self.space_polys = {s.id: Polygon(list(s.polygon)) for s in level.spaces}
        self.obstacle_polys = [Polygon(list(o.polygon)) for o in level.obstacles]


class NavigationGraph:
    """Le graphe de navigation d'un WorldSpec (mono-étage en v3.0)."""

    def __init__(self, world: WorldSpec) -> None:
        self.world = world
        self._geom: dict[str, _Geometry] = {}
        self._space_poly: dict[str, Polygon] = {}
        self._space_level: dict[str, str] = {}
        self._space_exits: dict[str, list[str]] = {}
        self._exit_segment: dict[str, LineString] = {}
        self._exit_space: dict[str, str] = {}
        self._space_graph: nx.Graph = nx.Graph()

        self._build(world)

    # --- construction ---
    def _build(self, world: WorldSpec) -> None:
        g = self._space_graph
        for lv in world.levels:
            geo = _Geometry(lv)
            self._geom[lv.id] = geo
            for s in lv.spaces:
                g.add_node(s.id)
                self._space_poly[s.id] = geo.space_polys[s.id]
                self._space_level[s.id] = lv.id
                for e in lv.exits:
                    seg = LineString(e.segment)
                    mid = ShapelyPoint(*seg.interpolate(0.5, normalized=True).coords[0])
                    # covers (frontière incluse) : les sorties sont sur la frontière.
                    if geo.space_polys[s.id].covers(mid):
                        self._space_exits.setdefault(s.id, []).append(e.id)
                        self._exit_segment[e.id] = seg
                        self._exit_space[e.id] = s.id
        for lv in world.levels:
            for p in lv.portals:
                a, b = p.between
                if a != "outside" and b != "outside" and p.state == "open":
                    g.add_edge(a, b)

    # --- contrat NavigationGraph ---
    def space_at(self, point: Point, level: str) -> str | None:
        geo = self._geom.get(level)
        if geo is None:
            return None
        pt = ShapelyPoint(point)
        for s_id, poly in geo.space_polys.items():
            if poly.contains(pt) or poly.covers(pt):
                return s_id
        return None

    def reachable_exits(self, point: Point, level: str) -> list[str]:
        space = self.space_at(point, level)
        if space is None:
            return []
        return self._exits_from(space)

    def _exits_from(self, space: str | None) -> list[str]:
        if space is None:
            return []
        return sorted(self._space_exits.get(space, []))

    def path_distance(self, a: Point, b: Point, level: str) -> float:
        """Distance de graphe entre deux points (0 si même espace)."""
        sa = self.space_at(a, level)
        sb = self.space_at(b, level)
        if sa is None or sb is None:
            return float("inf")
        if sa == sb:
            return 0.0
        try:
            return nx.algorithms.shortest_path_length(self._space_graph, sa, sb)
        except nx.NetworkXNoPath:
            return float("inf")

    def route(self, start: Point, goal: str, level: str) -> list[str]:
        """Suite d'espaces de ``start`` jusqu'à l'espace de la sortie ``goal``."""
        sa = self.space_at(start, level)
        te = self._exit_space.get(goal)
        if sa is None or te is None:
            return []
        try:
            return nx.shortest_path(self._space_graph, sa, te)
        except nx.NetworkXNoPath:
            return []

    def line_of_sight(self, a: Point, b: Point, level: str) -> bool:
        geo = self._geom.get(level)
        if geo is None:
            return False
        seg = LineString([a, b])
        if any(seg.intersects(ob) for ob in geo.obstacle_polys):
            return False
        walkable = geo.outline
        return walkable.covers(seg)

    def sample_spawn(self, space: str, rng: np.random.Generator) -> Point:
        poly = self._space_poly[space]
        bounds = poly.bounds
        for _ in range(100):
            x = rng.uniform(bounds[0], bounds[2])
            y = rng.uniform(bounds[1], bounds[3])
            pt = ShapelyPoint(x, y)
            if poly.contains(pt):
                return (x, y)
        # repli déterministe : le centroïde
        cx, cy = poly.centroid.x, poly.centroid.y
        return (float(cx), float(cy))

    def capacity(self, exit_id: str) -> float:
        seg = self._exit_segment.get(exit_id)
        return seg.length if seg is not None else 0.0

    def bounds(self, level: str) -> tuple[float, float, float, float]:
        geo = self._geom.get(level)
        return geo.outline.bounds if geo is not None else (0.0, 0.0, 0.0, 0.0)

    # --- utilitaire d'énumération ---
    def spaces(self) -> list[Space]:
        return [s for lv in self.world.levels for s in lv.spaces]


__all__ = ["NavigationGraph"]