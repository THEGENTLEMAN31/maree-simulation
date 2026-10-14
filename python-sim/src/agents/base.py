"""Interface uniforme des agents (décision 6, exigences A6 et E1)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Perception:
    """Ce qu'un agent perçoit à un instant donné (figé à la décision, C6).

    Ne contient JAMAIS d'information produite après le tick de décision
    (vérifié par l'oracle de cohérence temporelle, I5).
    """

    tick: int
    zone: str
    smoke_seen: bool
    visible_neighbors: list[str] = field(default_factory=list)
    announcements: list[str] = field(default_factory=list)
    false_infos: list[str] = field(default_factory=list)
    exits_known: list[str] = field(default_factory=list)  # sorties connues du profil


@dataclass
class Intention:
    """Intention décidée par l'agent (décision 8 : le moteur exécute, seul).

    Le moteur de déplacement exécute les intentions — c'est la frontière
    boucle rapide / boucle lente qui permet de passer du graphe au continu.
    """

    action: str  # "move" | "stay" | "evacuate"
    target_zone: str | None = None
    exit_code: str | None = None
    belief_safe_exit: str | None = None
    belief_danger: bool | None = None

    @property
    def is_evacuation(self) -> bool:
        return self.action == "evacuate"


class Agent(ABC):
    """Contrat commun à tout agent (LLM ou règles)."""

    agent_id: str
    profile_name: str

    def __init__(self, agent_id: str, profile_name: str) -> None:
        self.agent_id = agent_id
        self.profile_name = profile_name

    @abstractmethod
    async def decide(self, perception: Perception) -> Intention:
        """Décide d'une intention à partir de sa perception et de sa mémoire.

        La mémoire est consommée en interne par l'agent ; l'interface reste
        uniforme pour permettre la comparaison LLM / règles (E1, A6).
        """
        raise NotImplementedError

    def fallback_intention(self, perception: Perception) -> Intention:
        """Intention de repli en cas d'échec LLM (A4, décision 7)."""
        # Comportement prudent : rester sur place.
        return Intention(action="stay", target_zone=perception.zone)


# Vues courtes pour le typage et la documentation.
LegacyLikelihoodSource = Literal["llm", "rules"]