"""agents.social — les liens sociaux d'un agent.

Le groupe n'est pas une abstraction : il a un leader éventuel, une
cohésion mesurable et un coût à se séparer (comportement.md §6).
``reunited_kin`` est la trace factuelle d'une réunion : elle sert à la
validation du phénomène P4 (cohésion du groupe).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from maree.v3.core.ids import AgentId


@dataclass(slots=True)
class SocialState:
    """Liens et observations sociales."""

    kin: set[AgentId] = field(default_factory=set)          # proches à retrouver
    reunited_kin: set[AgentId] = field(default_factory=set) # proches réunis
    group: AgentId | None = None                            # groupe de déplacement
    leader: AgentId | None = None                           # personne suivie
    trust: dict[AgentId, float] = field(default_factory=dict)
    observed: dict[AgentId, str] = field(default_factory=dict)  # comportement récent

    def mark_reunited(self, kin: AgentId) -> None:
        self.reunited_kin.add(kin)
        self.kin.discard(kin)

    def trust_of(self, agent: AgentId, default: float = 0.5) -> float:
        return self.trust.get(agent, default)

    def set_trust(self, agent: AgentId, value: float) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"confiance sociale {value} hors de 0..1")
        self.trust[agent] = value


__all__ = ["SocialState"]