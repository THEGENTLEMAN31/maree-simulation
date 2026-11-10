"""core.ids — identifiants typés et temps de la v3.

Le temps est un entier (tick) : aucune horloge système dans la logique du
monde (convention v3 non négociable). Les identifiants sont typés pour
éviter les confusions (agent / sortie / zone / événement).

Aucune règle métier ici.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Le temps du monde est un entier non signé (tick).
Tick = int


@dataclass(frozen=True, slots=True)
class AgentId:
    """Identité unique d'un agent dans un run."""

    uid: int

    def __str__(self) -> str:  # pragma: no cover - trivialité de rendu
        return f"A{self.uid:02d}"


@dataclass(frozen=True, slots=True)
class ExitId:
    """Identité d'une sortie du plan."""

    uid: str

    def __str__(self) -> str:  # pragma: no cover - trivialité de rendu
        return self.uid


@dataclass(frozen=True, slots=True)
class ZoneId:
    """Identité d'une zone du plan (pièce, couloir, étage…)."""

    uid: str

    def __str__(self) -> str:  # pragma: no cover - trivialité de rendu
        return self.uid


__all__ = ["AgentId", "ExitId", "Tick", "ZoneId"]