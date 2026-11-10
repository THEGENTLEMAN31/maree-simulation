"""agents.memory — la mémoire individuelle (épisodes, reçus, consolidation).

C'est le levier central de la mission 1 : deux agents du même archétype
partagent les traits et la connaissance *partagée*, mais leurs **mémoires
personnelles** (épisodes et reçus) divergent. L'appraisal lit ces reçus,
c'est ce qui rend la divergence *explicable*.

Règles (comportement.md §8) :
- consolidation **déterministe** (jamais par LLM) : le rejeu doit être exact ;
- une croyance porte fact, source, tick, confiance, et l'id de l'événement
  dont elle dérive ;
- on mémorise aussi les **fronts de signal** vus (fumée, annonce, fermeture)
  pour ne pas re-décider à chaque tick pour un signal déjà connu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from maree.v3.agents.knowledge import Source
from maree.v3.core.ids import Tick


class EpisodeKind(Enum):
    """Les cinq types d'épisode mémorisé (comportement.md §8.2)."""

    VU = "vu"
    ENTENDU = "entendu"
    DIT = "dit"
    DECIDE = "decide"
    RESUME = "resume"


@dataclass(frozen=True, slots=True)
class Episode:
    """Un épisode enregistré par l'agent."""

    tick: Tick
    kind: EpisodeKind
    content: str
    source: str
    salience: float    # 0..1


@dataclass(frozen=True, slots=True)
class Receipt:
    """Le reçu d'un apprentissage (comportement.md §8.3)."""

    fact: str
    source: Source
    tick: Tick
    confidence: float
    derived_from: str | None = None  # id d'événement du journal

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confiance {self.confidence} hors de 0..1")


@dataclass(slots=True)
class Memory:
    """La mémoire individuelle d'un agent."""

    episodes: list[Episode] = field(default_factory=list)
    receipts: dict[str, Receipt] = field(default_factory=dict)
    #: fronts de signal déjà vus : (genre, valeur). Empêche la re-décision
    #: pour un signal déjà mémorisé.
    signals_seen: set[tuple[str, str | int | bool]] = field(default_factory=set)
    consolidated_at: Tick = 0

    def log_episode(
        self,
        tick: Tick,
        kind: EpisodeKind,
        content: str,
        source: str,
        salience: float = 0.5,
    ) -> None:
        if not 0.0 <= salience <= 1.0:
            raise ValueError(f"saillance {salience} hors de 0..1")
        self.episodes.append(
            Episode(tick, kind, content, source, salience)
        )

    def learn(
        self,
        fact: str,
        source: Source,
        tick: Tick,
        confidence: float,
        derived_from: str | None = None,
    ) -> Receipt:
        """Enregistre un apprentissage sourcé et en rend le reçu."""
        receipt = Receipt(fact, source, tick, confidence, derived_from)
        # nouvelle croyance ou réactualisation : garde la plus confiante
        existing = self.receipts.get(fact)
        if existing is None or existing.confidence < confidence:
            self.receipts[fact] = receipt
        self.log_episode(tick, EpisodeKind.RESUME, fact, source.value, confidence)
        return receipt

    def mark_signal_seen(self, genre: str, value: str | int | bool) -> None:
        self.signals_seen.add((genre, value))

    def has_seen_signal(self, genre: str, value: str | int | bool) -> bool:
        return (genre, value) in self.signals_seen

    def receipt_for(self, fact: str) -> Receipt | None:
        return self.receipts.get(fact)

    def consolidate(self, now: Tick, threshold: int) -> None:
        """Consolidation déterministe : agrège les épisodes vieux en résumé.

        Les épisodes antérieurs à ``now - threshold`` sont remplacés par un
        unique épisode ``resume`` qui compte les types vus. Idempotent.
        """
        if now - self.consolidated_at < threshold:
            return
        cutoff = now - threshold
        old = [e for e in self.episodes if e.tick < cutoff]
        if not old:
            self.consolidated_at = now
            return
        counts: dict[str, int] = {}
        for e in old:
            counts[e.kind.value] = counts.get(e.kind.value, 0) + 1
        summary = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        self.episodes = [e for e in self.episodes if e.tick >= cutoff]
        if summary:
            self.log_episode(now, EpisodeKind.RESUME, f"plus tôt : {summary}", "memoire")
        self.consolidated_at = now


__all__ = [
    "Episode",
    "EpisodeKind",
    "Memory",
    "Receipt",
]