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
from datetime import datetime

from kafka import KafkaConsumer

from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import KafkaBus
from maree.v3.sim.journal import log_digest
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.sim.schemas import EVENT_SCHEMA_ID, validate
from maree.v3.world.sample import sample_worldspec

BOOTSTRAP = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1:9092"
TOPIC = "mv.events"
# un run_id ne se réutilise jamais (le topic est append-only) : deux lancements
# avec le même identifiant feraient croire à un run de 72 événements.
RUN_ID = f"c1_roundtrip_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


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

    # C1 : ce que le broker a reçu est ce que le journal a décidé — à l'ordre près
    recues = [
        (str(e["data"]["agent"]), str(e["data"]["action"]), e["data"]["target"])
        for e in seen
        if e["type"] == "agent.decision"
    ]
    journal = [(r.agent, r.action, r.target) for r in sim.log.rows]
    print(f"  décisions identiques au journal : {recues == journal}")
    print(f"  digest journal = {log_digest(sim.log)[:16]}…")

    # F4 : chaque trame reçue porte la version du contrat et satisfait son schéma
    hors_schema = [
        (e["type"], errors)
        for e in seen
        if (errors := validate(str(e["type"]), e["data"]))  # type: ignore[arg-type]
    ]
    versions = {e.get("schema") for e in seen}
    print(f"  F4 versions: {sorted(str(v) for v in versions)} | conformes : {len(seen) - len(hors_schema)}/{len(seen)}")
    for event_type, errors in hors_schema[:3]:
        print(f"    ✗ {event_type} : {errors}")

    ok = (
        n_dec == len(sim.log.rows)
        and n_smoke == 1
        and n_ann == 1
        and seqs == list(range(1, len(seen) + 1))
        and recues == journal
        and versions == {EVENT_SCHEMA_ID}
        and not hors_schema
    )
    print("C1 OK :", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())