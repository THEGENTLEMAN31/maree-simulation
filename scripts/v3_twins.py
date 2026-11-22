"""Mission n°1 — la divergence vient de la mémoire, et elle survit à la foule.

Deux expériences, deux échelles :

**A. Décision seule** (`verify/twins.py`, sans physique). Deux cohortes de
jumeaux : mêmes traits, même archétype, mêmes sorties connues, même scénario
public, **histoires personnelles opposées** (« A est bloquée » contre « B est
bloquée »). On mesure l'accord des paires, et l'ablation (mémoire coupée) qui
doit faire disparaître la divergence.

**B. En foule** (60 agents, JuPedSim, monde calibré). Même design, mais les
deux cohortes sont dans le **même** monde au même moment. Ce que l'on mesure
n'est plus un choix déclaré : c'est la porte que le corps prend réellement.

Usage : uv run python scripts/v3_twins.py [n_paires] [graines...]
Aucun modèle requis (règles) ; aucun GPU.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from maree.v3.agents.perception import Message
from maree.v3.agents.preference import preferred_exit
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.verify import scenario_crowd as sc
from maree.v3.verify.twins import (
    PublicEvent,
    TwinHistory,
    run_twins_experiment,
)

#: Chronologie **sans annonce nommant une porte** : sinon l'ordre officiel
#: écrase la mémoire personnelle (mesuré : les deux cohortes prenaient A).
#: On veut isoler l'effet de l'histoire personnelle, une variable à la fois.
TIMELINE: tuple[PublicEvent, ...] = (
    PublicEvent(1),
    PublicEvent(5, smoke=True),
    PublicEvent(10, smoke=True),
)

N_PAIRS = int(sys.argv[1]) if len(sys.argv) > 1 else 200
SEEDS = tuple(int(a) for a in sys.argv[2:]) or (1, 2, 3, 4, 5)

#: Histoires opposées, **même forme** de message : seule la lettre change.
LEFT = TwinHistory(
    "A bloquée",
    [
        (1, Message("La sortie A est bloquée", AgentId(900), 1, 0.9)),
    ],
)
RIGHT = TwinHistory(
    "B bloquée",
    [
        (1, Message("La sortie B est bloquée", AgentId(900), 1, 0.9)),
    ],
)


def part_a() -> dict[str, object]:
    """Décision seule : divergence entre jumeaux, avec et sans mémoire."""
    with_memory = run_twins_experiment(
        timeline=TIMELINE,
        left_history=LEFT,
        right_history=RIGHT,
        archetype="visiteur",
        known_exits=frozenset({"A", "B"}),
        n_pairs=N_PAIRS,
        memory_on=True,
    )
    ablated = run_twins_experiment(
        timeline=TIMELINE,
        left_history=LEFT,
        right_history=RIGHT,
        archetype="visiteur",
        known_exits=frozenset({"A", "B"}),
        n_pairs=N_PAIRS,
        memory_on=False,
    )
    return {
        "n_pairs": N_PAIRS,
        "memoire": {
            "accord": round(float(with_memory["agreement_ratio"]), 3),  # type: ignore[arg-type]
            "kl": round(float(with_memory["kl_divergence"]), 3),  # type: ignore[arg-type]
            "gauche": with_memory["left_distribution"],
            "droite": with_memory["right_distribution"],
        },
        "ablation_sans_memoire": {
            "accord": round(float(ablated["agreement_ratio"]), 3),  # type: ignore[arg-type]
            "kl": round(float(ablated["kl_divergence"]), 3),  # type: ignore[arg-type]
        },
    }


def _crowd_cohorts(seed: int, memory: bool) -> dict[str, object]:
    """60 agents, deux cohortes, un seul monde : la porte réellement prise."""
    bus = MemoryBus()
    sim = sc.build_sim(PolicyName.RULES, seed=seed, bus=bus, speak=False,
                       agents=sc.N_AGENTS)
    steps = sc.split_timeline(seed)
    believed: dict[str, str] = {}
    if memory:
        for uid, msg in steps[0].messages:
            believed[f"A{uid:02d}"] = msg.fact.split()[2]
        sim.run(steps)
    else:
        # ablation : même monde, mêmes positions, messages non délivrés
        stripped = [
            sc.Timestep(t.tick, smoke=t.smoke, hazard_origin=t.hazard_origin)
            for t in steps
        ]
        sim.run(stripped)

    # la porte visée = cible du dernier EVACUER, sinon préférence de croyance
    chosen: dict[str, str | None] = {}
    for row in sim.log.rows:
        if row.action.startswith("évacuer") and row.target:
            chosen[row.agent] = row.target
    avoided = total = 0
    for name, label in believed.items():
        target = chosen.get(name)
        if target is None:
            agent = next(
                i.agent for i in sim.scene.instances.values() if i.agent.name == name
            )
            target = preferred_exit(agent)
        if target is None:
            continue
        total += 1
        avoided += int(target != label)
    return {
        "seed": seed,
        "agents": sc.N_AGENTS,
        "evacuated": sum(1 for _ in sim._evacuated),
        "ignore_sa_porte_crue_bloquee": round(avoided / total, 3) if total else 0.0,
        "n": total,
    }


def part_b() -> dict[str, object]:
    with_memory = [_crowd_cohorts(seed, True) for seed in SEEDS]
    ablated = [_crowd_cohorts(seed, False) for seed in SEEDS]

    def med(rows: list[dict[str, object]], key: str) -> float:
        vals = sorted(float(r[key]) for r in rows)  # type: ignore[arg-type]
        return vals[len(vals) // 2]

    return {
        "avec_memoire": {
            "mediane": med(with_memory, "ignore_sa_porte_crue_bloquee"),
            "detail": with_memory,
        },
        "ablation": {
            "mediane": med(ablated, "ignore_sa_porte_crue_bloquee"),
            "detail": ablated,
        },
    }


def main() -> int:
    a = part_a()
    b = part_b()
    out = {"protocole": "twins v3 (règles, sans modèle)", "A_decision_seule": a,
           "B_foule": b}
    print("=== A. décision seule (" + str(N_PAIRS) + " paires) ===")
    print("  avec mémoire :", a["memoire"])
    print("  sans mémoire :", a["ablation_sans_memoire"])
    print("=== B. foule calibrée (" + str(len(SEEDS)) + " graines, 60 agents) ===")
    print("  avec mémoire : ignore sa porte crue bloquée à",
          b["avec_memoire"]["mediane"])
    print("  sans mémoire : ignore sa porte crue bloquée à",
          b["ablation"]["mediane"])
    path = Path("runs/v3/twins.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nJSON :", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
