"""Enveloppe d'événements — la brique dont dépend tout le reste.

Décisions respectées :

    1  le journal (JSONL append-only) est la source de vérité ;
    2  double horodatage : `t_prod` (tick de production) et `t_trait`
       (tick de traitement), plus `t_real` réservé au journal ;
    3  aucun appel à l'horloge système dans la logique du monde ;
    4  `schema_version` + `causation_id` ;
   16  chaque événement porte son `seq`, l'ordre canonique est le tri.

Le champ `causation_id` n'était jamais rempli en v1 (exigence B4 non
tenue). Ici, `Event.child()` le remplit mécaniquement : un événement
sait toujours quel événement l'a causé.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from maree.domain.ids import RunId, Seq, Tick

SCHEMA_VERSION = "2.0.0"


class EventType(StrEnum):
    # cycle de vie
    RUN_STARTED = "run.started"
    RUN_ENDED = "run.ended"
    TICK = "tick"
    SNAPSHOT = "world.snapshot"
    # monde
    WORLD_SMOKE = "world.smoke"
    EXIT_CLOSED = "world.exit_closed"
    ANNOUNCEMENT = "world.announcement"
    INJECTION = "control.injection"
    # agents
    DECISION = "agent.decision"
    BELIEF_UPDATED = "agent.belief"
    MESSAGE_SENT = "agent.message.sent"
    MESSAGE_HEARD = "agent.message.heard"
    # mesure et récit
    INDICATORS = "metrics.indicators"
    NARRATIVE = "narrative.generated"
    # erreurs
    INVALID = "dlq.invalid"


@dataclass(frozen=True, slots=True)
class Event:
    seq: Seq
    run_id: RunId
    type: EventType
    t_prod: Tick
    t_trait: Tick
    t_real: float
    causation_id: str | None = None
    correlation_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    @property
    def id(self) -> str:
        return f"{self.run_id}:{self.seq:06d}"

    def child(
        self,
        *,
        seq: Seq,
        type: EventType,
        t_trait: Tick,
        t_real: float,
        data: dict[str, Any],
    ) -> Event:
        """Événement dérivé : la causalité est établie automatiquement (B4)."""
        return Event(
            seq=seq,
            run_id=self.run_id,
            type=type,
            t_prod=self.t_prod,
            t_trait=t_trait,
            t_real=t_real,
            causation_id=self.id,
            correlation_id=self.correlation_id or self.id,
            data=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "run_id": self.run_id,
            "type": str(self.type),
            "t_prod": self.t_prod,
            "t_trait": self.t_trait,
            "t_real": round(self.t_real, 6),
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "schema_version": self.schema_version,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        return cls(
            seq=int(d["seq"]),
            run_id=d["run_id"],
            type=EventType(d["type"]),
            t_prod=int(d["t_prod"]),
            t_trait=int(d["t_trait"]),
            t_real=float(d.get("t_real", 0.0)),
            causation_id=d.get("causation_id"),
            correlation_id=d.get("correlation_id"),
            data=d.get("data") or {},
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )
