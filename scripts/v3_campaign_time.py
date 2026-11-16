#!/usr/bin/env python
"""Campagne temps (C5/O10) : sync vs async, même scénario, vrai LLM.

Hypothèse (écrite avant mesure) : en **async**, les décisions sont appliquées
plus tard (lag > 0), donc l'ordre de traitement se déforme — cela peut changer
le consensus/le coût par rapport au **sync** (t_prod == t_trait, lag = 0).

Usage : uv run python scripts/v3_campaign_time.py [seeds]
Prérequis : make v3-llm-up (8081)
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("MAREE_LLM_URL", "http://127.0.0.1:8081/v1")

from maree.v3 import bootstrap

bootstrap.assemble()

from maree.v3.agents.perception import Message  # noqa: E402
from maree.v3.core.ids import AgentId  # noqa: E402
from maree.v3.core.ports import ExecutionMode, PolicyName  # noqa: E402
from maree.v3.sim.bus import MemoryBus  # noqa: E402
from maree.v3.sim.orchestrator import Simulation, Timestep  # noqa: E402
from maree.v3.verify.emergence import emergence_report  # noqa: E402
from maree.v3.world.generate import build  # noqa: E402

SEEDS = [int(a) for a in sys.argv[1:]] or [1, 2, 3]


def run(mode: ExecutionMode, seed: int) -> dict:
    world = build("hall_3")
    sim = Simulation(seed=seed, policy=PolicyName.LLM, run_id=f"time_{mode.value}_s{seed}",
                     bus=MemoryBus(), mode=mode).build(world)
    sim.spawn("visiteur", 4, frozenset({"A", "B"}))
    msgs = (
        (1, Message("B est bloquée", AgentId(99), 3)), (2, Message("B est bloquée", AgentId(99), 3)),
        (3, Message("B est libre", AgentId(99), 3)), (4, Message("B est libre", AgentId(99), 3)),
    )
    sim.run([Timestep(2, messages=msgs), Timestep(10, smoke=True), Timestep(20), Timestep(30)])
    report = emergence_report([i.agent for i in sim.scene.instances.values()])
    tokens = sum((i.agent._last_decision.llm_trace.response.prompt_tokens +
                  i.agent._last_decision.llm_trace.response.completion_tokens)
                 for i in sim.scene.instances.values() if i.agent._last_decision and i.agent._last_decision.llm_trace)
    return {
        "mode": mode.value, "seed": seed,
        "decisions": len(sim.log.rows),
        "llm_calls": sum(1 for r in sim.log.rows if r.llm_model),
        "tokens": tokens,
        "lag_max": max((r.lag for r in sim.log.rows), default=0),
        "consensus": report["consensus"], "couplage": report["couplage"],
    }


def main() -> int:
    print(f"graines {SEEDS} — HYP : async => lag>0, sync => lag=0")
    results = []
    t0 = time.time()
    for mode in (ExecutionMode.SYNC, ExecutionMode.ASYNC):
        for seed in SEEDS:
            r = run(mode, seed)
            results.append(r)
            print(f"  {mode.value:<6} s{seed}  dec={r['decisions']:>2} calls={r['llm_calls']:>2} "
                  f"tokens={r['tokens']:>4} lagmax={r['lag_max']:>2} cons={r['consensus']:.2f} coupl={r['couplage']:.2f}")
    print(f"durée : {time.time()-t0:.0f}s")
    by = {"sync": [r for r in results if r["mode"] == "sync"],
          "async": [r for r in results if r["mode"] == "async"]}
    print("\n=== AGRÉGAT (médiane) ===")
    for name, rs in by.items():
        print(f"  {name:<6} lag_max={statistics.median(r['lag_max'] for r in rs):.0f} "
              f"decisions={statistics.median(r['decisions'] for r in rs):.0f} "
              f"calls={statistics.median(r['llm_calls'] for r in rs):.0f} "
              f"tokens={statistics.median(r['tokens'] for r in rs):.0f} "
              f"consensus={statistics.median(r['consensus'] for r in rs):.2f}")
    out = Path("runs/v3")
    out.mkdir(parents=True, exist_ok=True)
    (out / "campaign_time.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())