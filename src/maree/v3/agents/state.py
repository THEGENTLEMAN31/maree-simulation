"""agents.state — l'état courant d'un agent.

Variables *courantes* (comportement.md §4) : elles changent au fil du temps
et modulent l'appraisal. Contrairement aux traits (stables) et aux
croyances (datées), l'état est un instantané : on le reconstruit chaque
tick, on ne le mute pas.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class State:
    """État courant de l'agent (toutes grandeurs normalisées sauf mention)."""

    stress: float = 0.0       # 0..1 — accélère ou fige
    fatigue: float = 0.0      # 0..1 — réduit la vitesse
    co_exposure: float = 0.0  # ppm — réduit les capacités
    visibility: float = 50.0  # m — change la direction (grandeur, pas normalisée)
    crowding: float = 0.0     # pers/m² — ralentit, stresse
    injured: bool = False     # réduit la mobilité

    def __post_init__(self) -> None:
        for name in ("stress", "fatigue", "co_exposure"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"état {name}={value} hors de 0..1")


__all__ = ["State"]