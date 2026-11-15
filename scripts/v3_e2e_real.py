#!/usr/bin/env python
"""Vrai run de bout en bout : monde généré + mouvement (JuPedSim) + vrai LLM.

Sur un bâtiment **généré** (world/generate), une foule se déplace réellement
(JuPedSim), décide au vrai modèle (gemma4-e2b), consulte la base de
connaissances (RAG, retriever stub) et sa mémoire, et sort par les issues —
le tout diffusé sur Kafka. On mesure : décisions, appels/tokens, déplacement,
évacuations, et on reconsomme le topic (C1).

Usage : uv run python scripts/v3_e2e_real.py   (après make kafka-up + v3-llm-up)
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("MAREE_LLM_URL", "http://127.0.0.1:8081/v1")

import json

from kafka import KafkaConsumer

from maree.v3 import bootstrap

bootstrap.assemble()

import numpy as np  # noqa: E402

from maree.v3.adapters.physics import JuPedSimCrowd  # noqa: E402
from maree.v3.core.ports import PolicyName  # noqa: E402
from maree.v3.knowledge.corpus import passages  # noqa: E402
from maree.v3.knowledge.embeddings import StubEmbedder  # noqa: E402
from maree.v3.knowledge.rag import RagRetriever  # noqa: E402
from maree.v3.sim.bus import KafkaBus  # noqa: E402
from maree.v3.sim.journal import run_header, write_jsonl  # noqa: E402
from maree.v3.sim.orchestrator import Simulation, Timestep  # noqa: E402
from maree.v3.world.generate import build  # noqa: E402
from maree.v3.world.navgraph import NavigationGraph  # noqa: E402
from maree.v3.world.simartifact import build_sim_artifact  # noqa: E402

RUN_ID = "e2e_real_hall3"
BOOTSTRAP = "127.0.0.1:9092"


def main() -> int:
    world = build("hall_3")
    graph = NavigationGraph(world)
    art = build_sim_artifact(world, graph, np.random.default_rng(0), spawn_per_space=8)
    lv0 = art.levels["L0"]
    exits = {e.id: e.segment for e in world.level("L0").exits}
    phys = JuPedSimCrowd(walkable=lv0.walkable, exits=exits, seed=1)
    retriever = RagRetriever.build(StubEmbedder(), corpus=passages())

    bus = KafkaBus(BOOTSTRAP, topic="mv.events", run_id=RUN_ID)
    sim = Simulation(seed=42, policy=PolicyName.LLM, bus=bus, run_id=RUN_ID,
                     physics=phys, physics_steps_per_tick=200).build(world)
    for a in (("habitue", 2, frozenset({"A", "B", "C"})),
              ("visiteur", 3, frozenset({"A", "B"})),
              ("famille", 1, frozenset({"A"}))):
        sim.spawn(*a)
    for inst in sim.scene.instances.values():
        inst.agent.retriever = retriever

    ts = [Timestep(1), Timestep(10, smoke=True,
                                announcement="Veuillez évacuer immédiatement par la sortie A")]
    ts += [Timestep(t) for t in (20, 30, 40, 50, 60, 70, 80)]

    t0 = time.time()
    sim.run(ts)
    wall = time.time() - t0
    bus.close()

    # bilan
    rows = sim.log.rows
    calls = [r for r in rows if r.llm_model]
    print("=" * 70)
    print(f"MONDE GÉNÉRÉ : {world.id} — niveaux {len(world.levels)} · "
          f"sorties {[e.id for e in world.level('L0').exits]}")
    print(f"DÉCISIONS : {len(rows)} · appels LLM : {len(calls)} · replis : "
          f"{sum(1 for r in rows if r.fallback)} · {wall:.1f}s murale")
    for r in rows:
        evac = " ✔ évacué" if r.agent in {f"A{t:02d}" for t in sim._evacuated} else ""
        print(f"  t{r.tick:>3} {r.agent:<6} {r.action:<22} -> {r.target!s:<3}{evac}")
    positions = phys.positions()
    print("POSITIONS photo (t=fin) : " + ", ".join(
        f"{f'A{t:02d}'}={(round(x, 1), round(y, 1))}" for t, (x, y) in positions.items()) or "(tous sortis)")
    print(f"ÉVACUÉS : {sorted(sim._evacuated)} / {len(sim.scene.instances)}")

    tokens = 0
    for inst in sim.scene.instances.values():
        d = inst.agent._last_decision
        if d and d.llm_trace:
            tokens += d.llm_trace.response.prompt_tokens + d.llm_trace.response.completion_tokens
    print(f"COÛT : {tokens} tokens LLM")

    # re-consommer le topic pour prouver C1 de bout en bout
    consumer = KafkaConsumer("mv.events", bootstrap_servers=BOOTSTRAP,
                             auto_offset_reset="earliest", consumer_timeout_ms=6000,
                             value_deserializer=lambda v: json.loads(v.decode("utf-8")))
    n = sum(1 for m in consumer if m.value.get("run_id") == RUN_ID)
    consumer.close()
    print(f"KAFKA : {n} événements reconsommés sur mv.events (run {RUN_ID})")

    out = __import__("pathlib").Path(__file__).resolve().parents[1] / "runs" / "v3"
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / f"{RUN_ID}.jsonl", run_header(RUN_ID, world, 42, sim.policy), sim.log)
    print(f"journal : {out / RUN_ID}.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())