"""sim.bus — le bus d'événements (C1).

Le journal JSONL est la **source de vérité** ; le bus est la **diffusion**
temps réel des mêmes événements. Deux implémentations derrière un port :
- ``MemoryBus`` : par défaut (campagnes de mesure, zéro dépendance) ;
- ``KafkaBus`` : publie sur ``mv.events`` du broker (C1, flux live Godot).

Chaque enveloppe porte ``run_id, seq, type, t_prod, t_trait`` et un
``causation_id`` (maillon d'audit). Le temps **simulé** vient de l'enveloppe,
jamais de l'horodatage du broker.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from maree.v3.core.ids import Tick


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    run_id: str
    seq: int
    type: str
    t_prod: Tick
    t_trait: Tick
    causation_id: str | None = None
    data: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "seq": self.seq,
            "type": self.type,
            "t_prod": self.t_prod,
            "t_trait": self.t_trait,
            "causation_id": self.causation_id,
            "data": self.data,
        }


class EventBus(Protocol):
    def publish(self, envelope: EventEnvelope) -> None: ...
    def close(self) -> None: ...


class MemoryBus:
    """Collecte les enveloppes en mémoire (tests + campagnes)."""

    def __init__(self) -> None:
        self.envelopes: list[EventEnvelope] = []
        self.closed = False

    def publish(self, envelope: EventEnvelope) -> None:
        self.envelopes.append(envelope)

    def published(self, event_type: str | None = None) -> list[EventEnvelope]:
        if event_type is None:
            return self.envelopes
        return [e for e in self.envelopes if e.type == event_type]

    def close(self) -> None:
        self.closed = True


class KafkaBus:
    """Publie sur un topic Kafka (par défaut ``mv.events``), clé = ``run_id``."""

    def __init__(
        self,
        bootstrap: str,
        topic: str = "mv.events",
        run_id: str = "v3",
        batch_size: int = 1,
    ) -> None:
        from kafka import KafkaProducer

        self._topic = topic
        self._run_id = run_id
        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8"),
            batch_size=batch_size,
        )

    @classmethod
    def from_env(cls, run_id: str, bootstrap: str | None = None) -> KafkaBus:
        return cls(bootstrap or "127.0.0.1:9092", run_id=run_id)

    def publish(self, envelope: EventEnvelope) -> None:
        self._producer.send(
            self._topic,
            key=self._run_id,
            value=envelope.to_dict(),
        )

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()


__all__ = ["EventBus", "EventEnvelope", "KafkaBus", "MemoryBus"]