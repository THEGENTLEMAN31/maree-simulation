"""C1 — vérifie que les événements transitent réellement par Kafka.

Ce script ne fait pas partie du moteur : c'est un **témoin**. Il consomme
les topics du bus et recompte ce qu'il a vu, indépendamment du journal.
Sans lui, « les événements transitent par Kafka » serait une affirmation
sur du code, pas une mesure.

    uv run python scripts/kafka_check.py --bootstrap 172.28.0.10:9092 --run-id run_x

Sortie : un JSON avec, par topic, le nombre de messages et la répartition
par type, plus le nombre de `run_id` distincts (doit valoir 1).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter, defaultdict

from aiokafka import AIOKafkaConsumer

TOPICS = (
    "world.events",
    "agent.decisions",
    "agent.social",
    "metrics.indicators",
    "narrative.generated",
    "dlq.invalid",
)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap", default="localhost:9092")
    parser.add_argument("--run-id", default=None, help="filtrer sur un run")
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    consumer = AIOKafkaConsumer(
        *TOPICS,
        bootstrap_servers=args.bootstrap,
        auto_offset_reset="earliest",
        group_id=None,
        enable_auto_commit=False,
    )
    await consumer.start()
    per_topic: dict[str, Counter[str]] = defaultdict(Counter)
    runs: Counter[str] = Counter()
    first_seq: dict[str, int] = {}
    last_seq: dict[str, int] = {}
    try:
        end = asyncio.get_event_loop().time() + args.seconds
        while True:
            left = end - asyncio.get_event_loop().time()
            if left <= 0:
                break
            batches = await consumer.getmany(timeout_ms=int(left * 1000) or 1)
            for tp, messages in batches.items():
                for msg in messages:
                    event = json.loads(msg.value)
                    if args.run_id and event.get("run_id") != args.run_id:
                        continue
                    per_topic[tp.topic][event["type"]] += 1
                    runs[event["run_id"]] += 1
                    first_seq.setdefault(event["run_id"], event["seq"])
                    last_seq[event["run_id"]] = max(
                        last_seq.get(event["run_id"], 0), event["seq"]
                    )
    finally:
        await consumer.stop()

    payload = {
        "bootstrap": args.bootstrap,
        "topics": {
            topic: {"total": sum(types.values()), "types": dict(types)}
            for topic, types in sorted(per_topic.items())
        },
        "runs": dict(runs),
        "seq": {
            run: {"first": first_seq[run], "last": last_seq[run]}
            for run in runs
        },
        "total": sum(sum(t.values()) for t in per_topic.values()),
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for topic, info in payload["topics"].items():
            print(f"{topic:<24} {info['total']:>5} messages")
            for type_, count in sorted(info["types"].items()):
                print(f"    {type_:<26} {count:>5}")
        print(f"runs distincts : {len(runs)}  |  total : {payload['total']}")


if __name__ == "__main__":
    asyncio.run(main())
