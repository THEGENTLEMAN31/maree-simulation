#!/usr/bin/env python
"""Campagne macro C6 : 4 bras × 2 scénarios × N graines sur le monde calibré.

Usage : uv run python scripts/v3_crowd_campaign.py [graines...]
Prérequis : serveurs 8081 (grand) et 8082 (petit).

Sortie : runs/v3/campaign_crowd.json (runs + agrégat), et un tableau lisible.
Aucune moyenne ne cache un run : médianes **et** intervalles observés.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("MAREE_LLM_URL", "http://127.0.0.1:8081/v1")
os.environ.setdefault("MAREE_LLM_SMALL_URL", "http://127.0.0.1:8082/v1")

from maree.v3 import bootstrap

bootstrap.assemble()

from maree.v3.verify.campaign_crowd import ARMS, aggregate  # noqa: E402

ARGS = [a for a in sys.argv[1:]]
SILENT = "--silent" in ARGS
ARMS_FILTER = None
for arg in ARGS:
    if arg.startswith("--arms="):
        ARMS_FILTER = tuple(arg.split("=", 1)[1].split(","))
SEEDS = tuple(int(a) for a in ARGS if a.isdigit()) or (1, 2, 3, 4, 5)
SCENARIOS = ("split", "contradiction")
SELECTED = tuple(a for a in ARMS if ARMS_FILTER is None or a.name in ARMS_FILTER)
#: Nom de sortie. **On ne réécrit jamais une campagne complète avec un
#: sous-ensemble** : un run filtré (``--arms=``) écrit son propre fichier.
#: C'est une leçon payée le 2026-11-22 (une campagne `decision_head` a écrasé
#: les 60 runs de la campagne 10 graines).
if ARMS_FILTER is None:
    OUT_NAME = "campaign_crowd_silence.json" if SILENT else "campaign_crowd.json"
else:
    suffix = "-".join(ARMS_FILTER)
    OUT_NAME = f"campaign_{suffix}{'_silence' if SILENT else ''}.json"


def main() -> int:
    mode = "SILENCE (null de B3)" if SILENT else "parole active"
    print(
        f"graines {SEEDS} — scénarios {SCENARIOS} — bras {[a.name for a in SELECTED]}"
        f" — {mode}"
    )
    t0 = time.time()
    runs = []
    for arm in SELECTED:
        for scenario in SCENARIOS:
            for seed in SEEDS:
                t_run = time.time()
                from maree.v3.verify.campaign_crowd import run_arm

                r = run_arm(arm, scenario, seed, speak=not SILENT)
                runs.append(r)
                print(
                    f"  {arm.name:<10} {scenario:<14} s{seed}  "
                    f"déc={r.decisions:>3} appels={r.llm_attempted:>3}/{r.llm_ok:<3} "
                    f"jetons={r.tokens:>6} mural={r.wall_s:>6.1f}s "
                    f"évac={r.evacuations:>2}/60 I5={r.indicators['I5_max_density']:.2f} "
                    f"I7={r.indicators['I7_delay_seconds']:.0f}s "
                    f"paroles={r.messages:>3} cible_bloq={r.part_decisions_bloquees:.2f} "
                    f"(dont faute_de_mieux={r.targeted_blocked_least_bad / r.decisions if r.decisions else 0:.2f})",
                    flush=True,
                )
                _ = t_run
    print(f"durée murale : {time.time() - t0:.0f}s")

    agg = aggregate(runs)
    print("\n=== AGRÉGAT (médiane [min–max]) ===")
    for key, a in agg.items():
        print(
            f"  {key:<26} déc={a['decisions_med']:>5.0f} "
            f"appels={a['llm_attempted_med']:>5.0f}/{a['llm_ok_med']:.0f} "
            f"jetons={a['tokens_med']:>7.0f} mural={a['wall_s_med']:>6.1f}s "
            f"| I1={a['I1_med']:.2f} I3={a['I3_med']:.2f} "
            f"I5={a['I5_med']:.2f} {a['I5_span']} I7={a['I7_med']:.0f}s {a['I7_span']} "
            f"| bloq={a['part_decisions_bloquees_med']:.2f} "
            f"résolues={a['target_resolved_med']:.0f} "
            f"| esc={a['escalations']} replis={a['replis']}"
        )

    out = Path("runs/v3")
    out.mkdir(parents=True, exist_ok=True)
    (out / OUT_NAME).write_text(
        json.dumps(
            {
                "seeds": list(SEEDS),
                "scenarios": list(SCENARIOS),
                "runs": [r.as_dict() for r in runs],
                "aggregate": agg,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nJSON : runs/v3/{OUT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
