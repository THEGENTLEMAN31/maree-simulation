"""H5 — un démenti tardif corrige-t-il l'action engagée ?

Protocole : 60 agents, fumée à t1, la foule part vers la sortie la plus
confiante (A). Un **démenti** (« la sortie A est bloquée ») arrive à t, ou
jamais. On fait varier t.

Trois mesures, et il faut les trois pour répondre :

1. **combien de personnes le démenti atteint** — celles qui sont encore dans
   la salle à t (les sortis n'entendent plus rien) ;
2. **parmi elles, combien changent d'action** — c'est la vraie question H5
   (« la croyance se corrige, l'action engagée non ») ;
3. **quel délai** entre l'annonce et la première décision vers B.

Si (2) vaut 1,0 à tous les instants, H5 est **falsifiée** dans ce modèle :
l'action suit la croyance sans inertie, et ce qui limite l'effet d'un démenti
tardif n'est pas l'engagement, c'est le nombre de gens déjà dehors.

Usage : uv run python scripts/v3_denial.py [graines...] (aucun modèle)
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.verify import scenario_crowd as sc

SEEDS = tuple(int(a) for a in sys.argv[1:]) or (1, 2, 3)
#: instants testés (None = aucun démenti, le témoin).
DENIAL_TICKS: tuple[int | None, ...] = (None, 2, 3, 4, 5, 6, 8)


def one(t_denial: int | None, seed: int) -> dict[str, object]:
    bus = MemoryBus()
    sim = sc.build_sim(PolicyName.RULES, seed=seed, bus=bus, speak=False)
    sim.run(sc.denial_timeline(t_denial))

    snapshots = {
        env.t_prod: env.data["agents"] for env in bus.published("world.snapshot")
    }
    inside = (
        {f"A{int(k):02d}" for k in snapshots.get(t_denial, {})}
        if t_denial is not None
        else set()
    )
    after = {
        row.agent: row.target
        for row in sim.log.rows
        if t_denial is not None
        and row.tick >= t_denial
        and row.action.startswith("évacuer")
        and row.target
    }
    delay = [
        row.tick - t_denial
        for row in sim.log.rows
        if t_denial is not None
        and row.tick >= t_denial
        and row.target == "B"
    ]
    last: dict[str, str] = {}
    for row in sim.log.rows:
        if row.action.startswith("évacuer") and row.target:
            last[row.agent] = row.target
    crowd = bus.published("indicator.crowd")
    return {
        "t_denial": t_denial,
        "seed": seed,
        "encore_present": len(inside),
        "ont_change": sum(1 for a in inside if after.get(a) == "B"),
        "part_change_parmi_presents": (
            round(sum(1 for a in inside if after.get(a) == "B") / len(inside), 3)
            if inside
            else None
        ),
        "delai_median": statistics.median(delay) if delay else None,
        "sortis": len(sim._evacuated),
        "choix_final": dict(Counter(last.values())),
        "I7_s": crowd[-1].data["I7_delay_seconds"],
        "I5_pic": max(e.data["I5_max_density"] for e in crowd),
    }


def main() -> int:
    rows: list[dict[str, object]] = [
        one(t, seed) for t in DENIAL_TICKS for seed in SEEDS
    ]
    by_t: dict[str, list[dict[str, object]]] = {}
    for r in rows:
        by_t.setdefault(str(r["t_denial"]), []).append(r)

    print(f"{'démenti':>8} {'présents':>9} {'changent':>9} {'part':>6} "
          f"{'délai':>6} {'sortie A':>9} {'I7':>5}")
    for t in DENIAL_TICKS:
        group = by_t[str(t)]
        presents = statistics.median(float(r["encore_present"]) for r in group)  # type: ignore[arg-type]
        change = statistics.median(float(r["ont_change"]) for r in group)  # type: ignore[arg-type]
        parts = [
            float(r["part_change_parmi_presents"])  # type: ignore[arg-type]
            for r in group
            if r["part_change_parmi_presents"] is not None
        ]
        delays = [
            float(r["delai_median"])  # type: ignore[arg-type]
            for r in group
            if r["delai_median"] is not None
        ]
        a_final = statistics.median(
            float(r["choix_final"].get("A", 0) if isinstance(r["choix_final"], dict) else 0)  # type: ignore[union-attr]
            for r in group
        )
        print(f"{str(t) if t is not None else 'aucun':>8} {presents:>9.0f} "
              f"{change:>9.0f} {statistics.median(parts) if parts else 0:>6.2f} "
              f"{statistics.median(delays) if delays else 0:>6.0f} {a_final:>9.0f} "
              f"{statistics.median(float(r['I7_s']) for r in group):>5.0f}")  # type: ignore[arg-type]

    out = Path("runs/v3/denial.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nJSON :", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
