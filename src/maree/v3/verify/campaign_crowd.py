"""verify.campaign_crowd — la campagne macro (C6) : trois bras, deux scénarios.

Ce module assemble ce que C2–C5 ont rendu mesurable : la même salle calibrée,
la même foule, la même physique, et trois façons de décider — avec le coût
compté par décision. Les scénarios contiennent **l'ambiguïté** ; sans elle, le
bras hybride ne fait aucun appel (c'est sa définition, pas un défaut).

Scénarios :

- ``split`` : moitié « A bloquée », moitié « B bloquée » ; les deux portes
  restent physiquement ouvertes. La bonne réponse est de contourner ce que
  l'on croit fermé.
- ``contradiction`` : mêmes croyances, plus une annonce officielle qui nomme
  **A** — donc une consigne qui contredit la croyance d'un agent sur deux.

Mesures par run : I1–I7, décisions, appels tentés/réussis, jetons, temps mural
et temps LLM, escalades par cause, replis par cause, et la part des décisions
qui visent une porte **crue bloquée** (D14). Aucune moyenne ne cache un run :
les médianes sont publiées avec leur intervalle observé.
"""

from __future__ import annotations

import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.verify import scenario_crowd as sc


@dataclass(frozen=True, slots=True)
class Arm:
    """Un bras : un nom pour les tables, une politique, un alias de modèle."""

    name: str
    policy: PolicyName
    alias: str | None = None


#: Les bras comparés. ``grand`` et ``petit`` sont le **même** bras ``llm`` avec
#: deux tailles de modèle : c'est l'axe « la taille compte-t-elle ? ».
ARMS: tuple[Arm, ...] = (
    Arm("regles", PolicyName.RULES),
    Arm("hybride", PolicyName.HYBRID, "decision"),
    Arm("llm_grand", PolicyName.LLM, "decision"),
    Arm("llm_petit", PolicyName.LLM, "petit"),
)


@dataclass(slots=True)
class CrowdRun:
    arm: str
    scenario: str
    seed: int
    decisions: int
    llm_attempted: int
    llm_ok: int
    tokens: int
    wall_s: float
    escalations: dict[str, int] = field(default_factory=dict)
    replis: dict[str, int] = field(default_factory=dict)
    targeted_blocked: int = 0
    target_resolved: int = 0
    evacuations: int = 0
    indicators: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "arm": self.arm,
            "scenario": self.scenario,
            "seed": self.seed,
            "decisions": self.decisions,
            "llm_attempted": self.llm_attempted,
            "llm_ok": self.llm_ok,
            "tokens": self.tokens,
            "wall_s": self.wall_s,
            "escalations": self.escalations,
            "replis": self.replis,
            "targeted_blocked": self.targeted_blocked,
            "target_resolved": self.target_resolved,
            "evacuations": self.evacuations,
            "indicators": self.indicators,
        }

    @property
    def part_decisions_bloquees(self) -> float:
        return self.targeted_blocked / self.decisions if self.decisions else 0.0


def run_arm(arm: Arm, scenario: str, seed: int) -> CrowdRun:
    """Un run d'un bras, journalisé et compté par décision."""
    bus = MemoryBus()
    sim = sc.build_sim(arm.policy, seed=seed, bus=bus, alias=arm.alias)
    steps = (
        sc.split_timeline(seed)
        if scenario == "split"
        else sc.contradiction_timeline(seed)
        if scenario == "contradiction"
        else sc.timeline()
    )
    t0 = time.perf_counter()
    sim.run(steps)
    wall = time.perf_counter() - t0

    rows = sim.log.rows
    # la porte que l'agent **croit** bloquée : le message de t1 la nomme
    believed: dict[str, str] = {}
    for agent_uid, message in steps[0].messages:
        if message.fact.startswith("La sortie "):
            believed[f"A{agent_uid:02d}"] = message.fact.split()[2]
    targeted = sum(
        1
        for row in rows
        if row.target is not None and believed.get(row.agent) == row.target
    )
    escalations = Counter(
        str(env.data["cause"]) for env in bus.published("agent.escalation")
    )
    replis = Counter(row.fallback_cause or "inconnue" for row in rows if row.fallback)
    series = [dict(env.data) for env in bus.published("indicator.crowd")]
    summary = sc.summarise_series(series)
    return CrowdRun(
        arm=arm.name,
        scenario=scenario,
        seed=seed,
        decisions=len(rows),
        llm_attempted=sum(1 for r in rows if r.llm_attempted),
        llm_ok=sum(1 for r in rows if r.llm_ok),
        tokens=sum(r.prompt_tokens + r.completion_tokens for r in rows),
        wall_s=round(wall, 2),
        escalations=dict(sorted(escalations.items())),
        replis=dict(sorted(replis.items())),
        targeted_blocked=targeted,
        target_resolved=sum(1 for r in rows if r.target_resolved),
        evacuations=sum(1 for _ in sim._evacuated),
        indicators=summary,
    )


def campaign(
    *,
    arms: tuple[Arm, ...] = ARMS,
    scenarios: tuple[str, ...] = ("split", "contradiction"),
    seeds: tuple[int, ...] = (1, 2, 3, 4, 5),
) -> list[CrowdRun]:
    """Déroule bras × scénarios × graines (ordre déterministe)."""
    out: list[CrowdRun] = []
    for arm in arms:
        for scenario in scenarios:
            for seed in seeds:
                out.append(run_arm(arm, scenario, seed))
    return out


def _med(values: list[float]) -> float:
    return round(statistics.median(values), 3) if values else 0.0


def aggregate(runs: list[CrowdRun]) -> dict[str, Any]:
    """Médianes et intervalles observés, par bras × scénario."""
    grouped: dict[tuple[str, str], list[CrowdRun]] = {}
    for run in runs:
        grouped.setdefault((run.arm, run.scenario), []).append(run)
    out: dict[str, Any] = {}
    for (arm, scenario), rows in grouped.items():
        def ind(key: str, rows: list[CrowdRun] = rows) -> float:
            return _med([float(r.indicators.get(key, 0.0)) for r in rows])

        def span(key: str, rows: list[CrowdRun] = rows) -> list[float]:
            vals = [float(r.indicators.get(key, 0.0)) for r in rows]
            return [round(min(vals), 3), round(max(vals), 3)]

        out[f"{arm}|{scenario}"] = {
            "n_runs": len(rows),
            "decisions_med": _med([float(r.decisions) for r in rows]),
            "llm_attempted_med": _med([float(r.llm_attempted) for r in rows]),
            "llm_ok_med": _med([float(r.llm_ok) for r in rows]),
            "tokens_med": _med([float(r.tokens) for r in rows]),
            "wall_s_med": _med([r.wall_s for r in rows]),
            "part_decisions_bloquees_med": _med(
                [r.part_decisions_bloquees for r in rows]
            ),
            "target_resolved_med": _med([float(r.target_resolved) for r in rows]),
            "evacuations_med": _med([float(r.evacuations) for r in rows]),
            "I1_med": ind("I1_consensus"),
            "I2_med": ind("I2_entropy"),
            "I3_med": ind("I3_evacuated"),
            "I5_med": ind("I5_max_density"),
            "I7_med": ind("I7_delay_seconds"),
            "I5_span": span("I5_max_density"),
            "I7_span": span("I7_delay_seconds"),
            "escalations": dict(
                sorted(
                    Counter(
                        cause
                        for r in rows
                        for cause, n in r.escalations.items()
                        for _ in range(n)
                    ).items()
                )
            ),
            "replis": dict(
                sorted(
                    Counter(
                        cause
                        for r in rows
                        for cause, n in r.replis.items()
                        for _ in range(n)
                    ).items()
                )
            ),
        }
    return out


__all__ = ["ARMS", "Arm", "CrowdRun", "aggregate", "campaign", "run_arm"]
