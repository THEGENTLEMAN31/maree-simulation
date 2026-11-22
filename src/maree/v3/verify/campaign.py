"""verify.campaign — le runner de campagne **historique** (E2/E1/E4/E5).

> **Dette assumée (2026-11-22).** Ce runner est celui de la première vague :
> il mesure des décisions sur une chronologie générique, sans monde calibré.
> Les campagnes qui portent les conclusions du rapport passent par
> `verify/campaign_crowd.py` (monde `crowd_hall`, physique, scénarios avec
> ambiguïté). Ne pas comparer un chiffre de `campaign.py` à un chiffre de
> `campaign_crowd.py` : ni le monde ni la durée du tick ne sont les mêmes.
> La fusion des deux runners est un chantier, pas un oubli.

Déroule N graines × M configurations sur un même monde, collecte par run
(décisions, coût, indicateurs de foule et d'émergence) puis **agrège** —
médiane et dispersion entre graines, jamais deux runs appariés (leçon v2).

Correctif C4 : le coût se lit **sur les lignes du journal**, pas sur la
dernière décision de chaque agent. L'ancienne lecture ne comptait qu'un appel
par agent — un agent qui reconsidérait dix fois n'en comptait qu'un — et
attribuait les jetons du dernier appel au run entier. On publie désormais :
appels **tentés**, appels **réussis**, jetons, et la part du temps mural
passée dans le LLM (`wall_llm`, somme des latences mesurées) séparément du
temps de physique.
"""

from __future__ import annotations

import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import cast

from maree.v3.agents.agent import Agent
from maree.v3.core.ports import ExecutionMode, PolicyName
from maree.v3.sim.bus import EventBus, EventEnvelope, MemoryBus
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.verify.emergence import emergence_report
from maree.v3.verify.indicators import KEYS, summarise
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
    llm_attempted: int
    llm_ok: int
    replis: int
    replis_par_cause: dict[str, int]
    tokens_prompt: int
    tokens_completion: int
    wall_s: float
    wall_llm_s: float
    wall_physics_s: float
    lag_max: int
    escalations: dict[str, int]
    indicators: dict[str, float] = field(default_factory=dict)
    consensus: float = 0.0
    couplage: float = 0.0
    social_excess: float = 0.0
    emergence: bool = False

    @property
    def tokens(self) -> int:
        return self.tokens_prompt + self.tokens_completion

    def as_dict(self) -> dict[str, object]:
        return {
            "config": self.config,
            "seed": self.seed,
            "decisions": self.decisions,
            "llm_attempted": self.llm_attempted,
            "llm_ok": self.llm_ok,
            "replis": self.replis,
            "replis_par_cause": self.replis_par_cause,
            "tokens": self.tokens,
            "tokens_prompt": self.tokens_prompt,
            "tokens_completion": self.tokens_completion,
            "wall_s": self.wall_s,
            "wall_llm_s": self.wall_llm_s,
            "wall_physics_s": self.wall_physics_s,
            "lag_max": self.lag_max,
            "escalations": self.escalations,
            "indicators": self.indicators,
            "consensus": self.consensus,
            "couplage": self.couplage,
            "social_excess": self.social_excess,
            "emergence": self.emergence,
        }


def _agents_of(sim: Simulation) -> list[Agent]:
    return [i.agent for i in sim.scene.instances.values()]


class _RecordingBus:
    """Bus qui garde les enveloppes publiées (quel que soit le bus sous-jacent).

    ``MemoryBus.published`` n'existe que pour le bus mémoire ; en campagne on
    veut les mêmes comptes avec n'importe quel bus (Redpanda compris).
    """

    def __init__(self, inner: EventBus) -> None:
        self.inner = inner
        self.envelopes: list[EventEnvelope] = []

    def publish(self, envelope: EventEnvelope) -> None:
        self.envelopes.append(envelope)
        self.inner.publish(envelope)

    def close(self) -> None:
        self.inner.close()

    def of_type(self, event_type: str) -> list[EventEnvelope]:
        return [e for e in self.envelopes if e.type == event_type]


def _crowd_series(recorder: _RecordingBus) -> list[dict[str, object]]:
    """Les I1–I7 publiés pendant le run (une trame par tick)."""
    return [
        cast("dict[str, object]", env.data)
        for env in recorder.of_type("indicator.crowd")
    ]


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
    recorder = _RecordingBus(bus or MemoryBus())
    sim = Simulation(
        seed=seed,
        policy=config.policy,
        mode=config.mode,
        bus=recorder,
        run_id=f"{run_id_prefix}_{config.name}_s{seed}",
        physics=physics,
        physics_steps_per_tick=physics_steps_per_tick,
    ).build(world)
    for archetype, count, known in config.population:
        sim.spawn(archetype, count, known, llm_alias=config.llm_alias)
    steps = timeline or _DEFAULT_TIMELINE
    t0 = time.perf_counter()
    sim.run(list(steps))
    wall = time.perf_counter() - t0

    rows = sim.log.rows
    causes = Counter(r.fallback_cause or "inconnue" for r in rows if r.fallback)
    escalations = Counter(
        str(env.data["cause"])
        for env in recorder.of_type("agent.escalation")
        if isinstance(env.data.get("cause"), str)
    )
    active = [
        inst.agent
        for agent_id, inst in sim.scene.instances.items()
        if agent_id.uid not in sim._evacuated
    ]
    report = emergence_report(active, seed=seed)
    series = _crowd_series(recorder)
    crowd = summarise(series) if series else {key: 0.0 for key in KEYS}
    return RunResult(
        config=config.name,
        seed=seed,
        decisions=len(rows),
        llm_attempted=sum(1 for r in rows if r.llm_attempted),
        llm_ok=sum(1 for r in rows if r.llm_ok),
        replis=sum(causes.values()),
        replis_par_cause=dict(sorted(causes.items())),
        tokens_prompt=sum(r.prompt_tokens for r in rows),
        tokens_completion=sum(r.completion_tokens for r in rows),
        wall_s=round(wall, 3),
        wall_llm_s=round(sum(r.latency_s for r in rows), 3),
        wall_physics_s=round(sim.wall_physics_s, 3),
        lag_max=max((r.lag for r in rows), default=0),
        escalations=dict(sorted(escalations.items())),
        indicators={key: round(crowd[key], 4) for key in KEYS},
        consensus=float(cast("float", report["consensus"])),
        couplage=float(cast("float", report["couplage"])),
        social_excess=float(cast("float", report["social_excess"])),
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
            vals = sorted(float(getattr(r, key)) for r in rows)
            return round(statistics.median(vals), 3)

        def span(key: str, rows: list[RunResult] = rows) -> tuple[float, float]:
            vals = [float(getattr(r, key)) for r in rows]
            return (min(vals), max(vals))

        def med_ind(key: str, rows: list[RunResult] = rows) -> float:
            vals = sorted(r.indicators.get(key, 0.0) for r in rows)
            return round(statistics.median(vals), 3)

        out[config] = {
            "n_runs": len(rows),
            "decisions_med": med("decisions"),
            "llm_attempted_med": med("llm_attempted"),
            "llm_ok_med": med("llm_ok"),
            "replis_med": med("replis"),
            "tokens_med": med("tokens"),
            "wall_s_med": med("wall_s"),
            "wall_llm_s_med": med("wall_llm_s"),
            "wall_physics_s_med": med("wall_physics_s"),
            "lag_max_med": med("lag_max"),
            "consensus_med": med("consensus"),
            "couplage_med": med("couplage"),
            "social_excess_med": med("social_excess"),
            "empreinte_emergence": sum(1 for r in rows if r.emergence),
            "decisions_span": span("decisions"),
            "llm_attempted_span": span("llm_attempted"),
            "tokens_span": span("tokens"),
            "I1_med": med_ind("I1_consensus"),
            "I2_med": med_ind("I2_entropy"),
            "I3_med": med_ind("I3_evacuated"),
            "I4_med": med_ind("I4_seconds"),
            "I5_med": med_ind("I5_max_density"),
            "I6_med": med_ind("I6_belief_gap"),
            "I7_med": med_ind("I7_delay_seconds"),
        }
    return out


__all__ = ["_DEFAULT_TIMELINE", "CampConfig", "RunResult", "aggregate", "run_once"]
