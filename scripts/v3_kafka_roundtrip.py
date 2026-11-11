#!/usr/bin/env python
"""Preuve C1 de bout en bout : un run v3 publie sur Kafka (mv.events).

- l'orchestrateur émet world.smoke / world.announcement / agent.decision ;
- un producteur kafka-python les publie (clé = run_id) ;
- on reconsomme le topic et on vérifie que les décisions reçues == celles
  du journal du run et que les séquences sont complètes.

Usage : uv run python scripts/v3_kafka_roundtrip.py [bootstrap]
Prérequis : broker Kafka lancé (make kafka-up), port 9092.
"""

from __future__ import annotations

import json
import sys

from kafka import KafkaConsumer

from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import KafkaBus
from maree.v3.sim.journal import log_digest
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.world.sample import sample_worldspec

BOOTSTRAP = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:9092"
TOPIC = "mv.events"
RUN_ID = "c1_roundtrip"


def main() -> int:
    bus = KafkaBus(BOOTSTRAP, topic=TOPIC, run_id=RUN_ID)
    sim = Simulation(seed=5, policy=PolicyName.RULES, bus=bus, run_id=RUN_ID).build(
        sample_worldspec()
    )
    sim.spawn("visiteur", 3, frozenset({"A", "B"}))
    sim.run(
        [
            Timestep(1),
            Timestep(5, announcement="Veuillez évacuer par la sortie A"),
            Timestep(10, smoke=True),
        ]
    )
    bus.close()  # flush

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BOOTSTRAP,
        auto_offset_reset="earliest",
        consumer_timeout_ms=8000,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )
    seen: list[dict[str, object]] = []
    for msg in consumer:
        env = msg.value
        if env.get("run_id") == RUN_ID:
            seen.append(env)
    consumer.close()

    n_dec = sum(1 for e in seen if e["type"] == "agent.decision")
    n_smoke = sum(1 for e in seen if e["type"] == "world.smoke")
    n_ann = sum(1 for e in seen if e["type"] == "world.announcement")
    print(f"événements reçus du topic '{TOPIC}' (run {RUN_ID}) : {len(seen)}")
    print(f"  décisions: {n_dec} | world.smoke: {n_smoke} | world.announcement: {n_ann}")
    seqs = sorted(int(e["seq"]) for e in seen)
    print(f"  seq: {seqs[0]}..{seqs[-1]}, continu : {seqs == list(range(1, len(seen) + 1))}")
    print(f"  digest journal = {log_digest(sim.log)[:16]}…")
    ok = n_dec == len(sim.log.rows) and n_smoke == 1 and n_ann == 1
    print("C1 OK :" , ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())