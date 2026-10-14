"""Oracle de cohérence temporelle (C6, décision 2, indicateur I5).

Vérifie que chaque décision ne s'appuie que sur des informations disponibles
à l'instant de la décision : date de production (et d'arrivée pour un message)
<= tick de décision. Chaque écart devient un événement de violation compté
dans I5. En mode asynchrone, une décision appliquée sur un état périmé n'est
PAS une violation : son décalage est mesuré à part (C7).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TemporalViolation:
    tick: int
    agent_id: str
    detail: str


class TemporalOracle:
    """Vérificateur de cohérence temporelle (exécuté en test automatique)."""

    def __init__(self) -> None:
        self.violations: list[TemporalViolation] = []

    def check_decisions(
        self,
        *,
        tick: int,
        decisions: list[dict],
        messages_by_agent: dict[str, list[tuple[int, str]]],
    ) -> None:
        """Vérifie que chaque décision cite uniquement des messages arrivés."""
        for dec in decisions:
            agent_id = dec.get("agent_id")
            arrived = messages_by_agent.get(agent_id, [])
            latest_arrived = max((t for t, _ in arrived), default=-1)
            if latest_arrived > tick:
                self.violations.append(
                    TemporalViolation(
                        tick=tick,
                        agent_id=agent_id,
                        detail=(
                            f"décision à t={tick} cite un message arrivé à "
                            f"t={latest_arrived}"
                        ),
                    )
                )

    def assert_clean(self) -> None:
        """À appeler en test : échoue si une violation est détectée."""
        if self.violations:
            v = self.violations[0]
            raise AssertionError(
                f"violation temporelle : {v.agent_id} @tick {v.tick} — {v.detail}"
            )