"""agents.perception — la perception figée d'un instant T.

Règle v3 (architecture.md §5) : un agent ne lit jamais la vérité du monde
directement. Il lit une **perception datée**, bornée par sa position, sa
visibilité et son étage. Tous les agents perçoivent le même instant T avant
de décider.

Les signaux de danger sont des **fronts** (fumée visible, annonce,
fermeture) : la persistance par agent — le fait qu'on ne re-décide pas pour
un signal déjà vu — est gérée par la mémoire, pas par la perception.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from maree.v3.agents.state import State
from maree.v3.core.ids import AgentId, Tick, ZoneId


@dataclass(frozen=True, slots=True)
class Message:
    """Un message entendu d'un autre agent (véhicule l'influence sociale)."""

    fact: str                    # "la sortie B est praticable", "il faut évacuer"
    from_agent: AgentId
    tick: Tick
    confidence: float = 0.8      # confiance affichée par l'émetteur


@dataclass(frozen=True, slots=True)
class Perception:
    """Ce que l'agent perçoit et reçoit au tick courant (instantané figé)."""

    tick: Tick
    zone: ZoneId
    state: State
    #: signaux de danger (fronts). None = non perçu.
    smoke_visible: bool | None = None
    announcement: str | None = None
    threat: float = 0.0          # 0..1 menace perçue (bruit, densité, cri…)
    #: ce qu'on observe des autres (comportement social).
    seen_agents: tuple[AgentId, ...] = field(default_factory=tuple)
    exits_visible: frozenset = frozenset()
    #: messagers entendus à cet instant.
    heard: tuple[Message, ...] = field(default_factory=tuple)
    #: densité locale perçue (l'état courant la porte aussi).
    crowding: float = 0.0

    @property
    def has_danger_signal(self) -> bool:
        """Un signal de danger est-il perçu *maintenant* (front naissant)."""
        return bool(
            self.smoke_visible
            or self.announcement
            or self.threat > 0.0
        )


__all__ = ["Message", "Perception"]