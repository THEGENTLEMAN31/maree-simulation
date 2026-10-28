"""Intentions : ce qu'un agent a décidé de faire.

L'interface `decide(perception) -> Intention` est la même pour les agents
LLM et pour les agents à règles (décision 6). C'est ce qui rend la
comparaison X4 possible : deux moteurs, un seul contrat.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IntentionKind(StrEnum):
    GO_EXIT = "go_exit"  # rejoindre une sortie
    GO_ZONE = "go_zone"  # rejoindre une zone (observer, se regrouper)
    FOLLOW = "follow"  # suivre un agent jugé fiable
    SEARCH = "search"  # chercher un proche
    GUIDE = "guide"  # orienter les autres (sécurité)
    STAY = "stay"  # ne pas bouger


@dataclass(frozen=True, slots=True)
class Intention:
    kind: IntentionKind
    target: str | None
    reason: str
    tick: int
    confidence: float = 0.0

    def describe(self) -> str:
        match self.kind:
            case IntentionKind.GO_EXIT:
                return f"aller vers la sortie {self.target}"
            case IntentionKind.GO_ZONE:
                return f"aller vers {self.target}"
            case IntentionKind.FOLLOW:
                return f"suivre {self.target}"
            case IntentionKind.SEARCH:
                return f"chercher {self.target}"
            case IntentionKind.GUIDE:
                return "guider les autres"
            case _:
                return "rester sur place"

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": str(self.kind),
            "target": self.target,
            "reason": self.reason,
            "tick": self.tick,
            "confidence": round(self.confidence, 4),
        }
