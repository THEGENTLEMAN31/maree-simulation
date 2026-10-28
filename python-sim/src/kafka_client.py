"""Client Kafka (aiokafka) avec topics typés et mode mémoire pour les tests.

Topics (cadrage § Architecture) :
- world.events        : événements du monde (1 partition : ordre du registre)
- agent.decisions     : intentions, justifications, passages RAG, coût
- metrics.indicators  : I1–I5 recalculés en continu
- control.commands    : événements injectés depuis Godot
- dlq.invalid         : événements non conformes (F4)

Mode mémoire (:memory: true) : file déterministe in-process utilisée par les
tests et le replay hors-ligne. Le mode réseau (default) reste celui produit.
"""
from __future__ import annotations

import json
from typing import Self

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .events import EventEnvelope

TOPICS = {
    "world": "world.events",
    "agents": "agent.decisions",
    "metrics": "metrics.indicators",
    "control": "control.commands",
    "dlq": "dlq.invalid",
}


class _MemoryLog:
    """File FIFO déterministe (mode tests) — pas de réseau."""

    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    def publish(self, ev: EventEnvelope) -> int:
        """Publie et retourne l'offset mémoire (0, 1, 2…)."""
        self.events.append(ev)
        return len(self.events) - 1


class KafkaClient:
    """Wrapper asynchrone producer/consumer pour les topics MARÉE."""

    def __init__(
        self,
        bootstrap_servers: str,
        run_id: str,
        *,
        memory: bool = False,
    ) -> None:
        self.bootstrap_servers = bootstrap_servers
        self.run_id = run_id
        self.memory = memory
        self.producer: AIOKafkaProducer | None = None
        self._consumers: dict[str, AIOKafkaConsumer] = {}
        self._memlogs: dict[str, _MemoryLog] = {}
        self._mem_pos: dict[str, int] = {}
        # F6 / décision 16 : offsets réellement attribués par Kafka (ou par
        # la file mémoire). On garde le dernier offset par topic/partition et
        # la position exacte de chaque event_id, pour que chaque indicateur
        # puisse citer une plage vérifiable.
        self._offsets: dict[str, dict[int, int]] = {}
        self._event_offsets: dict[str, dict[str, int | str]] = {}

    # -- producer ----------------------------------------------------------

    async def start(self) -> Self:
        if self.memory:
            return self
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            compression_type="gzip",
        )
        await self.producer.start()
        return self

    def _log_for(self, topic: str) -> _MemoryLog:
        if topic not in self._memlogs:
            self._memlogs[topic] = _MemoryLog()
        return self._memlogs[topic]

    async def publish(self, topic: str, envelope: EventEnvelope) -> None:
        """Publie une enveloppe et mémorise l'offset attribué (F6).

        `topic` peut être un alias interne (`world`, `agents`, `metrics`…) :
        on résout le nom Kafka réel avant de publier et d'enregistrer
        l'offset, sinon la plage source ne serait pas interrogeable.
        """
        actual_topic = TOPICS.get(topic, topic)
        if self.memory:
            offset = self._log_for(actual_topic).publish(envelope)
            partition = 0
        else:
            if self.producer is None:
                raise RuntimeError("KafkaClient non démarré")
            key = (envelope.agent_id or envelope.event_id).encode()
            # aiokafka `send()` est une coroutine qui rend un Future : il faut
            # l'attendre deux fois pour obtenir les métadonnées (offset,
            # partition). Un seul `await` renvoyait le Future et F6 restait
            # silencieusement vide.
            pending = await self.producer.send(
                actual_topic,
                key=key,
                value=envelope.model_dump_json().encode(),
            )
            metadata = await pending
            offset = metadata.offset
            partition = metadata.partition
        self._record_offset(envelope.event_id, actual_topic, partition, offset)

    def _record_offset(
        self, event_id: str, topic: str, partition: int, offset: int
    ) -> None:
        self._offsets.setdefault(topic, {})[partition] = max(
            offset, self._offsets.get(topic, {}).get(partition, -1)
        )
        self._event_offsets[event_id] = {
            "topic": topic,
            "partition": partition,
            "offset": offset,
        }

    def event_offset(self, event_id: str) -> dict[str, int | str] | None:
        """Position Kafka d'un événement, ou None s'il n'a pas été publié."""
        return self._event_offsets.get(event_id)

    def source_ranges(self, event_ids: list[str]) -> dict[str, dict]:
        """Plage d'offsets par topic pour une liste d'événements (décision 16).

        Les topics MARÉE ont une seule partition. On expose néanmoins la
        partition et le nombre d'événements, pour que la vue F6/B4 puisse
        distinguer une plage réelle d'une simple borne haute.
        """
        grouped: dict[str, list[tuple[int, int]]] = {}
        for event_id in event_ids:
            info = self._event_offsets.get(event_id)
            if not info or not isinstance(info.get("offset"), int):
                continue
            topic = str(info["topic"])
            grouped.setdefault(topic, []).append(
                (int(info["partition"]), int(info["offset"]))
            )
        ranges: dict[str, dict] = {}
        for topic, positions in grouped.items():
            partitions = sorted({p for p, _ in positions})
            offsets = [o for _, o in positions]
            ranges[topic] = {
                "partition": partitions[0] if len(partitions) == 1 else partitions,
                "from": min(offsets),
                "to": max(offsets),
                "events": len(positions),
            }
        return ranges

    def high_watermarks(self) -> dict[str, dict[int, int]]:
        """Dernier offset connu par topic et partition (instantané)."""
        return {topic: dict(parts) for topic, parts in self._offsets.items()}

    async def publish_many(self, topic: str, events: list[EventEnvelope]) -> None:
        for ev in events:
            await self.publish(topic, ev)

    # -- consumer ----------------------------------------------------------

    async def subscribe(self, topic: str, *, from_beginning: bool = True) -> None:
        if self.memory:
            self._mem_pos.setdefault(topic, 0)
            return
        c = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            auto_offset_reset="earliest" if from_beginning else "latest",
            group_id=f"{self.run_id}-{topic}",
        )
        await c.start()
        self._consumers[topic] = c

    async def next_event(self, topic: str, *, timeout_sec: float = 1.0) -> EventEnvelope | None:
        if self.memory:
            events = self._memlogs.get(topic)
            if events is None:
                return None
            pos = self._mem_pos.get(topic, 0)
            if pos >= len(events.events):
                return None
            ev = events.events[pos]
            self._mem_pos[topic] = pos + 1
            return ev
        c = self._consumers.get(topic)
        if c is None:
            raise RuntimeError(f"consumer non initialisé : {topic}")
        from aiokafka.errors import KafkaError

        try:
            msg = await c.getone(timeout=timeout_sec)
        except KafkaError:
            return None
        return EventEnvelope.model_validate_json(msg.value)

    async def reset_consumers(self) -> None:
        """Repositionne les consumers mémoire au début (replay E3)."""
        for topic in self._mem_pos:
            self._mem_pos[topic] = 0

    async def close(self) -> None:
        if self.producer:
            await self.producer.stop()
        for c in self._consumers.values():
            await c.stop()