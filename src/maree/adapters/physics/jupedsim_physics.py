"""Physique de foule — JuPedSim 1.4.

Mesures du spike (RTX 3050 non sollicitée, CPU seul) :

    60 agents x 2 000 pas (100 s simulées) : 0,06 s mural  -> 1 761x temps réel
    60 agents, SocialForceModel            : 0,07 s mural  -> 1 353x temps réel
    déterminisme (12 agents, 200 pas)      : positions identiques à 1e-9

Conclusion : **la foule n'est pas le coût**. Soixante agents, ou trois
cents, ne changent rien à la facture. Le seul poste qui coûte est l'appel
LLM. C'est cette mesure qui justifie l'architecture à trois horloges.

Deux modèles disponibles, et le choix n'est pas cosmétique :

    CollisionFreeSpeedModel   rapide, files réalistes, modèle « ingénieur »
    SocialForceModel          Helbing & Molnár 1995 — celui que cite le
                              cahier des charges, avec les forces sociales

Le second est le bras « modèle classique » de la comparaison du sujet.
"""

from __future__ import annotations

import math
from typing import Any

import jupedsim as jps
import shapely

from maree.domain.geometry import Plan
from maree.domain.ids import AgentId, ExitId, Point
from maree.ports import Destination

#: Distance minimale d'un agent aux parois (le rayon du modèle).
WALL_MARGIN = 0.25

_MODELS: dict[str, Any] = {
    "collision_free": jps.CollisionFreeSpeedModel,
    "social_force": jps.SocialForceModel,
}


class JuPedSimPhysics:
    def __init__(
        self,
        plan: Plan,
        *,
        dt: float = 0.05,
        seed: int = 0,
        model: str = "collision_free",
        desired_speed: float = 1.2,
    ) -> None:
        self._plan = plan
        self._dt = dt
        self._seed = seed
        self._desired_speed = desired_speed
        self._model_name = model
        self._centroid = self._walkable_centroid()

        model_factory = _MODELS.get(model)
        if model_factory is None:
            raise ValueError(f"modèle inconnu : {model!r} (attendu {sorted(_MODELS)})")
        self._model = model_factory()
        self._geometry = self._build_geometry()
        self._sim = jps.Simulation(
            model=self._model,
            geometry=self._geometry,
            dt=dt,
            seed=seed,
        )
        # CollisionFreeSpeedModel -> CollisionFreeSpeedModelAgentParameters
        self._params = getattr(jps, type(self._model).__name__ + "AgentParameters")

        # --- issues et voyages -----------------------------------
        self._exit_stage: dict[ExitId, int] = {}
        self._exit_journey: dict[ExitId, int] = {}
        for exit_id, exit_ in plan.exits.items():
            polygon = shapely.Polygon(exit_.stage_polygon(self._centroid))
            stage = self._sim.add_exit_stage(polygon)
            self._exit_stage[exit_id] = stage
            self._exit_journey[exit_id] = self._sim.add_journey(
                jps.JourneyDescription([stage])
            )

        # --- points (waypoints) ----------------------------------
        self._point_stage: dict[tuple[float, float], int] = {}
        self._point_journey: dict[tuple[float, float], int] = {}
        self._barrier_journey: dict[ExitId, int] = {}

        # --- suivi ------------------------------------------------
        self._jps_id: dict[AgentId, int] = {}
        self._agent_of: dict[int, AgentId] = {}
        self._target: dict[AgentId, Destination] = {}
        self._closed: set[ExitId] = set()

    # ---- utilitaires ------------------------------------------
    def _build_geometry(self) -> shapely.Polygon:
        """Domaine marchable, obstacles percés en trous.

        Les obstacles ne sont pas décoratifs : sans eux, les agents
        traversent la scène et les stands, et la densité mesurée au
        goulot ne veut plus rien dire. Le plan YAML est la seule source.
        """
        shell = shapely.Polygon(self._plan.walkable)
        holes = [list(o.polygon) for o in self._plan.obstacles]
        return shapely.Polygon(shell.exterior, holes)

    def _walkable_centroid(self) -> Point:
        pts = self._plan.walkable
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    def _journey_for(self, destination: Destination) -> tuple[int, int]:
        """Retourne (journey_id, stage_id) pour une destination."""
        if destination.kind == "exit" and destination.exit_id:
            exit_id = destination.exit_id
            return self._exit_journey[exit_id], self._exit_stage[exit_id]
        if destination.kind == "point" and destination.point:
            # Un waypoint doit être dans le domaine : un point de spawn
            # peut tomber dans un stand ou une paroi, et JuPedSim refuse.
            safe = self._safe_position(destination.point)
            key = (round(safe[0], 1), round(safe[1], 1))
            if key not in self._point_journey:
                stage = self._sim.add_waypoint_stage(key, 0.4)
                self._point_stage[key] = stage
                self._point_journey[key] = self._sim.add_journey(
                    jps.JourneyDescription([stage])
                )
            return self._point_journey[key], self._point_stage[key]
        if destination.kind == "agent" and destination.agent_id:
            # Suivi : on vise la position ACTUELLE du meneur. Le suiveur
            # re-décidera au prochain déclencheur ; ce n'est pas un
            # rattachement dynamique permanent (limite assumée).
            leader = self._target.get(destination.agent_id)
            position = self.positions().get(destination.agent_id)
            if position is not None:
                return self._journey_for(Destination.to_point(position))
            _ = leader
        # Repli : rester sur place.
        return self._journey_for(Destination.to_point(self._centroid))

    def _safe_position(self, position: Point) -> Point:
        """Écarte un point de spawn des parois et des obstacles."""
        x, y = position
        cx, cy = self._centroid
        for _ in range(10):
            if self._geometry.buffer(-WALL_MARGIN).contains(shapely.Point(x, y)):
                return (x, y)
            x += (cx - x) * 0.08
            y += (cy - y) * 0.08
        return (cx, cy)

    def _place(self, position: Point, journey: int, stage: int) -> int:
        """Place un agent, en spirale déterministe si la place est prise.

        JuPedSim refuse deux agents à moins de 0,4 m et tout point à
        moins de 0,2 m d'une paroi. Un spawn aléatoire échouerait donc
        une fois sur dix ; on n'attrape pas l'exception, on cherche une
        place libre — toujours dans le même ordre.
        """
        base = self._safe_position(position)
        last: RuntimeError | None = None
        for attempt in range(48):
            if attempt == 0:
                candidate = base
            else:
                angle = attempt * 2.399963  # ~angle d'or, déterministe
                radius = 0.35 * math.sqrt(attempt)
                candidate = (
                    base[0] + radius * math.cos(angle),
                    base[1] + radius * math.sin(angle),
                )
            if not self._geometry.buffer(-WALL_MARGIN).contains(
                shapely.Point(candidate[0], candidate[1])
            ):
                continue
            try:
                return self._sim.add_agent(
                    self._params(
                        position=candidate,
                        journey_id=journey,
                        stage_id=stage,
                        desired_speed=self._desired_speed,
                    )
                )
            except RuntimeError as exc:  # place occupée
                last = exc
        raise RuntimeError(
            f"impossible de placer l'agent près de {position} : {last}"
        )

    # ---- CrowdPhysics -----------------------------------------
    def add_agent(
        self, agent_id: AgentId, position: Point, destination: Destination
    ) -> None:
        journey, stage = self._journey_for(destination)
        jps_id = self._place(position, journey, stage)
        self._jps_id[agent_id] = jps_id
        self._agent_of[jps_id] = agent_id
        self._target[agent_id] = destination

    def set_destination(self, agent_id: AgentId, destination: Destination) -> None:
        jps_id = self._jps_id.get(agent_id)
        if jps_id is None:
            return
        # L'agent a pu franchir une issue depuis la dernière décision :
        # JuPedSim l'a alors retiré et `switch_agent_journey` lèverait
        # « Trying to access unknown Agent ». Ce n'est pas une erreur,
        # c'est la fin de son parcours.
        if jps_id not in self._alive_ids():
            return
        if destination.kind == "exit" and destination.exit_id in self._closed:
            destination = self._barrier(destination.exit_id)
        journey, stage = self._journey_for(destination)
        self._target[agent_id] = destination
        self._sim.switch_agent_journey(jps_id, journey, stage)

    def _alive_ids(self) -> set[int]:
        return {a.id for a in self._sim.agents()}

    def remove_agent(self, agent_id: AgentId) -> None:
        jps_id = self._jps_id.pop(agent_id, None)
        if jps_id is not None:
            self._sim.mark_agent_for_removal(jps_id)
            self._agent_of.pop(jps_id, None)
        self._target.pop(agent_id, None)

    def step(self) -> None:
        self._sim.iterate()

    def positions(self) -> dict[AgentId, Point]:
        out: dict[AgentId, Point] = {}
        for agent_id, jps_id in self._jps_id.items():
            try:
                position = self._sim.agent(jps_id).position
            except (RuntimeError, KeyError):
                continue
            out[agent_id] = (float(position[0]), float(position[1]))
        return out

    def evacuated(self) -> set[AgentId]:
        """Agents sortis : JuPedSim les retire après le franchissement."""
        alive = {a.id for a in self._sim.agents()}
        return {
            agent_id
            for agent_id, jps_id in self._jps_id.items()
            if jps_id not in alive
        }

    def close_exit(self, exit_id: ExitId) -> None:
        """Ferme une issue : les agents qui y allaient sont arrêtés devant.

        On ne détruit pas l'issue (JuPedSim ne le permet pas proprement) :
        on redirige vers un point d'arrêt situé 1,5 m à l'intérieur. Les
        agents s'y accumulent, ce qui est exactement le comportement
        observé quand une grille tombe — et ce que le rejeu doit montrer.
        """
        self._closed.add(exit_id)
        for agent_id, target in list(self._target.items()):
            if target.kind == "exit" and target.exit_id == exit_id:
                self.set_destination(agent_id, self._barrier(exit_id))

    def _barrier(self, exit_id: ExitId) -> Destination:
        exit_ = self._plan.exit(exit_id)
        cx, cy = exit_.center
        nx, ny = exit_.normal
        ox, oy = self._centroid
        if (ox - cx) * nx + (oy - cy) * ny < 0:
            nx, ny = -nx, -ny
        return Destination.to_point((cx + nx * 1.5, cy + ny * 1.5))

    @property
    def agent_count(self) -> int:
        return self._sim.agent_count()

    @property
    def elapsed_s(self) -> float:
        return float(self._sim.elapsed_time())

    def neighbours(self, position: Point, radius: float) -> list[AgentId]:
        """Requête spatiale déléguée au moteur (bien plus rapide qu'en Python)."""
        try:
            found = self._sim.agents_in_range(position, radius)
        except (RuntimeError, AttributeError):
            return []
        return [self._agent_of[a.id] for a in found if a.id in self._agent_of]

    def density_at(self, position: Point, radius: float) -> float:
        return len(self.neighbours(position, radius)) / (math.pi * radius**2)
