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
    #: modèle de décision System 1 (P3.1) : distribution sur options fermées.
    Arm("decision_head", PolicyName.DECISION_HEAD),
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
    speak: bool = True
    messages: int = 0
    escalations: dict[str, int] = field(default_factory=dict)
    replis: dict[str, int] = field(default_factory=dict)
    targeted_blocked: int = 0
    #: décisions dont la cible était **crue bloquée au moment de décider**.
    #: C'est la mesure propre : le compteur `targeted_blocked` ci-dessus suit la
    #: porte **désignée** à t1, que la croyance peut avoir oubliée depuis.
    targeted_believed_blocked: int = 0
    #: décisions vers la porte **désignée bloquée à t1** (celle qu'on lui a
    #: annoncée), quand aucune autre n'était crue praticable : ce n'est pas une
    #: erreur, c'est un monde sans option.
    targeted_blocked_least_bad: int = 0
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
            "speak": self.speak,
            "messages": self.messages,
            "escalations": self.escalations,
            "replis": self.replis,
            "targeted_blocked": self.targeted_blocked,
            "targeted_believed_blocked": self.targeted_believed_blocked,
            "targeted_blocked_least_bad": self.targeted_blocked_least_bad,
            "target_resolved": self.target_resolved,
            "evacuations": self.evacuations,
            "indicators": self.indicators,
        }

    @property
    def part_decisions_bloquees(self) -> float:
        return self.targeted_blocked / self.decisions if self.decisions else 0.0


def run_arm(
    arm: Arm, scenario: str, seed: int, *, speak: bool = True
) -> CrowdRun:
    """Un run d'un bras, journalisé et compté par décision.

    ``speak=False`` est le **null** de B3 : le même monde, la même politique,
    les mêmes croyances initiales, mais aucune émission. Il doit être joué
    avec le **même code** que le bras observé : deux runs séparés par une
    version de code ne comparent rien.
    """
    bus = MemoryBus()
    sim = sc.build_sim(arm.policy, seed=seed, bus=bus, alias=arm.alias, speak=speak)
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
    # Définition exacte du compteur : `target == la porte annoncée bloquée à
    # t1 pour cet agent`. Ce n'est pas « la porte qu'il croit bloquée
    # maintenant » : la croyance de danger s'oublie (decay 0,98 par décision)
    # et un ouï-dire peut la repasser sous le seuil 0,5. Le chiffre mesure donc
    # un **scénario** (« revenir vers la porte qu'on lui a dite fermée »), pas
    # un état de croyance instantané — c'est le choix de mesure, pas un
    # raccourci.
    targeted_rows = [
        row
        for row in rows
        if row.target is not None and believed.get(row.agent) == row.target
    ]
    targeted = len(targeted_rows)
    least_bad = sum(1 for row in targeted_rows if row.target_least_bad)
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
        speak=speak,
        messages=len(bus.published("agent.message")),
        escalations=dict(sorted(escalations.items())),
        replis=dict(sorted(replis.items())),
        targeted_blocked=targeted,
        targeted_believed_blocked=sum(
            1 for row in rows if row.target_believed_blocked
        ),
        targeted_blocked_least_bad=least_bad,
        target_resolved=sum(1 for r in rows if r.target_resolved),
        evacuations=sum(1 for _ in sim._evacuated),
        indicators=summary,
    )


def campaign(
    *,
    arms: tuple[Arm, ...] = ARMS,
    scenarios: tuple[str, ...] = ("split", "contradiction"),
    seeds: tuple[int, ...] = (1, 2, 3, 4, 5),
    speak: bool = True,
) -> list[CrowdRun]:
    """Déroule bras × scénarios × graines (ordre déterministe)."""
    out: list[CrowdRun] = []
    for arm in arms:
        for scenario in scenarios:
            for seed in seeds:
                out.append(run_arm(arm, scenario, seed, speak=speak))
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
            "messages_med": _med([float(r.messages) for r in rows]),
            "part_decisions_bloquees_med": _med(
                [r.part_decisions_bloquees for r in rows]
            ),
            "part_believed_blocked_med": _med(
                [
                    (r.targeted_believed_blocked / r.decisions if r.decisions else 0.0)
                    for r in rows
                ]
            ),
            "believed_blocked_med": _med(
                [float(r.targeted_believed_blocked) for r in rows]
            ),
            "target_resolved_med": _med([float(r.target_resolved) for r in rows]),
            "least_bad_med": _med([float(r.targeted_blocked_least_bad) for r in rows]),
            "part_bloquees_least_bad_med": _med(
                [
                    (r.targeted_blocked_least_bad / r.decisions if r.decisions else 0.0)
                    for r in rows
                ]
            ),
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
