"""Croyances d'un agent : ce qu'il pense savoir, et à quel point.

Trois choses distinctes, souvent confondues :

    la réalité      l'état du monde (sortie ouverte/fermée) — vérité terrain
    la croyance     ce que l'agent pense (sortie → confiance)
    la source       d'où il le tient (RAG, message, observation)

L'écart entre les deux premières est **le sujet du projet**. Il est
mesurable : c'est l'indicateur I6.

La confiance décroît si rien ne la renforce. C'est ce qui fait basculer
un agent quand ses yeux contredisent ce qu'il croyait.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from maree.domain.ids import ExitId


def entropy(probs: Iterable[float]) -> float:
    """Entropie de Shannon en nats. 0 = certitude, log(n) = ignorance totale."""
    values = [p for p in probs if p > 0]
    if not values:
        return 0.0
    return -sum(p * math.log(p) for p in values)


@dataclass(frozen=True, slots=True)
class ExitBelief:
    """Une croyance sur une sortie, datée et sourcée (décision 12)."""

    exit_id: ExitId
    confidence: float  # 0..1
    source: str  # "rag:#42" | "entendu:A19" | "vu" | "inconnu"
    tick: int

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confiance hors [0,1] : {self.confidence}")


@dataclass(slots=True)
class BeliefTable:
    """État de croyance d'un agent. Jamais partagé entre agents."""

    exits: dict[ExitId, ExitBelief] = field(default_factory=dict)
    danger: float = 0.0  # 0 = rien, 1 = danger certain
    danger_source: str = "inconnu"

    # ---- lecture ----------------------------------------------
    def confidence(self, exit_id: ExitId) -> float:
        belief = self.exits.get(exit_id)
        return belief.confidence if belief else 0.0

    def best(self) -> ExitId | None:
        """Sortie crue la plus sûre, ou None si aucune croyance."""
        if not self.exits:
            return None
        return max(self.exits, key=lambda e: self.exits[e].confidence)

    def distribution(self, n_exits: int | None = None) -> dict[ExitId, float]:
        """Distribution normalisée. Sans croyance : uniforme (ignorance)."""
        total = sum(b.confidence for b in self.exits.values())
        if total <= 0:
            n = n_exits or max(len(self.exits), 1)
            return {e: 1.0 / n for e in self.exits} if self.exits else {}
        return {e: b.confidence / total for e, b in self.exits.items()}

    def entropy(self, n_exits: int | None = None) -> float:
        """I2 : incertitude de l'agent. Max quand il ne sait rien."""
        if not self.exits:
            return math.log(n_exits) if n_exits and n_exits > 1 else 0.0
        return entropy(self.distribution(n_exits).values())

    # ---- écriture ---------------------------------------------
    def set(self, exit_id: ExitId, confidence: float, source: str, tick: int) -> None:
        self.exits[exit_id] = ExitBelief(
            exit_id=exit_id,
            confidence=max(0.0, min(1.0, confidence)),
            source=source,
            tick=tick,
        )

    def reinforce(self, exit_id: ExitId, delta: float, source: str, tick: int) -> None:
        self.set(exit_id, self.confidence(exit_id) + delta, source, tick)

    def decay(self, factor: float = 0.85, floor: float = 0.0) -> None:
        """Oubli : une croyance non renforcée perd de l'assurance."""
        for exit_id, belief in list(self.exits.items()):
            new = max(floor, belief.confidence * factor)
            self.exits[exit_id] = ExitBelief(
                exit_id=exit_id,
                confidence=new,
                source=belief.source,
                tick=belief.tick,
            )

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {
            e: {"confidence": round(b.confidence, 4), "source": b.source, "tick": b.tick}
            for e, b in self.exits.items()
        }
