"""agents.preference — quelle sortie un agent préfère, et pourquoi.

Fonction pure partagée par la décision (règles), la mesure d'émergence et le
null (mémoires brouillées). Elle vit hors de ``verify`` pour que l'agent
puisse la consulter sans importer un module de mesure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from maree.v3.agents.knowledge import Belief

if TYPE_CHECKING:
    from maree.v3.agents.agent import Agent


def preferred_from_beliefs(beliefs: Mapping[str, Belief]) -> str | None:
    """La sortie la plus confiante, en ignorant celles crues bloquées."""
    best: tuple[float, str] | None = None
    for key, belief in beliefs.items():
        if not key.startswith("exit:"):
            continue
        label = key[len("exit:"):]
        hazard = beliefs.get(f"hazard:{label}")
        if hazard is not None and hazard.confidence >= 0.5:
            continue
        if best is None or belief.confidence > best[0]:
            best = (belief.confidence, label)
    return best[1] if best else None


def preferred_exit(agent: Agent) -> str | None:
    """La sortie préférée de l'agent (la plus confiante, non crue bloquée)."""
    return preferred_from_beliefs(agent.knowledge.beliefs)


__all__ = ["preferred_exit", "preferred_from_beliefs"]
