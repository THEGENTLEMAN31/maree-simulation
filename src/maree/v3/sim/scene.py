"""sim.scene — l'instant du monde perçu par les agents.

Règle v3 : tous les agents perçoivent le **même instant T** (perception
figée) avant de décider. Le ``Scene`` détient l'état courant du monde
(signaux globaux, messages adressés, positions des agents) et construit la
``Perception`` de chaque agent — bornée par son espace, sa visibilité et son
étage.

Correctif 2026-11-17 (C2) : la perception porte désormais ce que
l'architecture promettait déjà mais ne remplissait pas :

- les **voisins** visibles (les 8 plus proches, ordre déterministe) ;
- la **densité locale** (noyau circulaire de 2 m, même définition que I5) ;
- la **distance au danger** quand l'origine est connue ;
- les **sorties visibles** (distance + ligne de vue, pas de mur);
- un **état qui évolue** (stress, fatigue, co-exposition, visibilité,
  entassement) au lieu d'un ``State()`` neuf à chaque tick.

Aucune cognition ici : on ne calcule que ce que les agents *reçoivent*.
L'état est un fait du corps, pas une décision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from maree.v3.agents.agent import Agent
from maree.v3.agents.appraisal import Action
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.state import State
from maree.v3.core.ids import AgentId, ZoneId
from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.worldspec import Point

#: rayon du noyau de densité local (m) — même définition que I5 en v2.
DENSITY_RADIUS = 2.0
#: nombre maximal de voisins transmis à la cognition.
SEEN_LIMIT = 8
#: distance (m) à laquelle on distingue encore une issue sans fumée.
BASE_VISIBILITY = 50.0
#: distance (m) au-delà de laquelle un danger n'est plus « proche ».
DANGER_RANGE = 40.0
#: montée/descente maximale du stress par tick.
_STRESS_RATE = 0.25
#: décroissance du stress quand la menace baisse.
_STRESS_RELAX = 0.4
#: fatigue gagnée par mètre parcouru (1 000 m → 1,0 ; un hall se traverse en 40 m).
_FATIGUE_PER_M = 0.0015
#: convergence de la co-exposition vers sa cible (par tick).
_CO_EXPOSURE_RATE = 0.20
#: part de la visibilité perdue à co-exposition maximale.
_CO_VISIBILITY_LOSS = 0.8


@dataclass(slots=True)
class Instance:
    """Un agent dans le monde : sa position (espace) et ce qu'il a reçu."""

    agent: Agent
    space_id: str
    point: Point


@dataclass(slots=True)
class Scene:
    """L'état courant du monde vu comme source de perceptions."""

    tick: int = 0
    smoke: bool = False
    announcement: str | None = None
    instances: dict[AgentId, Instance] = field(default_factory=dict)
    #: messages adressés à un agent pour ce tick (vidés après diffusion).
    mails: dict[AgentId, list[Message]] = field(default_factory=dict)
    navgraph: NavigationGraph | None = None
    #: position physique du dernier pas (None ⇒ point de spawn).
    positions: dict[AgentId, Point] = field(default_factory=dict)
    #: origine du danger (fumée/feu) si connue : la distance est perçue.
    hazard_origin: Point | None = None
    #: sorties fermées dans le monde (front perceptible).
    closed_exits: set[str] = field(default_factory=set)
    #: vrai quand un moteur physique alimente les positions (C1).
    physics_active: bool = False
    #: (tick calculé, état, position) — l'état évolue, il ne se réinitialise pas.
    _states: dict[AgentId, tuple[int, State, Point]] = field(default_factory=dict)
    #: intention de chaque agent en tête de tick (perception figée : on ne lit
    #: jamais une décision prise plus tard dans le même tick).
    _decisions_snapshot: dict[AgentId, tuple[Action, str | None] | None] = field(
        default_factory=dict
    )

    # --- alimentation par le moteur ---
    def add(self, agent: Agent, space_id: str, point: Point) -> None:
        self.instances[agent.uid] = Instance(agent, space_id, point)

    def update_positions(self, positions: dict[int, Point]) -> None:
        """Recopie les positions physiques du dernier pas (source du corps).

        Appelé **en tête de tick**, avant toute perception : tous les agents
        voient donc le même instant. Les agents sortis ne sont plus dans
        ``positions`` ; on garde leur dernière position connue.

        On fige aussi les **intentions** courantes : un agent ne doit pas voir
        la décision qu'un autre vient de prendre plus tard dans le même tick.
        """
        for raw_uid, point in positions.items():
            agent_id = AgentId(raw_uid)
            self.positions[agent_id] = point
            inst = self.instances.get(agent_id)
            if inst is not None:
                inst.point = point
        self._decisions_snapshot = {}
        for agent_id, inst in self.instances.items():
            decision = inst.agent._last_decision
            self._decisions_snapshot[agent_id] = (
                None
                if decision is None
                else (decision.action, decision.target)
            )

    def position_of(self, agent_id: AgentId) -> Point:
        """Position courante (physique si connue, sinon point de spawn)."""
        known = self.positions.get(agent_id)
        if known is not None:
            return known
        return self.instances[agent_id].point

    # --- construction de la perception ---
    def perception_for(self, agent_id: AgentId) -> Perception:
        inst = self.instances[agent_id]
        position = self.position_of(agent_id)
        state = self._advance_state(agent_id, position)
        # le corps reçoit l'état perçu : vitesse, fatigue, visibilité.
        inst.agent.state = state
        distance = self._distance_to_danger(position)
        level = self._level_of(inst.space_id)
        seen = self._seen_agents(agent_id, position, state.visibility)
        return Perception(
            tick=self.tick,
            zone=ZoneId(inst.space_id),
            state=state,
            smoke_visible=self.smoke,
            announcement=self.announcement,
            threat=self._threat(distance),
            distance_to_danger=distance,
            heard=tuple(self.mails.get(agent_id, ())),
            seen_agents=seen,
            exits_visible=self._visible_exits(position, level, state.visibility),
            crowding=state.crowding,
            position=position if self.physics_active else None,
            closed_exits=frozenset(sorted(self.closed_exits)),
            seen_leaving_elsewhere=self._leaving_elsewhere(agent_id, seen),
        )

    def drain(self, agent_id: AgentId) -> None:
        """Vide la boîte aux lettres de l'agent (les messages ont été lus)."""
        self.mails.pop(agent_id, None)

    # --- voisins, densité, sorties ---
    def _active_points(self, exclude: AgentId) -> list[Point]:
        return [
            self.position_of(other)
            for other in sorted(self.instances, key=lambda a: a.uid)
            if other != exclude
        ]

    def _seen_agents(
        self, agent_id: AgentId, position: Point, visibility: float
    ) -> tuple[AgentId, ...]:
        """Les ``SEEN_LIMIT`` agents les plus proches, à portée de vue.

        Ordre déterministe (distance, puis ``uid``) : deux runs identiques
        produisent la même liste, et le client peut la rejouer.
        """
        ranked: list[tuple[float, int, AgentId]] = []
        for other in self.instances:
            if other == agent_id:
                continue
            other_pos = self.position_of(other)
            distance = math.dist(position, other_pos)
            if distance <= visibility:
                ranked.append((distance, other.uid, other))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return tuple(other for _dist, _uid, other in ranked[:SEEN_LIMIT])

    def _leaving_elsewhere(
        self, agent_id: AgentId, seen: tuple[AgentId, ...]
    ) -> int:
        """Combien de voisins partent vers une sortie **différente** de la mienne.

        Lecture du snapshot de début de tick : la perception ne dépend pas de
        l'ordre dans lequel les agents décident. C'est ce qui permet de voir
        « six personnes font demi-tour » sans casser la barrière de tick.
        """
        own = self._decisions_snapshot.get(agent_id)
        own_target = own[1] if own is not None else None
        count = 0
        for other in seen:
            decision = self._decisions_snapshot.get(other)
            if decision is None:
                continue
            action, target = decision
            if action is Action.EVACUER and target and target != own_target:
                count += 1
        return count

    def _crowding(self, agent_id: AgentId, position: Point) -> float:
        """Densité locale, noyau circulaire de ``DENSITY_RADIUS`` (pers/m²).

        Même définition que l'indicateur I5 : compter les voisins à moins de
        2 m et diviser par l'aire du disque. Une grille de 1 m saturait à 2
        agents par cellule ; le noyau, lui, varie.
        """
        area = math.pi * DENSITY_RADIUS * DENSITY_RADIUS
        radius_sq = DENSITY_RADIUS * DENSITY_RADIUS
        neighbours = sum(
            1
            for other in self._active_points(agent_id)
            if (other[0] - position[0]) ** 2 + (other[1] - position[1]) ** 2
            <= radius_sq
        )
        return neighbours / area

    def _distance_to_danger(self, position: Point) -> float | None:
        """Distance au foyer, si l'origine est connue et la fumée visible."""
        if not self.smoke or self.hazard_origin is None:
            return None
        return math.dist(position, self.hazard_origin)

    def _threat(self, distance: float | None) -> float:
        """Menace perçue : la fumée seule vaut 0,6 ; la distance la module."""
        if not self.smoke:
            return 0.0
        if distance is None:
            return 0.6
        proximity = max(0.0, min(1.0, 1.0 - distance / DANGER_RANGE))
        return 0.25 + 0.75 * proximity

    def _level_of(self, space_id: str) -> str:
        if self.navgraph is not None:
            level = self.navgraph.level_of_space(space_id)
            if level is not None:
                return level
        return space_id

    def _visible_exits(
        self, position: Point, level: str, visibility: float
    ) -> frozenset[str]:
        """Sorties à portée de vue **et** sans mur entre l'agent et l'issue."""
        if self.navgraph is None:
            return frozenset()
        try:
            spec = self.navgraph.world.level(level)
        except KeyError:
            return frozenset()
        visible: set[str] = set()
        for exit_spec in spec.exits:
            (x1, y1), (x2, y2) = exit_spec.segment
            midpoint = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            if math.dist(position, midpoint) > visibility:
                continue
            if self.navgraph.line_of_sight(position, midpoint, level):
                visible.add(exit_spec.id)
        return frozenset(sorted(visible))

    # --- évolution de l'état ---
    def _advance_state(self, agent_id: AgentId, position: Point) -> State:
        """Fait évoluer l'état du corps (idempotent dans un même tick)."""
        cached = self._states.get(agent_id)
        if cached is not None and cached[0] == self.tick:
            return cached[1]
        previous = cached[1] if cached is not None else State()
        previous_position = cached[2] if cached is not None else position
        moved = math.dist(previous_position, position)

        crowding = self._crowding(agent_id, position)
        distance = self._distance_to_danger(position)
        proximity = (
            0.0
            if distance is None
            else max(0.0, min(1.0, 1.0 - distance / DANGER_RANGE))
        )

        fatigue = min(1.0, previous.fatigue + _FATIGUE_PER_M * moved)
        stress_target = min(
            1.0, 0.55 * proximity + 0.35 * min(1.0, crowding / 2.0)
        )
        if stress_target >= previous.stress:
            stress = min(stress_target, previous.stress + _STRESS_RATE)
        else:
            stress = max(stress_target, previous.stress - _STRESS_RATE * _STRESS_RELAX)

        co_target = (0.2 + 0.6 * proximity) if self.smoke else 0.0
        co_exposure = previous.co_exposure + _CO_EXPOSURE_RATE * (
            co_target - previous.co_exposure
        )
        co_exposure = max(0.0, min(1.0, co_exposure))
        visibility = BASE_VISIBILITY * (1.0 - _CO_VISIBILITY_LOSS * co_exposure)

        state = State(
            stress=stress,
            fatigue=fatigue,
            co_exposure=co_exposure,
            visibility=visibility,
            crowding=crowding,
            injured=previous.injured,
        )
        self._states[agent_id] = (self.tick, state, position)
        return state


__all__ = ["Instance", "Scene"]
