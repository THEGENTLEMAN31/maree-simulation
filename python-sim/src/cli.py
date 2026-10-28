"""CLI — points d'entrée de la simulation.

Commandes :
- run          : lance un run (mode normal, sync/async)
- replay       : rejoue un run depuis le journal (E3)
- experiments  : exécute le protocole X1–X7 (E2)
- report       : génère le rapport (tableaux + figures, F5)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from .config import SimulationConfig, load_config


@click.group()
def cli() -> None:
    """MARÉE — simulation multi-agents LLM."""


@cli.command()
@click.option("--config", "-c", type=click.Path(exists=True), required=True)
@click.option("--run-id", type=str, default=None, help="surcharge le run_id")
@click.option("--mode", type=click.Choice(["sync", "async"]), default=None)
@click.option("--ticks", type=int, default=None)
@click.option("--dry-run", is_flag=True, help="aucun appel réseau LLM (tests)")
@click.option("--kafka-memory", is_flag=True, help="Kafka en mémoire (banc d'essai sans Redpanda)")
@click.option("--json", "as_json", is_flag=True, help="sortie JSON")
def run(config: str, run_id: str | None, mode: str | None, ticks: int | None, dry_run: bool, kafka_memory: bool, as_json: bool) -> None:
    """Lance un run de simulation."""
    cfg = load_config(config)
    if run_id:
        cfg.run_id = run_id
    if mode:
        cfg.mode = mode  # type: ignore[assignment]
    if ticks:
        cfg.max_ticks = ticks

    from .orchestrator import Orchestrator

    orch = Orchestrator(cfg, dry_run=dry_run, kafka_memory=kafka_memory)
    summary = asyncio.run(orch.run(max_ticks=ticks))
    if as_json:
        click.echo(json.dumps(summary, indent=2))
    else:
        click.echo(f"run {cfg.run_id} terminé — {_fmt_summary(summary)}")


@cli.command()
@click.option("--run-id", type=str, required=True)
@click.option("--log-dir", type=str, default="/logs")
def replay(run_id: str, log_dir: str) -> None:
    """Rejoue un run depuis le journal (E3) — aucun appel LLM."""
    from .replay import ReplayEngine, reconstruct_decisions

    result = ReplayEngine.replay(run_id, log_dir)
    check = reconstruct_decisions(run_id, log_dir)
    click.echo(
        f"rejeu {result.run_id} : {result.n_events} événements, "
        f"hash indicateurs = {result.indicator_hash}"
    )
    click.echo(
        "décisions LLM reconstruites : "
        f"{check['matching']}/{check['n_decisions']} "
        f"(traces complètes {check['trace_complete']}, "
        f"non appariables {len(check['mismatches'])})"
    )


@cli.command()
@click.option("--config", "-c", type=click.Path(exists=True), required=True)
@click.option("--dry-run", is_flag=True)
@click.option("--runs-per-config", type=int, default=5)
@click.option("--log-dir", type=str, default="/logs")
@click.option("--only", type=str, default=None, help="restreindre à X1,X2,…")
@click.option("--corpus", type=str, default=None)
@click.option("--llm-url", type=str, default=None)
@click.option("--kafka-memory", is_flag=True)
def experiments(
    config: str,
    dry_run: bool,
    runs_per_config: int,
    log_dir: str,
    only: str | None,
    corpus: str | None,
    llm_url: str | None,
    kafka_memory: bool,
) -> None:
    """Exécute le protocole expérimental X1–X7 (E2)."""
    from .experiments.runner import ExperimentRunner

    sel = [x.strip() for x in only.split(",")] if only else None
    runner = ExperimentRunner(
        config,
        dry_run=dry_run,
        n_runs=runs_per_config,
        base_dir=log_dir,
        only=sel,
        corpus_path=corpus,
        llm_base_url=llm_url,
        kafka_memory=True if kafka_memory else None,
    )
    runner.run_all()


@cli.command()
@click.option("--log-dir", type=str, default="/logs")
@click.option("--out", type=click.Path(), default="/logs/report.md")
@click.option("--rag-eval", type=str, default=None, help="JSON F2 (rag_eval)")
def report(log_dir: str, out: str, rag_eval: str | None) -> None:
    """Génère le rapport à partir des runs journalisés (F5)."""
    from .experiments.report import build_report

    tests = build_report(log_dir, out, rag_eval_path=rag_eval)
    click.echo(f"rapport écrit dans {out} ({len(tests)} tests)")


def _fmt_summary(s: dict) -> str:
    return (
        f"{s['calls']} appels LLM, {s['tokens_in']}→{s['tokens_out']} tokens, "
        f"{s['total_ms'] / 1000:.1f}s cumulées, {s['temporal_violations']} violations temporelles"
    )


if __name__ == "__main__":
    sys.exit(cli())