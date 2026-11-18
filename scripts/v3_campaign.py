#!/usr/bin/env python
"""Campagne scientifique (E2/E1/E4) — N graines × configs, indicateurs + coût + dispersion.

Compare sur un monde généré : `rules` (baseline, 0 appel) / `hybrid` /
`llm` (grand modèle). Fournisseur : **réel** si le serveur 8081 répond,
sinon **stub** (CI, sans modèle). Agrège médis + dispersion entre graines.

Usage : V3_PROVIDER=real|stub uv run python scripts/v3_campaign.py [seeds]
Prérequis (real) : make v3-llm-up
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from maree.v3 import bootstrap

bootstrap.assemble()

from maree.v3.core.ports import PolicyName  # noqa: E402
from maree.v3.verify.campaign import CampConfig, aggregate, run_once  # noqa: E402
from maree.v3.world.generate import build  # noqa: E402

SEEDS = [int(a) for a in __import__("sys").argv[1:]] or [1, 2, 3, 4, 5]

CONFIGS = (
    CampConfig("rules", policy=PolicyName.RULES),
    CampConfig("hybrid", policy=PolicyName.HYBRID),
    CampConfig("llm_big", policy=PolicyName.LLM, llm_alias="decision"),
)


def _auto_provider() -> str:
    import subprocess

    env = os.environ.get("V3_PROVIDER")
    if env in ("real", "stub"):
        return env
    ok = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "3",
         "http://127.0.0.1:8081/health"],
        capture_output=True, text=True,
    ).stdout.strip() == "200"
    return "real" if ok else "stub"


def main() -> int:
    provider = _auto_provider()
    if provider == "stub":
        from maree.v3.adapters.chat_stub import StubChat
        from maree.v3.agents.catalog import register_provider

        register_provider("llamacpp", StubChat(lambda _: '{"action": "evacuer", "cible": "A", "confiance": 0.8}'))
        print("fournisseur : STUB (CI, sans modèle)")

    world = build("hall_3")
    print(f"fournisseur : {provider} — monde {world.id} — graines {SEEDS}")
    results = []
    for cfg in CONFIGS:
        for seed in SEEDS:
            r = run_once(world, cfg, seed, run_id_prefix="campaign")
            results.append(r)
            print(f"  {cfg.name:<8} seed {seed}  dec={r.decisions:>2} "
                  f"appels={r.llm_attempted:>2}/{r.llm_ok:<2} repli={r.replis}"
                  f" tokens={r.tokens:>5} cons={r.consensus:.2f} coupl={r.couplage:.2f}")

    agg = aggregate(results)
    print("\n=== AGRÉGAT (médiane, dispersion) ===")
    for name, a in agg.items():
        span = a["llm_attempted_span"]
        print(f"  {name:<8} décisions={a['decisions_med']} "
              f"appels={a['llm_attempted_med']} [{span[0]}..{span[1]}] "
              f"tokens={a['tokens_med']} I1={a['I1_med']} I3={a['I3_med']} "
              f"I5={a['I5_med']} I7={a['I7_med']} "
              f"émergence={a['empreinte_emergence']}/{a['n_runs']}")

    out = Path("runs") / "v3"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"campaign_{provider}.json").write_text(
        json.dumps({"provider": provider, "rows": [r.as_dict() for r in results],
                    "aggregate": agg}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON : runs/v3/campaign_{provider}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())