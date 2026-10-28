"""C7 — latence LLM -> ticks de traitement, médiane/p95, et rafale.

Deux runs asynchrones (20 et 60 agents) mesurent `t_trait - t_prod`; un
benchmark séparé compare le même serveur à concurrence 1 et 8 pour vérifier
que le p95 augmente sous rafale. Écrit `/logs/c7_summary.json`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

from ..config import load_config
from ..llm_gateway import LLMGateway
from ..orchestrator import Orchestrator


async def _run(config_path: str, run_id: str, ticks: int, log_dir: str) -> dict:
    cfg = load_config(config_path)
    cfg.run_id = run_id
    cfg.max_ticks = ticks
    cfg.log_dir = log_dir
    orch = Orchestrator(cfg, corpus_path="/world_corpus")
    return await orch.run(max_ticks=ticks)


def _stats(values: list[int]) -> dict:
    if not values:
        return {"n": 0, "median": None, "p95": None, "max": None}
    ordered = sorted(values)

    def pct(q: float) -> float:
        pos = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
        return float(ordered[pos])

    return {
        "n": len(values),
        "median": pct(0.5),
        "p95": pct(0.95),
        "max": float(max(values)),
    }


async def _burst(base_url: str, concurrency: int, n_calls: int) -> dict:
    gateway = LLMGateway(base_url, timeout_sec=120.0)
    async def one() -> int:
        result = await gateway.chat(
            "gemma4-e2b",
            [{"role": "user", "content": "Réponds uniquement par le mot OK."}],
            temperature=0.1,
            max_tokens=4,
        )
        return int(result.duration_ms)

    t0 = time.time()
    sem = asyncio.Semaphore(concurrency)

    async def guarded() -> int:
        async with sem:
            return await one()

    durations = await asyncio.gather(*(guarded() for _ in range(n_calls)))
    wall_ms = int((time.time() - t0) * 1000)
    await gateway.aclose()
    stats = _stats(list(durations))
    stats["wall_ms"] = wall_ms
    stats["concurrency"] = concurrency
    return stats


async def main_async(args: argparse.Namespace) -> dict:
    twenty = await _run(args.c20, "c7_pop20", args.ticks, args.log_dir)
    sixty = await _run(args.c60, "c7_pop60", args.ticks, args.log_dir)
    base_url = load_config(args.c20).llm.get("base_url", "http://llama-cpp:8081/v1")
    calm = await _burst(base_url, 1, args.burst_calls)
    burst = await _burst(base_url, args.concurrency, args.burst_calls)
    out = {
        "ticks": args.ticks,
        "pop20": {
            "llm_latency_ms": twenty.get("llm_latency_ms"),
            "processing_delay_ticks": twenty.get("processing_delay_ticks"),
            "calls": twenty.get("calls"),
        },
        "pop60": {
            "llm_latency_ms": sixty.get("llm_latency_ms"),
            "processing_delay_ticks": sixty.get("processing_delay_ticks"),
            "calls": sixty.get("calls"),
        },
        "burst": {
            "calm_concurrency_1": calm,
            "burst_concurrency_N": burst,
            "p95_ratio": (
                (burst["p95"] / calm["p95"])
                if calm.get("p95") and burst.get("p95")
                else None
            ),
        },
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"C7 terminé → {args.out}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--c20", default="/config/c7-20.yaml")
    parser.add_argument("--c60", default="/config/c7-60.yaml")
    parser.add_argument("--ticks", type=int, default=30)
    parser.add_argument("--burst-calls", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--log-dir", default="/logs")
    parser.add_argument("--out", default="/logs/c7_summary.json")
    asyncio.run(main_async(parser.parse_args()))
