"""Échantillon de mondes (P1.2) — la bande de calibration tient-elle ailleurs ?

Cinq salles de même distribution (20–24 × 14–18 m, deux issues de 1,1–1,3 m),
trois graines chacune, bras `règles`, sans parole (mesure de la physique, pas
du modèle). On vérifie le critère **pré-enregistré** :

    I5 pic ∈ [0,8 ; 1,6] pers/m², pic après le spawn, 60/60 sortis.

Usage : uv run python scripts/v3_worlds.py [n_mondes]
Aucun modèle, aucun GPU.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from maree.v3.core.ports import PolicyName
from maree.v3.verify import scenario_crowd as sc
from maree.v3.verify import worlds

N_WORLDS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
RUN_SEEDS = (1, 2, 3)
BAND = (0.8, 1.6)


def main() -> int:
    rows: list[dict[str, object]] = []
    print(f"{'monde':>6} {'salle':>10} {'issue':>6} {'I5 pic':>7} {'I7':>5} "
          f"{'I3':>5} {'pic t':>6}")
    for ws in range(1, N_WORLDS + 1):
        spec = worlds.draw(ws)
        world = worlds.build(spec)
        peaks: list[float] = []
        delays: list[float] = []
        evacuations: list[int] = []
        ticks: list[int] = []
        for rs in RUN_SEEDS:
            r = sc.measure(PolicyName.RULES, seed=rs, world=world, speak=False)
            summary = r["summary"]
            peaks.append(float(summary["I5_max_density"]))
            delays.append(float(summary["I7_delay_seconds"]))
            evacuations.append(int(r["evacuated"]))
            ticks.append(int(r["peak_tick"]))
        med_peak = statistics.median(peaks)
        row = {
            **spec.as_dict(),
            "I5_pic": round(med_peak, 3),
            "I5_pic_span": [round(min(peaks), 3), round(max(peaks), 3)],
            "I7_s": round(statistics.median(delays), 1),
            "evacuated": evacuations,
            "peak_tick": ticks,
            "dans_la_bande": BAND[0] <= med_peak <= BAND[1],
            "pic_apres_spawn": all(t >= 3 for t in ticks),
        }
        rows.append(row)
        print(f"{ws:>6} {spec.width:.1f}x{spec.height:.1f} {spec.exit_width:>6.2f} "
              f"{med_peak:>7.2f} {row['I7_s']:>5.0f} "
              f"{min(evacuations):>5} {min(ticks):>6}")

    dans = sum(1 for r in rows if r["dans_la_bande"])
    apres = sum(1 for r in rows if r["pic_apres_spawn"])
    complets = sum(1 for r in rows if min(r["evacuated"]) == 60)  # type: ignore[arg-type]
    print(f"\n{dans}/{len(rows)} mondes dans la bande {BAND}, "
          f"{apres}/{len(rows)} pics après le spawn, {complets}/{len(rows)} vidés")
    out = Path("runs/v3/worlds.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"bande": BAND, "run_seeds": list(RUN_SEEDS), "mondes": rows},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print("JSON :", out)
    return 0 if dans == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
