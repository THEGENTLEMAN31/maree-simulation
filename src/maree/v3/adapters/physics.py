"""adapters.physics — le vrai moteur de foule derrière le port ``CrowdPhysics``.

JuPedSim 1.4 (LGPL) : évitement, vitesse, densité, goulots. Le moteur
n'exécute que des intentions (sortie ou rester). Mesures v2 : 60 agents ×
2 000 pas ≈ 0,06 s — **la foule n'est pas le coût**, le LLM l'est.

Point non négociable (AGENTS.md) : un agent doit être à > 0,2 m des parois
et > 0,4 m d'un autre, sinon JuPedSim lève. ``_place`` cherche donc une
place libre en spirale déterministe ; une issue fermée redirige (v3.1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import jupedsim as jps
import shapely
from shapely.geometry import Polygon

from maree.v3.sim.physics import Target
from maree.v3.world.worldspec import Point, Segment

#: marge minimale aux parois (rayon du modèle).
WALL_MARGIN = 0.25


@dataclass
class JuPedSimCrowd:
    """Implémente ``CrowdPhysics`` avec JuPedSim (mono-étage, v3.0)."""

    walkable: Polygon               # le polygone marchable (SimArtifact)
    exits: dict[str, Segment]       # étiquette -> segment de sortie (frontière)
    dt: float = 0.05
    seed: int = 0
    model: str = "collision_free"
    desired_speed: float = 1.2

    _sim: Any = field(init=False)
    _params: Any = field(init=False)
    _model: Any = field(init=False)
    _exit_stage: dict[str, int] = field(default_factory=dict, init=False)
    _exit_journey: dict[str, int] = field(default_factory=dict, init=False)
    _point_stage: dict[tuple[float, float], int] = field(default_factory=dict, init=False)
    _point_journey: dict[tuple[float, float], int] = field(default_factory=dict, init=False)
    _tag_jps: dict[int, int] = field(default_factory=dict, init=False)
    _jps_tag: dict[int, int] = field(default_factory=dict, init=False)
    _evacuated: set[int] = field(default_factory=set, init=False)
    _centroid: tuple[float, float] = field(init=False)

    def __post_init__(self) -> None:
        model_factory = {
            "collision_free": jps.CollisionFreeSpeedModel,
            "social_force": jps.SocialForceModel,
        }.get(self.model)
        if model_factory is None:
            raise ValueError(f"modèle inconnu : {self.model!r}")
        self._model = model_factory()
        self._sim = jps.Simulation(
            model=self._model,
            geometry=self.walkable,
            dt=self.dt,
            seed=self.seed,
        )
        self._params = getattr(jps, type(self._model).__name__ + "AgentParameters")
        self._centroid = self._geometry_centroid()
        for label, seg in self.exits.items():
            stage = self._sim.add_exit_stage(self._exit_polygon(seg))
            self._exit_stage[label] = stage
            self._exit_journey[label] = self._sim.add_journey(
                jps.JourneyDescription([stage])
            )

    # ---- utilitaires -------------------------------------------------
    def _geometry_centroid(self) -> tuple[float, float]:
        cx, cy = self.walkable.centroid.x, self.walkable.centroid.y
        return (float(cx), float(cy))

    def _exit_polygon(self, seg: Segment) -> Polygon:
        """Un petit polygone *à l'intérieur* du domaine, devant la sortie."""
        (x1, y1), (x2, y2) = seg
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy) or 1.0
        tx, ty = dx / length, dy / length          # tangent
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        nx, ny = -ty, tx                            # perpendiculaire (normal brute)
        ox, oy = self._centroid
        # oriente la normale vers l'intérieur du domaine
        if (ox - cx) * nx + (oy - cy) * ny < 0:
            nx, ny = -nx, -ny
        half = max(0.4, length / 2)
        depth = 1.5
        return Polygon([
            (cx + tx * half + nx * 0.2, cy + ty * half + ny * 0.2),
            (cx - tx * half + nx * 0.2, cy - ty * half + ny * 0.2),
            (cx - tx * half + nx * depth, cy - ty * half + ny * depth),
            (cx + tx * half + nx * depth, cy + ty * half + ny * depth),
        ])

    def _safe_position(self, position: Point) -> Point:
        x, y = position
        cx, cy = self._centroid
        inner = self.walkable.buffer(-WALL_MARGIN)
        for _ in range(12):
            if inner.contains(shapely.Point(x, y)):
                return (x, y)
            x += (cx - x) * 0.12
            y += (cy - y) * 0.12
        return (float(cx), float(cy))

    def _stay_journey(self, position: Point) -> tuple[int, int]:
        """(journey, stage) d'un point : l'agent « reste » sur place."""
        safe = self._safe_position(position)
        key = (round(safe[0], 1), round(safe[1], 1))
        if key not in self._point_journey:
            stage = self._sim.add_waypoint_stage(key, 0.4)
            self._point_stage[key] = stage
            self._point_journey[key] = self._sim.add_journey(
                jps.JourneyDescription([stage])
            )
        return self._point_journey[key], self._point_stage[key]

    def _journey_for(self, target: Target) -> tuple[int, int]:
        if target.kind == "exit" and target.exit_id in self._exit_journey:
            return self._exit_journey[target.exit_id], self._exit_stage[target.exit_id]
        return self._stay_journey((0.0, 0.0))

    def _place(self, position: Point, journey: int, stage: int, desired_speed: float) -> int:
        base = self._safe_position(position)
        inner = self.walkable.buffer(-WALL_MARGIN)
        last: RuntimeError | None = None
        for attempt in range(48):
            if attempt == 0:
                candidate = base
            else:
                angle = attempt * 2.399963
                radius = 0.35 * math.sqrt(attempt)
                candidate = (base[0] + radius * math.cos(angle), base[1] + radius * math.sin(angle))
            if not inner.contains(shapely.Point(candidate[0], candidate[1])):
                continue
            try:
                return self._sim.add_agent(
                    self._params(
                        position=candidate,
                        journey_id=journey,
                        stage_id=stage,
                        desired_speed=desired_speed,
                    )
                )
            except RuntimeError as exc:
                last = exc
        raise RuntimeError(f"impossible de placer l'agent près de {position} : {last}")

    # ---- CrowdPhysics -------------------------------------------------
    def spawn(self, tag: int, position: Point, desired_speed: float) -> None:
        journey, stage = self._stay_journey(position)
        jps_id = self._place(position, journey, stage, desired_speed)
        self._tag_jps[tag] = jps_id
        self._jps_tag[jps_id] = tag

    def set_intention(self, tag: int, target: Target) -> None:
        jps_id = self._tag_jps.get(tag)
        if jps_id is None or jps_id not in self._alive():
            return
        journey, stage = self._journey_for(target)
        self._sim.switch_agent_journey(jps_id, journey, stage)

    def advance(self, steps: int = 1) -> None:
        for _ in range(steps):
            self._sim.iterate()

    def _alive(self) -> set[int]:
        return {a.id for a in self._sim.agents()}

    def positions(self) -> dict[int, Point]:
        out: dict[int, Point] = {}
        for tag, jps_id in self._tag_jps.items():
            try:
                p = self._sim.agent(jps_id).position
            except (RuntimeError, KeyError):
                continue
            out[tag] = (float(p[0]), float(p[1]))
        return out

    def evacuated(self) -> set[int]:
        alive = self._alive()
        newly = {tag for tag, jps_id in self._tag_jps.items() if jps_id not in alive}
        self._evacuated |= newly
        return self._evacuated

    def close(self) -> None:
        """Libère les ressources (rien à fermer pour le moteur embarqué)."""
        self._evacuated = set()


__all__ = ["JuPedSimCrowd"]