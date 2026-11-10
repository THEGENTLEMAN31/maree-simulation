"""world.simartifact — SimArtifact, dérivé du WorldSpec pour le moteur.

Artefact dérivé et reconstructible (architecture.md §2) : polygones
marchables (étage − trous − obstacles), zones de spawn par espace, capacités
de sortie. Jamais édité à la main — on corrige le WorldSpec, pas ceci.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon

from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.worldspec import Point, WorldSpec


@dataclass(frozen=True, slots=True)
class LevelArtifact:
    level_id: str
    #: polygone marchable : étage − trous − obstacles.
    walkable: Polygon
    #: points de spawn par espace (déterministes pour une graine donnée).
    spawn_points: dict[str, tuple[Point, ...]]
    #: capacité (largeur) par sortie.
    exit_capacities: dict[str, float]


@dataclass(frozen=True, slots=True)
class SimArtifact:
    levels: dict[str, LevelArtifact]

    def spawn_points(self, space: str) -> tuple[Point, ...]:
        for art in self.levels.values():
            if space in art.spawn_points:
                return art.spawn_points[space]
        return ()

    def capacity(self, exit_id: str) -> float:
        for art in self.levels.values():
            if exit_id in art.exit_capacities:
                return art.exit_capacities[exit_id]
        return 0.0


def build_sim_artifact(
    world: WorldSpec,
    graph: NavigationGraph,
    rng: np.random.Generator,
    spawn_per_space: int = 4,
) -> SimArtifact:
    """Dérive le SimArtifact depuis le monde validé et son graphe.

    ``rng`` est la seule source d'aléa : même graine ⇒ mêmes spawns (le
    déterminisme de la mission est préservé).
    """
    art: dict[str, LevelArtifact] = {}
    for lv in world.levels:
        walkable = Polygon(list(lv.outline), [list(h) for h in lv.holes])
        for o in lv.obstacles:
            op = Polygon(list(o.polygon))
            if walkable.covers(op):
                walkable = walkable.difference(op)
        spawns: dict[str, tuple[Point, ...]] = {}
        for s in lv.spaces:
            pts = tuple(graph.sample_spawn(s.id, rng) for _ in range(spawn_per_space))
            spawns[s.id] = pts
        caps = {e.id: graph.capacity(e.id) for e in lv.exits}
        art[lv.id] = LevelArtifact(lv.id, walkable, spawns, caps)
    return SimArtifact(art)


__all__ = ["LevelArtifact", "SimArtifact", "build_sim_artifact"]