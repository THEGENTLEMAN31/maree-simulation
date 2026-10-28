"""Bus d'événements : deux implémentations du même port.

    InMemoryBus   tests, rejeu, mode hors ligne — aucun Kafka requis
    RedpandaBus   production : aiokafka, topics versionnés

Le journal reste la source de vérité (décision 1). Le bus sert à la
diffusion temps réel (Godot, indicateurs, chroniqueur), jamais à la
persistance : si Kafka tombe, le run reste rejouable.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator

from maree.domain.events import Event


class InMemoryBus:
    """Bus local : publication en mémoire, abonnements par file."""

    def __init__(self) -> None:
        self.published: list[tuple[str, Event]] = []
        self._subs: dict[str, list[asyncio.Queue[Event]]] = defaultdict(list)

    async def publish(self, topic: str, event: Event) -> None:
        self.published.append((topic, event))
        for queue in self._subs.get(topic, []):
            await queue.put(event)

    def subscribe(self, topic: str) -> AsyncIterator[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subs[topic].append(queue)

        async def gen() -> AsyncIterator[Event]:
            while True:
                yield await queue.get()

        return gen()

    async def close(self) -> None:
        self._subs.clear()

    def events_on(self, topic: str) -> list[Event]:
        return [e for t, e in self.published if t == topic]


class RedpandaBus:
    """Bus Kafka (Redpanda). Clé de message = run_id : ordre par run garanti."""

    def __init__(self, bootstrap: str, group_id: str = "maree") -> None:
        self._bootstrap = bootstrap
        self._group_id = group_id
        self._producer = None

    async def _ensure_producer(self):
        if self._producer is None:
            from aiokafka import AIOKafkaProducer

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode(),
                key_serializer=lambda k: k.encode() if k else None,
                acks=1,
                linger_ms=5,
            )
            await self._producer.start()
        return self._producer

    async def publish(self, topic: str, event: Event) -> None:
        producer = await self._ensure_producer()
        await producer.send_and_wait(
            topic, value=event.to_dict(), key=event.run_id
        )

    def subscribe(self, topic: str) -> AsyncIterator[Event]:
        async def gen() -> AsyncIterator[Event]:
            from aiokafka import AIOKafkaConsumer

            consumer = AIOKafkaConsumer(
                topic,
                bootstrap_servers=self._bootstrap,
                group_id=self._group_id,
                auto_offset_reset="earliest",
                value_deserializer=lambda v: Event.from_dict(json.loads(v)),
            )
            await consumer.start()
            try:
                async for msg in consumer:
                    yield msg.value
            finally:
                await consumer.stop()

        return gen()

    async def close(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
