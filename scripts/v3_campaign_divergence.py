#!/usr/bin/env python
"""Campagne divergence — la mission à l'échelle (E2/E1/E4/A5/H2).

Deux groupes de visiteurs identiques reçoivent UN message personnel opposé
(« B est libre » vs « B est bloquée »), puis la même fumée. Pour chaque
configuration (règles / grand modèle / petit modèle) × graine, on mesure :

- ``mem_acc`` : la part des agent-message qui choisissent la sortie **que leur
  mémoire indique** (B libre → B ; B bloquée → ne pas prendre B) ;
- ``consensus`` / ``couplage`` (émergence) ; coût (appels, tokens, replis).

Usage : uv run python scripts/v3_campaign_divergence.py [seeds]
Prérequis : make v3-llm-up (8081) + serveur petit 8082 (qwen).
"""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("MAREE_LLM_URL", "http://127.0.0.1:8081/v1")
os.environ.setdefault("MAREE_LLM_SMALL_URL", "http://127.0.0.1:8082/v1")

import numpy as np

from maree.v3 import bootstrap

bootstrap.assemble()

from maree.v3.adapters.physics import JuPedSimCrowd  # noqa: E402
from maree.v3.agents.perception import Message  # noqa: E402
from maree.v3.core.ids import AgentId  # noqa: E402
from maree.v3.core.ports import PolicyName  # noqa: E402
from maree.v3.sim.bus import MemoryBus  # noqa: E402
from maree.v3.sim.orchestrator import Simulation, Timestep  # noqa: E402
from maree.v3.verify.emergence import active_agents, emergence_report  # noqa: E402
from maree.v3.world.generate import build  # noqa: E402
from maree.v3.world.navgraph import NavigationGraph  # noqa: E402
from maree.v3.world.simartifact import build_sim_artifact  # noqa: E402

SEEDS = [int(a) for a in sys.argv[1:]] or [1, 2, 3, 4, 5]
#: attente par agent-message : A01/A02 (B bloquée) -> pas B ; A03/A04 (B libre) -> B
EXPECTED = {"A01": "A", "A02": "A", "A03": "B", "A04": "B"}
CONFIGS = [
    ("regles", PolicyName.RULES, None),
    ("grand", PolicyName.LLM, "decision"),
    ("petit", PolicyName.LLM, "petit"),
]


def _phys(world):
    graph = NavigationGraph(world)
    art = build_sim_artifact(world, graph, np.random.default_rng(0), spawn_per_space=8)
    lv0 = art.levels["L0"]
    return JuPedSimCrowd(walkable=lv0.walkable,
                         exits={e.id: e.segment for e in world.level("L0").exits}, seed=1)


def run(config_policy, alias, seed) -> dict:
    world = build("hall_3")
    sim = Simulation(seed=seed, policy=config_policy, run_id=f"div_{alias or 'rules'}_s{seed}",
                     bus=MemoryBus(), physics=_phys(world), physics_steps_per_tick=20).build(world)
    sim.spawn("visiteur", 4, frozenset({"A", "B"}))
    msgs = (
        (1, Message("B est bloquée", AgentId(99), 3)),
        (2, Message("B est bloquée", AgentId(99), 3)),
        (3, Message("B est libre", AgentId(99), 3)),
        (4, Message("B est libre", AgentId(99), 3)),
    )
    sim.run([Timestep(2, messages=msgs), Timestep(10, smoke=True),
             Timestep(20), Timestep(30), Timestep(40), Timestep(50)])

    # choix final par agent-message = cible du dernier EVACUER
    last_target: dict[str, str] = {}
    for r in sim.log.rows:
        if r.action.startswith("évacuer") and r.target:
            last_target[r.agent] = r.target
    correct = sum(1 for a, exp in EXPECTED.items()
                  if last_target.get(a) == exp or (exp == "A" and last_target.get(a) not in ("B",)))
    mem_acc = correct / len(EXPECTED)

    report = emergence_report(active_agents(sim))
    tokens = 0
    for i in sim.scene.instances.values():
        d = i.agent._last_decision
        if d and d.llm_trace:
            tokens += d.llm_trace.response.prompt_tokens + d.llm_trace.response.completion_tokens
    return {
        "config": alias or "rules", "seed": seed,
        "mem_acc": round(mem_acc, 3),
        "consensus": report["consensus"], "couplage": report["couplage"],
        "choices": last_target,
        "llm_calls": sum(1 for r in sim.log.rows if r.llm_model),
        "replis": sum(1 for r in sim.log.rows if r.fallback),
        "tokens": tokens,
    }


def main() -> int:
    print(f"graines {SEEDS} — monde hall_3 — petit sur {os.environ['MAREE_LLM_SMALL_URL']}")
    rows = []
    t0 = time.time()
    for name, policy, alias in CONFIGS:
        for seed in SEEDS:
            r = run(policy, alias, seed)
            rows.append(r)
            print(f"  {name:<6} s{seed}  mem_acc={r['mem_acc']:.2f} cons={r['consensus']:.2f} "
                  f"coupl={r['couplage']:.2f} calls={r['llm_calls']:>2} repli={r['replis']} "
                  f"tokens={r['tokens']:>4} choix={r['choices']}")
    print(f"durée murale : {time.time()-t0:.0f}s")

    # agrégat par config
    import statistics
    from collections import defaultdict
    by = defaultdict(list)
    for r in rows:
        by[r["config"]].append(r)
    print("\n=== AGRÉGAT (médiane mem_acc / coût / dispersion) ===")
    for cfg, rs in by.items():
        acc = statistics.median(r["mem_acc"] for r in rs)
        calls = statistics.median(r["llm_calls"] for r in rs)
        repli = sum(r["replis"] for r in rs)
        tok = statistics.median(r["tokens"] for r in rs)
        print(f"  {cfg:<6} mem_acc={acc:.2f} calls={calls:.0f} replis_tot={repli} tokens={tok:.0f}")

    out = __import__("pathlib").Path("runs/v3")
    out.mkdir(parents=True, exist_ok=True)
    (out / "campaign_divergence.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nJSON : runs/v3/campaign_divergence.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())