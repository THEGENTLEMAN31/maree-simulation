"""Ports : ce que le domaine exige du monde extérieur.

Chaque port est un `Protocol`. Le domaine et le moteur ne connaissent que
ces contrats ; les implémentations vivent dans `adapters/`.

C'est ce qui rend le projet remplaçable pièce par pièce :

    CrowdPhysics   JuPedSim aujourd'hui, autre moteur demain
    LLMPort        llama.cpp aujourd'hui, API distante demain
    RetrieverPort  FAISS + bge-m3 aujourd'hui, autre index demain
    JournalPort    JSONL aujourd'hui, Kafka ou Parquet demain
    EventBus       Redpanda aujourd'hui, mémoire en test
    MemoryPort     projection du journal aujourd'hui, autre store demain
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from maree.domain.events import Event
from maree.domain.ids import AgentId, ExitId, Point, RunId, Tick


# ============================================================
# LLM
# ============================================================
@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class LLMResult:
    """Trace complète d'un appel — condition de rejeu (E3) et de coût (E4)."""

    text: str
    prompt: str
    seed: int
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    duration_s: float = 0.0
    ok: bool = True
    error: str | None = None


@runtime_checkable
class LLMPort(Protocol):
    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        seed: int,
        model: str | None = None,
        max_tokens: int = 256,
        temperature: float = 0.3,
    ) -> LLMResult: ...

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


# ============================================================
# Physique de foule
# ============================================================
@dataclass(frozen=True, slots=True)
class Destination:
    """Où va un agent, du point de vue de la physique."""

    kind: Literal["exit", "point", "agent"]
    exit_id: ExitId | None = None
    point: Point | None = None
    agent_id: AgentId | None = None

    @classmethod
    def to_exit(cls, exit_id: ExitId) -> Destination:
        return cls(kind="exit", exit_id=exit_id)

    @classmethod
    def to_point(cls, point: Point) -> Destination:
        return cls(kind="point", point=point)

    @classmethod
    def follow(cls, agent_id: AgentId) -> Destination:
        return cls(kind="agent", agent_id=agent_id)


@runtime_checkable
class CrowdPhysics(Protocol):
    """Moteur de déplacement. Ne connaît ni LLM, ni croyance, ni Kafka."""

    def add_agent(self, agent_id: AgentId, position: Point, destination: Destination) -> None: ...
    def set_destination(self, agent_id: AgentId, destination: Destination) -> None: ...
    def remove_agent(self, agent_id: AgentId) -> None: ...
    def step(self) -> None: ...
    def positions(self) -> dict[AgentId, Point]: ...
    def evacuated(self) -> set[AgentId]: ...
    def close_exit(self, exit_id: ExitId) -> None: ...
    @property
    def agent_count(self) -> int: ...


# ============================================================
# Mémoire
# ============================================================
@dataclass(frozen=True, slots=True)
class Episode:
    """Un souvenir daté, sourcé, pondéré par sa saillance."""

    tick: Tick
    kind: Literal["vu", "entendu", "dit", "decide", "resume"]
    content: str
    source: str
    salience: float = 0.5
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "kind": self.kind,
            "content": self.content,
            "source": self.source,
            "salience": self.salience,
            "tags": list(self.tags),
        }


@runtime_checkable
class MemoryPort(Protocol):
    """Accès à la mémoire. Le cloisonnement est une garantie, pas une intention."""

    def remember(self, agent_id: AgentId, episode: Episode) -> None: ...
    def recall(
        self, agent_id: AgentId, query: str = "", k: int = 5, tick: Tick = 0
    ) -> list[Episode]: ...
    def beliefs(self, agent_id: AgentId) -> Any: ...
    def trust(self, agent_id: AgentId) -> dict[AgentId, float]: ...
    def consolidate(self, agent_id: AgentId, tick: Tick) -> None: ...


# ============================================================
# Journal
# ============================================================
@runtime_checkable
class JournalPort(Protocol):
    def append(self, event: Event) -> None: ...
    def read(self, run_id: RunId) -> list[Event]: ...
    def last_seq(self, run_id: RunId) -> int: ...


# ============================================================
# Bus d'événements
# ============================================================
@runtime_checkable
class EventBus(Protocol):
    async def publish(self, topic: str, event: Event) -> None: ...
    def subscribe(self, topic: str) -> AsyncIterator[Event]: ...
    async def close(self) -> None: ...


# ============================================================
# Récupération documentaire
# ============================================================
@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    doc_id: str
    text: str
    score: float
    collection: str
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class RetrieverPort(Protocol):
    """Accès RAG filtré par profil et par date de disponibilité (décision 15).

    Asynchrone : la requête doit être encodée (bge-m3 sur GPU), et un
    appel bloquant dans la boucle de décision sérialiserait tout le run.
    """

    async def retrieve(
        self, query: str, *, profile: str, tick: Tick, k: int = 3
    ) -> list[RetrievedPassage]: ...

    @property
    def degraded(self) -> bool: ...


__all__ = [
    "ChatMessage",
    "CrowdPhysics",
    "Destination",
    "Episode",
    "EventBus",
    "JournalPort",
    "LLMPort",
    "LLMResult",
    "MemoryPort",
    "RetrievedPassage",
    "RetrieverPort",
]
