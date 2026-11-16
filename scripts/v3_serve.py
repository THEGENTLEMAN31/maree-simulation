#!/usr/bin/env python
"""Sert un run v3 en WebSocket pour le client (P4) — la porte du front.

Le serveur ne simule rien : il diffuse les trames du contrat
(`docs/v3/donnees-et-api.md` §5) et accepte les commandes `inject` et
`agent` (dossier étiqueté). Une injection est appliquée au **tick suivant**
(perception unique).

Usage :
    uv run python scripts/v3_serve.py                 # règles, hall_3, 8766
    V3_POLICY=hybrid uv run python scripts/v3_serve.py --tick-ms 600
    uv run python scripts/v3_serve.py --start-now     # sans attendre le client

Côté client : `ws://127.0.0.1:8766`, première trame `hello`, puis `world`,
et le flux du run ; dernière trame `end`.
"""

from __future__ import annotations

import argparse
import asyncio
import os

import numpy as np

from maree.v3 import bootstrap

bootstrap.assemble()

from maree.v3.adapters.physics import JuPedSimCrowd  # noqa: E402
from maree.v3.api.server import serve_simulation  # noqa: E402
from maree.v3.core.ports import PolicyName  # noqa: E402
from maree.v3.sim.orchestrator import Simulation, Timestep  # noqa: E402
from maree.v3.world.generate import build  # noqa: E402
from maree.v3.world.navgraph import NavigationGraph  # noqa: E402
from maree.v3.world.simartifact import build_sim_artifact  # noqa: E402

POLICIES = {"rules": PolicyName.RULES, "hybrid": PolicyName.HYBRID, "llm": PolicyName.LLM}


def _physics(world, seed: int):
    graph = NavigationGraph(world)
    art = build_sim_artifact(world, graph, np.random.default_rng(seed), spawn_per_space=6)
    lv0 = art.levels["L0"]
    return JuPedSimCrowd(
        walkable=lv0.walkable,
        exits={e.id: e.segment for e in world.level("L0").exits},
        seed=seed,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("V3_PORT", "8766")))
    ap.add_argument("--tick-ms", type=float, default=400.0)
    ap.add_argument("--policy", default=os.environ.get("V3_POLICY", "rules"), choices=sorted(POLICIES))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--start-now", action="store_true", help="ne pas attendre un client")
    args = ap.parse_args()

    world = build("hall_3")
    phys = _physics(world, args.seed)
    sim = Simulation(
        seed=args.seed,
        policy=POLICIES[args.policy],
        physics=phys,
        physics_steps_per_tick=20,
        run_id=f"serve_{args.policy}_s{args.seed}",
    ).build(world)
    sim.spawn("visiteur", 4, frozenset({"A", "B"}))
    sim.spawn("habitue", 2, frozenset({"A", "B", "C"}))
    sim.spawn("famille", 2, frozenset({"A"}))
    timeline = [
        Timestep(0),
        Timestep(10, smoke=True),
        Timestep(20, announcement="Veuillez évacuer par la sortie A"),
        Timestep(30),
        Timestep(45),
        Timestep(60),
    ]
    asyncio.run(
        serve_simulation(
            sim,
            timeline,
            host=args.host,
            port=args.port,
            tick_ms=args.tick_ms,
            wait_client=not args.start_now,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
