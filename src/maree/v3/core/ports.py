"""core.ports — les contrats que le domaine exige du monde extérieur.

Règle (architecture.md §4) : le domaine et le moteur n'importent aucun
adaptateur concret ; tout est branché dans ``bootstrap``. En semaine 4 on
pose le port ``ChatModelPort`` (le LLM), le ``ModelSpec`` (catalogue) et la
``PolicyName`` (registre). D'autres ports suivront (physique, stockage…).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from maree.v3.core.ids import Tick


class PolicyName(StrEnum):
    """Les politiques de décision (comportement.md §10)."""

    RULES = "rules"
    HYBRID = "hybrid"
    LLM = "llm"
    DECISION_HEAD = "decision_head"


class ExecutionMode(StrEnum):
    """Comment le temps se déroule (C4) : barrière (sync) ou cadence (async).

    - ``SYNC`` : tous les agents perçoivent et décident au même pas
      (t_prod == t_trait) — le contrôle ;
    - ``ASYNC`` : chacun décide à son rythme (latence du LLM convertie en
      ticks), la décision est **appliquée quand elle aboutit** (t_trait ≥
      t_prod) — le réaliste : le monde ne s'arrête jamais pour un LLM.
    """

    SYNC = "sync"
    ASYNC = "async"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True, slots=True)
class LLMRequest:
    messages: tuple[LLMMessage, ...]
    temperature: float = 0.0
    max_tokens: int = 256
    seed: int | None = None
    #: identité pour les traces : fournies par le résolveur de catalogue.
    provider: str = "unknown"
    model: str = "unknown"


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    #: trace complète, condition du rejeu et du coût.
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    seed: int | None = None
    latency_s: float = 0.0
    ok: bool = True


@runtime_checkable
class ChatModelPort(Protocol):
    """Ce que la politique ``llm`` exige : un chat completions sourcé."""

    def complete(self, request: LLMRequest) -> LLMResponse: ...


@dataclass(frozen=True, slots=True)
class LLMTrace:
    """Trace d'un appel LLM, portée par le journal (audit + coût)."""

    tick: Tick
    request: LLMRequest
    response: LLMResponse
    policy: str = "llm"
    fallback: bool = False    # replié sur règles
    fallback_cause: str | None = None


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Un modèle résolvable du catalogue (provider + modèle + réglages)."""

    alias: str
    provider: str
    model: str
    max_tokens: int = 256
    temperature: float = 0.0
    seed: int | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)  # "small", "big", "decision"…

    @property
    def resolved(self) -> str:
        return f"{self.provider}:{self.model}"


__all__ = [
    "ChatModelPort",
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMTrace",
    "ModelSpec",
    "PolicyName",
]