#!/usr/bin/env python
"""Campagne **discriminante** grand vs petit (A5/H2) — première tentative.

Le scénario « mot personnel » (v3_campaign_divergence) ne séparait pas les
deux modèles : 0,50 chacun. Ici on ajoute une **annonce qui nomme B** au
moment de la fumée, afin que la mémoire personnelle (« B est bloquée ») et
l'ordre public se contredisent :

- ``B bloquée`` (A01/A02) : suivre sa mémoire = ne pas aller à B ;
- ``B libre`` (A03/A04)   : suivre sa mémoire = aller à B ;
- l'annonce dit « évacuez par B ».

Le petit modèle applique la règle (drapeau « annonce = oui » → B) et ne lit
pas la mémoire ; le grand modèle *peut* arbitrer mémoire vs ordre. Si les
deux restent à 0,50, la taille ne se voit pas sur cette tâche — et c'est une
mesure, pas une opinion.

Usage : uv run python scripts/v3_campaign_discriminant.py [seeds]
Prérequis : serveurs 8081 (grand) et 8082 (petit).
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

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
EXPECTED = {"A01": "A", "A02": "A", "A03": "B", "A04": "B"}   # mémoire personnelle
CONFIGS = [
    ("regles", PolicyName.RULES, None),
    ("grand", PolicyName.LLM, "decision"),
    ("petit", PolicyName.LLM, "petit"),
]

ANNOUNCEMENT = "Veuillez évacuer par la sortie B"


def _physics(world):
    graph = NavigationGraph(world)
    art = build_sim_artifact(world, graph, np.random.default_rng(0), spawn_per_space=8)
    lv0 = art.levels["L0"]
    return JuPedSimCrowd(
        walkable=lv0.walkable,
        exits={e.id: e.segment for e in world.level("L0").exits},
        seed=1,
    )


def run(policy: PolicyName, alias: str | None, seed: int) -> dict[str, object]:
    world = build("hall_3")
    sim = Simulation(
        seed=seed,
        policy=policy,
        run_id=f"disc_{alias or 'rules'}_s{seed}",
        bus=MemoryBus(),
        physics=_physics(world),
        physics_steps_per_tick=20,
    ).build(world)
    sim.spawn("visiteur", 4, frozenset({"A", "B"}))
    msgs = (
        (1, Message("B est bloquée", AgentId(99), 3)),
        (2, Message("B est bloquée", AgentId(99), 3)),
        (3, Message("B est libre", AgentId(99), 3)),
        (4, Message("B est libre", AgentId(99), 3)),
    )
    sim.run([
        Timestep(2, messages=msgs),
        Timestep(10, smoke=True, announcement=ANNOUNCEMENT),
        Timestep(20), Timestep(30), Timestep(40), Timestep(50),
    ])

    last_target: dict[str, str] = {}
    for r in sim.log.rows:
        if r.action.startswith("évacuer") and r.target:
            last_target[r.agent] = r.target
    correct = sum(
        1 for a, exp in EXPECTED.items()
        if last_target.get(a) == exp
    )
    tokens = 0
    for inst in sim.scene.instances.values():
        d = inst.agent._last_decision
        if d and d.llm_trace:
            tokens += d.llm_trace.response.prompt_tokens + d.llm_trace.response.completion_tokens
    report = emergence_report(active_agents(sim))
    return {
        "config": alias or "rules",
        "seed": seed,
        "mem_acc": round(correct / len(EXPECTED), 3),
        "choices": last_target,
        "consensus": report["consensus"],
        "couplage": report["couplage"],
        "llm_calls": sum(1 for r in sim.log.rows if r.llm_model),
        "replis": sum(1 for r in sim.log.rows if r.fallback),
        "incidents": dict(sorted(sim.incidents.items())),
        "tokens": tokens,
    }


def main() -> int:
    print(f"graines {SEEDS} — annonce « {ANNOUNCEMENT} » face à la mémoire personnelle")
    rows: list[dict[str, object]] = []
    t0 = time.time()
    for name, policy, alias in CONFIGS:
        for seed in SEEDS:
            r = run(policy, alias, seed)
            rows.append(r)
            print(
                f"  {name:<6} s{seed}  mem_acc={r['mem_acc']:.2f} cons={r['consensus']:.2f} "
                f"coupl={r['couplage']:.2f} calls={r['llm_calls']:>2} repli={r['replis']} "
                f"tokens={r['tokens']:>4} choix={r['choices']}"
            )
    print(f"durée murale : {time.time() - t0:.0f}s")

    by: dict[str, list[dict[str, object]]] = defaultdict(list)
    for r in rows:
        by[str(r["config"])].append(r)
    print("\n=== AGRÉGAT (médiane) ===")
    for cfg, rs in by.items():
        mem = statistics.median(float(r["mem_acc"]) for r in rs)
        cons = statistics.median(float(r["consensus"]) for r in rs)
        calls = statistics.median(int(r["llm_calls"]) for r in rs)
        tokens = statistics.median(int(r["tokens"]) for r in rs)
        replis = sum(int(r["replis"]) for r in rs)
        print(
            f"  {cfg:<6} mem_acc={mem:.2f} consensus={cons:.2f} "
            f"appels={calls:.0f} tokens={tokens:.0f} replis_tot={replis}"
        )

    out = Path("runs/v3")
    out.mkdir(parents=True, exist_ok=True)
    (out / "campaign_discriminant.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nJSON : runs/v3/campaign_discriminant.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
