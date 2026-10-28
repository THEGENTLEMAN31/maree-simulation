"""C8 — deux tailles de population (20 et 60) rejouées côte à côte.

Lance les deux runs, rejoue chacun depuis son journal et compare I1, I3 et
le coût. Écrit `/logs/c8_summary.json` (ou le chemin `--out`).
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from ..config import load_config
from ..orchestrator import Orchestrator
from ..replay import ReplayEngine, reconstruct_decisions


async def _run(config_path: str, run_id: str, ticks: int, log_dir: str) -> dict:
    cfg = load_config(config_path)
    cfg.run_id = run_id
    cfg.max_ticks = ticks
    cfg.log_dir = log_dir
    orch = Orchestrator(cfg, corpus_path="/world_corpus")
    summary = await orch.run(max_ticks=ticks)
    replay = ReplayEngine.replay(run_id, log_dir)
    reconstructed = reconstruct_decisions(run_id, log_dir)
    summary["replay"] = {
        "events": replay.n_events,
        "indicator_hash": replay.indicator_hash,
        "decisions_reconstructed": reconstructed["matching"],
        "decisions_total": reconstructed["n_decisions"],
    }
    return summary


def _compare(a: dict, b: dict) -> dict:
    keys = (
        "I1_median", "I2_median", "I3_evacuated_ratio",
        "I4_median", "calls", "total_ms", "tokens_in", "tokens_out",
    )
    return {
        k: {
            "20": a.get(k),
            "60": b.get(k),
            "delta": (b.get(k, 0) or 0) - (a.get(k, 0) or 0),
        }
        for k in keys
    }


async def main_async(args: argparse.Namespace) -> dict:
    twenty = await _run(args.c20, "c8_pop20", args.ticks, args.log_dir)
    sixty = await _run(args.c60, "c8_pop60", args.ticks, args.log_dir)
    out = {
        "ticks": args.ticks,
        "pop20": twenty,
        "pop60": sixty,
        "comparison": _compare(twenty, sixty),
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out["comparison"], indent=2, ensure_ascii=False))
    print(f"C8 terminé → {args.out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--c20", default="/config/c8-20.yaml")
    parser.add_argument("--c60", default="/config/c8-60.yaml")
    parser.add_argument("--ticks", type=int, default=30)
    parser.add_argument("--log-dir", default="/logs")
    parser.add_argument("--out", default="/logs/c8_summary.json")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
