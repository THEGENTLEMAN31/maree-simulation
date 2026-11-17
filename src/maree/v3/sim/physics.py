"""sim.physics — le port ``CrowdPhysics`` : le corps bouge vite.

Le moteur n'exécute que des **intentions** (frontière boucle rapide / boucle
lente). Le LLM met à jour l'intention quand il a fini de réfléchir ; la
physique, elle, avance à chaque pas. Aucun agent n'est téléporté : la
position évolue en continu dans le polygone marchable.

Implémentations :
- ``JuPedSimCrowd`` (adapters/physics.py) : le vrai moteur éprouvé (B) ;
- aucune en mémoire ici — le port suffit aux tests qui n'en ont pas besoin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from maree.v3.world.worldspec import Point


@dataclass(frozen=True, slots=True)
class Target:
    """L'intention d'un agent pour le corps : sortie, point, ou rester.

    ``stay`` ne porte **pas** de point : l'adaptateur le résout sur la
    position **courante** de l'agent (leçon 2026-11-17 : sans cela, « rester »
    envoyait tout le monde vers l'origine du repère).
    """

    kind: Literal["exit", "stay", "point"]
    exit_id: str | None = None
    point: Point | None = None

    @classmethod
    def exit(cls, exit_id: str) -> Target:
        return cls("exit", exit_id=exit_id)

    @classmethod
    def stay(cls) -> Target:
        return cls("stay")

    @classmethod
    def at(cls, point: Point) -> Target:
        """Aller vers un point (chercher de l'information, rejoindre un proche)."""
        return cls("point", point=point)


class CrowdPhysics(Protocol):
    """Ce que le moteur de déplacement exige (indépendant de JuPedSim)."""

    def spawn(self, tag: int, position: Point, desired_speed: float) -> None: ...
    def set_intention(self, tag: int, target: Target) -> None: ...
    def advance(self, steps: int = 1) -> None: ...
    def positions(self) -> dict[int, Point]: ...
    def evacuated(self) -> set[int]: ...
    def close(self) -> None: ...


__all__ = ["CrowdPhysics", "Target"]