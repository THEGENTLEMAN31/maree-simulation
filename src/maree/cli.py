"""Interface en ligne de commande.

    maree run                        un run de démonstration
    maree run run=e2e                le scénario du piège (A se ferme à t40)
    maree run world=port_aubel seed=3
    maree index                      construit l'index RAG (bge-m3)
    maree replay --run-id <id>       rejeu E3 depuis le journal seul
    maree report                     agrège les runs mesurés

Les imports lourds (JuPedSim, FAISS, llama.cpp) sont faits à l'intérieur
des commandes : `maree --help` doit fonctionner sans GPU ni modèle.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from hydra import compose, initialize_config_dir
from omegaconf import DictConfig, OmegaConf

#: Nom d'indicateur du protocole -> clé de la ligne de résultat.
#: Le YAML nomme les indicateurs comme le sujet (I4_seconds), les lignes
#: de `experiment_*.json` les abrègent (I4) : cette table fait le pont.
_INDICATOR_KEYS = {
    "I1_consensus": "I1",
    "I2_entropy": "I2",
    "I3_evacuated": "I3",
    "I4_seconds": "I4",
    "I5_max_density": "I5",
    "I6_belief_gap": "I6",
    "llm_calls": "llm_calls",
    "wall_s": "wall_s",
}

app = typer.Typer(add_completion=False, help="MARÉE — foule et évacuation interprétative")


# ============================================================
# Aides
# ============================================================
def _compose(overrides: list[str]) -> DictConfig:
    config_dir = Path("configs").resolve()
    if not config_dir.exists():
        raise typer.BadParameter(f"répertoire de configuration introuvable : {config_dir}")
    with initialize_config_dir(config_dir=str(config_dir), version_base=None):
        return compose(config_name="config", overrides=overrides)


def _new_run_id(seed: int) -> str:
    """Identifiant unique. On ne réutilise JAMAIS un run_id (décision 5)."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"run_{stamp}_{seed}_{secrets.token_hex(2)}"


def _run_config(cfg: DictConfig, run_id: str):
    from maree.agents.profiles import PROFILES
    from maree.domain.clock import Clocks
    from maree.engine.simulation import PopulationEntry, RunConfig

    run = cfg.run
    population = tuple(
        PopulationEntry(profile=e.profile, count=int(e.count), kind=e.kind)
        for e in cfg.population.entries
    )
    unknown = {p.profile for p in population} - set(PROFILES)
    if unknown:
        raise typer.BadParameter(f"profils inconnus : {sorted(unknown)}")
    clocks = Clocks(
        physics_dt=float(run.get("physics_dt", 0.05)),
        cognition_s=float(run.get("cognition_s", 10.0)),
        render_hz=float(run.get("render_hz", 10.0)),
    )
    return RunConfig(
        run_id=run_id,
        seed=int(cfg.seed),
        max_ticks=int(run.max_ticks),
        smoke_tick=int(run.smoke_tick),
        smoke_position=tuple(run.smoke_position),
        smoke_radius=float(run.smoke_radius),
        close_exit=run.get("close_exit"),
        close_tick=int(run.close_tick),
        announcement_tick=run.get("announcement_tick"),
        announcement=run.get("announcement"),
        population=population,
        max_concurrency=int(run.max_concurrency),
        narrative_every=int(cfg.narrative.every_ticks),
        message_radius=float(run.message_radius),
        density_radius=float(run.density_radius),
        clocks=clocks,
    )


def _build(cfg: DictConfig, run_id: str):
    """Assemble les ports concrets. C'est le seul endroit qui les connaît."""
    from maree.adapters.bus import InMemoryBus, RedpandaBus
    from maree.adapters.journal.jsonl import JsonlJournal
    from maree.adapters.llm import LlamaCppLLM
    from maree.adapters.physics.jupedsim_physics import JuPedSimPhysics
    from maree.adapters.retrieval.faiss_corpus import FaissRetriever
    from maree.domain.geometry import Plan
    from maree.engine.simulation import Simulation
    from maree.memory.store import EventSourcedMemory, NullMemory
    from maree.narrative.chroniqueur import Chroniqueur

    plan = Plan.from_dict(OmegaConf.to_container(cfg.world, resolve=True))
    config = _run_config(cfg, run_id)

    llm = LlamaCppLLM(
        base_url=str(cfg.llm.base_url),
        model=str(cfg.llm.model),
        embed_model=str(cfg.llm.embed_model),
        timeout=float(cfg.llm.timeout_s),
    )
    physics = JuPedSimPhysics(
        plan,
        dt=config.clocks.physics_dt,
        seed=config.seed,
        model=str(cfg.world.get("physics_model", "collision_free")),
    )
    journal = JsonlJournal(cfg.paths.runs)
    bus = (
        RedpandaBus(str(cfg.bus.bootstrap))
        if str(cfg.bus.backend) == "redpanda"
        else InMemoryBus()
    )
    index_dir = Path(str(cfg.paths.index))
    retriever = None
    if bool(cfg.rag.enabled) and (index_dir / "vectors.npy").exists():
        retriever = FaissRetriever.load(index_dir, llm)
    memory = (
        EventSourcedMemory(n_exits=len(plan.exits), window=int(cfg.memory.window))
        if bool(cfg.memory.enabled)
        else NullMemory(n_exits=len(plan.exits))
    )
    narrator = (
        Chroniqueur(
            llm,
            every_ticks=int(cfg.narrative.every_ticks),
            max_tokens=int(cfg.narrative.max_tokens),
            model=str(cfg.narrative.model),
            seed_base=config.seed,
        )
        if bool(cfg.narrative.enabled)
        else None
    )
    simulation = Simulation(
        config=config,
        plan=plan,
        physics=physics,
        llm=llm,
        retriever=retriever,
        memory=memory,
        journal=journal,
        bus=bus,
        narrator=narrator,
    )
    return simulation, llm, bus


# ============================================================
# Commandes
# ============================================================
@app.command()
def run(
    overrides: list[str] = typer.Argument(None, help="surcharges Hydra"),
) -> None:
    """Lance un run complet."""
    from maree.metrics.indicators import summarise

    cfg = _compose(list(overrides or []))
    run_id = str(cfg.run_id or _new_run_id(int(cfg.seed)))
    simulation, llm, bus = _build(cfg, run_id)

    async def _go() -> None:
        try:
            result = await simulation.run()
        finally:
            await llm.close()
            await bus.close()
        last = result.indicators[-1] if result.indicators else None
        summary = summarise([i.to_dict() for i in result.indicators])
        typer.echo(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "config_hash": result.config_hash,
                    "ticks": result.ticks,
                    "events": result.events,
                    "llm_calls": result.llm_calls,
                    "llm_ok": result.llm_ok,
                    "duration_s": round(result.duration_s, 1),
                    "evacuated": last.counts.get("evacuated") if last else 0,
                    "total": last.counts.get("agents") if last else 0,
                    "I1_consensus": round(summary["I1_consensus"], 3),
                    "I4_seconds": round(summary["I4_seconds"], 0),
                    "I5_max_density": round(summary["I5_max_density"], 2),
                    "I6_belief_gap_peak": round(summary["I6_belief_gap"], 3),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        if result.llm_calls and not result.llm_ok:
            typer.secho(
                "\nATTENTION — aucun appel LLM n'a abouti : toutes les décisions "
                "sont des replis sur les règles. Ce run n'est pas un run hybride.",
                fg=typer.colors.RED,
                err=True,
            )

    asyncio.run(_go())


@app.command()
def index(
    overrides: list[str] = typer.Argument(None),
) -> None:
    """Construit l'index RAG (bge-m3 + FAISS + centrage)."""
    from maree.adapters.llm import LlamaCppLLM
    from maree.adapters.retrieval.faiss_corpus import FaissRetriever

    cfg = _compose(list(overrides or []))
    llm = LlamaCppLLM(
        base_url=str(cfg.llm.base_url),
        model=str(cfg.llm.model),
        embed_model=str(cfg.llm.embed_model),
    )

    async def _go() -> None:
        try:
            retriever = await FaissRetriever.build(str(cfg.paths.corpus), llm)
        finally:
            await llm.close()
        retriever.save(str(cfg.paths.index))
        typer.echo(f"index construit : {len(retriever._passages)} passages -> {cfg.paths.index}")

    asyncio.run(_go())


@app.command()
def replay(
    run_id: str = typer.Option(None, help="identifiant du run (défaut : le plus récent)"),
    runs: str = typer.Option("runs", help="répertoire des runs"),
) -> None:
    """Rejoue un run depuis le journal seul (E3). Aucun LLM n'est appelé."""
    from maree.adapters.journal.jsonl import JsonlJournal
    from maree.engine.replay import narrate_from_journal
    from maree.engine.replay import replay as do_replay

    journal = JsonlJournal(runs)
    target = run_id or (journal.runs()[-1] if journal.runs() else None)
    if not target:
        raise typer.BadParameter("aucun run dans le journal")
    result = do_replay(target, journal)
    typer.echo(
        json.dumps(
            {
                "run_id": result.run_id,
                "events": result.events,
                "indicators_hash": result.indicators_hash,
                "decisions": {
                    "total": result.decisions.total,
                    "traces_completes": result.decisions.trace_complete,
                    "reconstruites": result.decisions.reconstructed,
                    "concordantes": result.decisions.matching,
                },
                "narratives": {"total": result.narratives, "valides": result.narratives_valid},
                "ok": result.ok,
                "problems": list(result.problems),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    for line in narrate_from_journal(target, journal):
        typer.echo(f"  t{line['tick']:>3}  {line['text']}")


@app.command()
def experiment(
    name: str = typer.Option(..., help="protocole : x1, x2, … x7"),
    seeds: int = typer.Option(3, help="nombre de graines par bras (≥ 5 en production)"),
    overrides: list[str] = typer.Argument(None, help="surcharges Hydra"),
) -> None:
    """Exécute un protocole X1–X7 : chaque bras × chaque graine."""
    from maree.metrics.indicators import summarise

    cfg = _compose([f"+experiment={name}", *(overrides or [])])
    spec = cfg.experiment
    rows: list[dict[str, Any]] = []
    for arm in spec.arms:
        for seed in range(seeds):
            merged = OmegaConf.merge(
                cfg,
                OmegaConf.create(
                    {
                        k: OmegaConf.to_container(arm[k], resolve=True)
                        for k in ("run", "population", "memory", "rag", "narrative")
                        if k in arm
                    }
                ),
                OmegaConf.create({"seed": seed}),
            )
            run_id = f"run_{spec.id.lower()}_{arm.name}_s{seed}_{secrets.token_hex(2)}"
            simulation, llm, bus = _build(merged, run_id)

            async def _go(simulation=simulation, llm=llm, bus=bus):
                try:
                    return await simulation.run()
                finally:
                    await llm.close()
                    await bus.close()

            result = asyncio.run(_go())
            summary = summarise([i.to_dict() for i in result.indicators])
            rows.append(
                {
                    "arm": arm.name,
                    "seed": seed,
                    "run_id": run_id,
                    "I1": summary["I1_consensus"],
                    "I2": summary["I2_entropy"],
                    "I3": summary["I3_evacuated"],
                    "I4": summary["I4_seconds"],
                    "I5": summary["I5_max_density"],
                    "I6": summary["I6_belief_gap"],
                    "llm_calls": result.llm_calls,
                    "llm_ok": result.llm_ok,
                    "wall_s": round(result.duration_s, 1),
                }
            )
            typer.echo(
                f"  {arm.name:<18} graine {seed}  "
                + "  ".join(
                    f"{name}={rows[-1][_INDICATOR_KEYS.get(name, name)]:.2f}"
                    for name in spec.indicators
                )
                + f"  LLM={result.llm_ok}/{result.llm_calls}  {result.duration_s:.0f}s"
            )

    out = Path(str(cfg.paths.runs)) / f"experiment_{spec.id.lower()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    typer.echo(f"\n{len(rows)} runs -> {out}")
    typer.echo("Médianes par bras :")
    for arm in spec.arms:
        values = [r for r in rows if r["arm"] == arm.name]
        if not values:
            continue
        parts = []
        for name in spec.indicators:
            key = _INDICATOR_KEYS.get(name, name)
            xs = sorted(float(r[key]) for r in values)
            parts.append(f"{name}={xs[len(xs) // 2]:.2f}")
        typer.echo(f"  {arm.name:<18} " + "  ".join(parts) + f"  (n={len(values)})")
    degraded = [r for r in rows if r["llm_calls"] and not r["llm_ok"]]
    if degraded:
        typer.secho(
            f"\nATTENTION — {len(degraded)} run(s) sans aucun appel LLM abouti : "
            "leurs décisions sont des replis sur les règles. Le protocole ne "
            "mesure pas ce qu'il prétend mesurer.",
            fg=typer.colors.RED,
            err=True,
        )


@app.command()
def serve(
    run_id: str = typer.Option(None, help="identifiant du run (défaut : le plus récent)"),
    port: int = typer.Option(8765, help="port WebSocket"),
    speed: float = typer.Option(5.0, help="ticks par seconde (0 = au plus vite)"),
    runs: str = typer.Option("runs", help="répertoire des runs"),
    prompts: bool = typer.Option(
        False,
        "--prompts",
        help="inclure le prompt LLM dans les décisions (~3 Ko chacune)",
    ),
) -> None:
    """Diffuse un run sur WebSocket, pour le client Godot.

    Lit le journal : fonctionne sur un run terminé comme sur un run en
    cours. Aucun appel LLM, aucune dépendance au moteur.
    """
    from maree.adapters.journal.jsonl import JsonlJournal
    from maree.adapters.ws import JournalStreamer

    cfg = _compose([])
    journal = JsonlJournal(runs)
    target = run_id or (journal.runs()[-1] if journal.runs() else None)
    if not target:
        raise typer.BadParameter("aucun run dans le journal")
    streamer = JournalStreamer(
        journal,
        target,
        plan=OmegaConf.to_container(cfg.world, resolve=True),
        port=port,
        speed=speed,
        include_prompts=prompts,
    )
    try:
        asyncio.run(streamer.serve_forever())
    except KeyboardInterrupt:
        typer.echo("diffusion arrêtée")


@app.command()
def report(runs: str = typer.Option("runs")) -> None:
    """Agrège les runs mesurés (I1..I6) en un tableau."""
    from maree.adapters.journal.jsonl import JsonlJournal
    from maree.domain.events import EventType
    from maree.metrics.indicators import summarise

    journal = JsonlJournal(runs)
    rows: list[dict[str, Any]] = []
    incomplete: list[str] = []
    for run_id in journal.runs():
        events = journal.read(run_id)
        if not any(e.type is EventType.RUN_ENDED for e in events):
            # Run interrompu (plantage, Ctrl-C) : ses indicateurs partiels
            # ne sont pas un résultat. On le signale, on ne l'agrège pas.
            incomplete.append(run_id)
            continue
        series = [e.data for e in events if e.type is EventType.INDICATORS]
        if not series:
            continue
        summary = summarise(series)
        rows.append({"run_id": run_id, **summary})
    if incomplete:
        typer.echo(f"ignorés (sans run.ended) : {', '.join(incomplete)}")
    if not rows:
        typer.echo("aucun run mesuré")
        return
    header = f"{'run_id':<34}{'I1':>8}{'I2':>8}{'I3':>8}{'I4':>8}{'I5':>8}{'I6pic':>8}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for row in rows:
        typer.echo(
            f"{row['run_id']:<34}"
            f"{row['I1_consensus']:>8.3f}{row['I2_entropy']:>8.3f}"
            f"{row['I3_evacuated']:>8.3f}{row['I4_seconds']:>8.0f}"
            f"{row['I5_max_density']:>8.2f}{row['I6_belief_gap']:>8.3f}"
        )


if __name__ == "__main__":
    app()
