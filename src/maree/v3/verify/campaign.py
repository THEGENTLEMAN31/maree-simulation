"""verify.campaign — le runner de campagne (E2/E1/E4/E5).

Déroule N graines × M configurations sur un même monde, collecte par run
(décisions, appels LLM, coût, indicateurs d'émergence) puis **agrège** —
médiane et dispersion entre graines, jamais deux runs appariés (leçon v2).
La politique : ``rules`` (baseline, zéro appel) ou ``llm``/``hybrid``
(résolutions du modèle via ``llm_alias``, fournisseur ménage ou stub).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import cast

from maree.v3.agents.agent import Agent
from maree.v3.core.ports import ExecutionMode, PolicyName
from maree.v3.sim.bus import EventBus, MemoryBus
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.verify.emergence import emergence_report
from maree.v3.world.worldspec import WorldSpec


@dataclass(frozen=True, slots=True)
class CampConfig:
    name: str
    policy: PolicyName = PolicyName.RULES
    mode: ExecutionMode = ExecutionMode.SYNC
    llm_alias: str | None = None
    #: population par défaut : mix d'archétypes, sorties connues différenciées.
    population: tuple[tuple[str, int, frozenset[str]], ...] = (
        ("habitue", 2, frozenset({"A", "B", "C"})),
        ("visiteur", 3, frozenset({"A", "B"})),
        ("famille", 1, frozenset({"A"})),
    )


@dataclass(slots=True)
class RunResult:
    config: str
    seed: int
    decisions: int
    llm_calls: int
    replis: int
    tokens: int
    wall_s: float
    lag_max: int
    consensus: float
    couplage: float
    emergence: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "config": self.config,
            "seed": self.seed,
            "decisions": self.decisions,
            "llm_calls": self.llm_calls,
            "replis": self.replis,
            "tokens": self.tokens,
            "wall_s": self.wall_s,
            "lag_max": self.lag_max,
            "consensus": self.consensus,
            "couplage": self.couplage,
            "emergence": self.emergence,
        }


def _agents_of(sim: Simulation) -> list[Agent]:
    return [i.agent for i in sim.scene.instances.values()]


def run_once(
    world: WorldSpec,
    config: CampConfig,
    seed: int,
    *,
    bus: EventBus | None = None,
    physics=None,
    run_id_prefix: str = "camp",
    timeline: tuple[Timestep, ...] | None = None,
    physics_steps_per_tick: int = 200,
) -> RunResult:
    """Un run d'une configuration, sur une graine, sur un monde fixé."""
    import time

    bus = bus or MemoryBus()
    sim = Simulation(seed=seed, policy=config.policy, mode=config.mode,
                     bus=bus, run_id=f"{run_id_prefix}_{config.name}_s{seed}",
                     physics=physics, physics_steps_per_tick=physics_steps_per_tick).build(world)
    for archetype, count, known in config.population:
        sim.spawn(archetype, count, known, llm_alias=config.llm_alias)
    steps = timeline or _DEFAULT_TIMELINE
    t0 = time.time()
    sim.run(list(steps))
    wall = time.time() - t0

    report = emergence_report(_agents_of(sim))
    tokens = 0
    for inst in sim.scene.instances.values():
        d = inst.agent._last_decision
        if d and d.llm_trace:
            tokens += d.llm_trace.response.prompt_tokens + d.llm_trace.response.completion_tokens
    return RunResult(
        config=config.name,
        seed=seed,
        decisions=len(sim.log.rows),
        llm_calls=sum(1 for r in sim.log.rows if r.llm_model),
        replis=sum(1 for r in sim.log.rows if r.fallback),
        tokens=tokens,
        wall_s=round(wall, 3),
        lag_max=max((r.lag for r in sim.log.rows), default=0),
        consensus=float(cast("float", report["consensus"])),
        couplage=float(cast("float", report["couplage"])),
        emergence=bool(cast("bool", report["emergence"])),
    )


_DEFAULT_TIMELINE: tuple[Timestep, ...] = (
    Timestep(1),
    Timestep(10, smoke=True),
    Timestep(20, announcement="Veuillez évacuer par la sortie A"),
    Timestep(30),
    Timestep(40),
)


def aggregate(results: list[RunResult]) -> dict[str, object]:
    """Agrège par configuration : médiane et dispersion (E2)."""
    by: dict[str, list[RunResult]] = defaultdict(list)
    for r in results:
        by[r.config].append(r)
    out: dict[str, object] = {}
    for config, rows in by.items():
        def med(key: str, rows: list[RunResult] = rows) -> float:
            vals = sorted(getattr(r, key) for r in rows)
            return round(statistics.median(vals), 3)

        def span(key: str, rows: list[RunResult] = rows) -> tuple[float, float]:
            vals = [getattr(r, key) for r in rows]
            return (min(vals), max(vals))

        out[config] = {
            "n_runs": len(rows),
            "decisions_med": med("decisions"),
            "llm_calls_med": med("llm_calls"),
            "tokens_med": med("tokens"),
            "wall_s_med": med("wall_s"),
            "lag_max_med": med("lag_max"),
            "consensus_med": med("consensus"),
            "couplage_med": med("couplage"),
            "empreinte_emergence": sum(1 for r in rows if r.emergence),
            "decisions_span": span("decisions"),
            "llm_calls_span": span("llm_calls"),
            "tokens_span": span("tokens"),
        }
    return out


__all__ = ["_DEFAULT_TIMELINE", "CampConfig", "RunResult", "aggregate", "run_once"]