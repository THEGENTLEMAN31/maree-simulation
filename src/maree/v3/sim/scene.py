"""sim.scene — l'instant du monde perçu par les agents.

Règle v3 : tous les agents perçoivent le **même instant T** (perception
figée) avant de décider. Le ``Scene`` détient l'état courant du monde
(signaux globaux, messages adressés, positions des agents) et construit la
``Perception`` de chaque agent — bornée par son espace et son étage.
(Aucune cognition ici : on ne manipule que ce que les agents *reçoivent*.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from maree.v3.agents.agent import Agent
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.state import State
from maree.v3.core.ids import AgentId, ZoneId
from maree.v3.world.navgraph import NavigationGraph


@dataclass(slots=True)
class Instance:
    """Un agent dans le monde : sa position (espace) et ce qu'il a reçu."""

    agent: Agent
    space_id: str
    point: tuple[float, float]


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

    def add(self, agent: Agent, space_id: str, point: tuple[float, float]) -> None:
        self.instances[agent.uid] = Instance(agent, space_id, point)

    def perception_for(self, agent_id: AgentId) -> Perception:
        inst = self.instances[agent_id]
        return Perception(
            tick=self.tick,
            zone=ZoneId(inst.space_id),
            state=State(),
            smoke_visible=self.smoke,
            announcement=self.announcement,
            threat=(0.6 if self.smoke else 0.0),
            heard=tuple(self.mails.get(agent_id, ())),
            seen_agents=(),
            exits_visible=frozenset(),
        )

    def drain(self, agent_id: AgentId) -> None:
        """Vide la boîte aux lettres de l'agent (les messages ont été lus)."""
        self.mails.pop(agent_id, None)


__all__ = ["Instance", "Scene"]