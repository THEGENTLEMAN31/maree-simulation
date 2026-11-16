#!/usr/bin/env python
"""Énergie par bras (E4), mesurée — pas estimée.

On échantillonne `nvidia-smi --query-gpu=power.draw` à 1 Hz **pendant** chaque
run, on mesure le temps mural, et on publie :

- la puissance moyenne du run (W) ;
- l'énergie **totale** du run (Wh) ;
- l'énergie **active** (Wh), repos soustrait (la médiane des échantillons
  hors run) — c'est la part imputable à la simulation, pas au bureau.

C'est une puissance moyenne intégrée, pas un compteur matériel : la
dispersion entre graines est publiée avec la médiane.

Usage :
    uv run python scripts/v3_energy.py --seeds 1 2 3
Prérequis : serveurs 8081/8082 pour les bras llm/hybride.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import threading
import time
from pathlib import Path

os.environ.setdefault("MAREE_LLM_URL", "http://127.0.0.1:8081/v1")
os.environ.setdefault("MAREE_LLM_SMALL_URL", "http://127.0.0.1:8082/v1")

import numpy as np

from maree.v3 import bootstrap

bootstrap.assemble()

from maree.v3.adapters.physics import JuPedSimCrowd  # noqa: E402
from maree.v3.core.ports import ExecutionMode, PolicyName  # noqa: E402
from maree.v3.sim.bus import MemoryBus  # noqa: E402
from maree.v3.sim.orchestrator import Simulation, Timestep  # noqa: E402
from maree.v3.world.generate import build  # noqa: E402
from maree.v3.world.navgraph import NavigationGraph  # noqa: E402
from maree.v3.world.simartifact import build_sim_artifact  # noqa: E402

CONFIGS = {
    "regles": (PolicyName.RULES, None),
    "hybride": (PolicyName.HYBRID, "decision"),
    "grand": (PolicyName.LLM, "decision"),
    "petit": (PolicyName.LLM, "petit"),
}
TIMELINE = [
    Timestep(0),
    Timestep(10, smoke=True),
    Timestep(20, announcement="Veuillez évacuer par la sortie A"),
    Timestep(30),
    Timestep(40),
]


def power_now() -> float | None:
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip().splitlines()[0]
        return float(out)
    except Exception:
        return None


class Sampler(threading.Thread):
    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.stop = threading.Event()
        self.samples: list[float] = []

    def run(self) -> None:
        while not self.stop.is_set():
            p = power_now()
            if p is not None:
                self.samples.append(p)
            time.sleep(1.0)

    def window(self) -> tuple[int, int]:
        return (len(self.samples), len(self.samples))


def _physics(world, seed: int):
    graph = NavigationGraph(world)
    art = build_sim_artifact(world, graph, np.random.default_rng(seed), spawn_per_space=6)
    lv0 = art.levels["L0"]
    return JuPedSimCrowd(
        walkable=lv0.walkable,
        exits={e.id: e.segment for e in world.level("L0").exits},
        seed=seed,
    )


def run_once(name: str, seed: int) -> dict[str, object]:
    policy, alias = CONFIGS[name]
    world = build("hall_3")
    sim = Simulation(
        seed=seed, policy=policy, bus=MemoryBus(), mode=ExecutionMode.SYNC,
        run_id=f"energy_{name}_s{seed}", physics=_physics(world, seed),
        physics_steps_per_tick=60,
    ).build(world)
    sim.spawn("visiteur", 4, frozenset({"A", "B"}), llm_alias=alias)
    sim.spawn("habitue", 2, frozenset({"A", "B", "C"}), llm_alias=alias)
    start = time.time()
    sim.run(TIMELINE)
    wall = time.time() - start
    calls = sum(1 for r in sim.log.rows if r.llm_model)
    return {
        "config": name,
        "seed": seed,
        "wall_s": round(wall, 3),
        "decisions": len(sim.log.rows),
        "llm_calls": calls,
        "evacuated": len(sim._evacuated),
        "start": start,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    ap.add_argument("--configs", nargs="+", default=list(CONFIGS))
    args = ap.parse_args()

    sampler = Sampler()
    sampler.start()
    time.sleep(4.0)                     # repos (bureau + GPU au repos)
    idle = statistics.median(sampler.samples) if sampler.samples else 0.0

    rows: list[dict[str, object]] = []
    for name in args.configs:
        for seed in args.seeds:
            i0 = len(sampler.samples)
            r = run_once(name, seed)
            window = sampler.samples[i0:] or [idle]
            mean_p = statistics.mean(window)
            wh = mean_p * float(r["wall_s"]) / 3600.0
            wh_active = max(mean_p - idle, 0.0) * float(r["wall_s"]) / 3600.0
            r.update(
                power_w=round(mean_p, 1),
                energy_wh=round(wh, 4),
                energy_active_wh=round(wh_active, 4),
            )
            rows.append(r)
            print(
                f"  {name:<8} s{seed}  mural={r['wall_s']:>5.2f}s appels={r['llm_calls']:>3} "
                f"P={mean_p:>5.1f}W  E={wh:.4f}Wh  E_act={wh_active:.4f}Wh"
            )
    sampler.stop.set()
    sampler.join(timeout=2)

    print(f"\nrepos GPU : {idle:.1f} W")
    by: dict[str, list[dict[str, object]]] = {}
    for r in rows:
        by.setdefault(str(r["config"]), []).append(r)
    print("=== AGRÉGAT (médiane) ===")
    aggregate: dict[str, object] = {}
    for cfg, rs in by.items():
        def med(k: str, rs: list[dict[str, object]] = rs) -> float:
            return round(statistics.median(float(r[k]) for r in rs), 4)
        aggregate[cfg] = {
            "n": len(rs),
            "wall_s_med": med("wall_s"),
            "llm_calls_med": med("llm_calls"),
            "energy_wh_med": med("energy_wh"),
            "energy_active_wh_med": med("energy_active_wh"),
        }
        print(
            f"  {cfg:<8} mural={aggregate[cfg]['wall_s_med']:>5.2f}s "
            f"appels={aggregate[cfg]['llm_calls_med']:>4.0f} "
            f"E={aggregate[cfg]['energy_wh_med']:.4f}Wh "
            f"E_act={aggregate[cfg]['energy_active_wh_med']:.4f}Wh"
        )

    out = Path("runs/v3")
    out.mkdir(parents=True, exist_ok=True)
    (out / "energy.json").write_text(
        json.dumps({"idle_w": idle, "rows": rows, "aggregate": aggregate},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\nJSON : runs/v3/energy.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
