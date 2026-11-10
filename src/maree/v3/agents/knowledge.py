"""agents.knowledge — la connaissance individuelle, datée et sourcée.

Chaque croyance porte **sa source** et **son tick** (comportement.md §5).
C'est ce qui rend une décision auditable :
« il croyait B à 0,7, parce que A12 le lui a dit à t=12, et il ne l'a pas
vérifié ».
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from maree.v3.core.ids import ExitId, Tick, ZoneId


class Source(Enum):
    """Origine d'une croyance. Le vocabulaire reste en français du domaine."""

    CONNU = "connu"          # savoir initial du profil
    VU = "vu"                # observation directe
    ENTENDU = "entendu"      # message d'un autre agent
    ANNONCE = "annonce"      # annonce officielle
    GUIDE = "guide"          # consigne d'un agent de sécurité
    RAG = "rag"              # passage du corpus
    RUMEUR = "rumeur"        # information non vérifiée


@dataclass(frozen=True, slots=True)
class Belief:
    """Une croyance : un fait, sa confiance, sa source et son tick."""

    fact: str
    confidence: float   # 0..1
    source: Source
    tick: Tick

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confiance {self.confidence} hors de 0..1")


@dataclass(slots=True)
class Knowledge:
    """La base de croyances d'un agent.

    ``beliefs`` indexe un fait par sa clé textuelle — pour les sorties on
    utilise conventionnellement ``exit:<ExitId>`` ; pour les zones
    ``hazard:<ZoneId>`` (fumée, chaleur, blocage). On garde aussi une note
    de route libre ``route:<nom>``.
    """

    beliefs: dict[str, Belief] = field(default_factory=dict)

    def known_keys(self) -> set[str]:
        return set(self.beliefs)

    def set(self, key: str, belief: Belief) -> None:
        self.beliefs[key] = belief

    def get(self, key: str) -> Belief | None:
        return self.beliefs.get(key)

    def exit_belief(self, exit_id: ExitId) -> Belief | None:
        return self.beliefs.get(f"exit:{exit_id}")

    def hazard_belief(self, zone_id: ZoneId) -> Belief | None:
        return self.beliefs.get(f"hazard:{zone_id}")

    def decay(self, factor: float, tick: Tick, floor: float = 0.0) -> None:
        """Oubli : atténue la confiance des croyances non renforcées.

        ``factor`` ∈ 0..1 : 1 = rien ne change, 0 = effacement immédiat.
        Une croyance qui tombe sous ``floor`` est retirée.
        """
        if not 0.0 <= factor <= 1.0:
            raise ValueError(f"facteur d'oubli {factor} hors de 0..1")
        survivors: dict[str, Belief] = {}
        for key, b in self.beliefs.items():
            new_conf = b.confidence * factor
            if new_conf >= floor:
                survivors[key] = Belief(b.fact, new_conf, b.source, tick)
        self.beliefs = survivors


__all__ = ["Belief", "Knowledge", "Source"]