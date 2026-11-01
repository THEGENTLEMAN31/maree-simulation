#!/usr/bin/env python3
"""Énergie par run et par bras (E4) — mesurée, pas estimée.

E4 demandait « l'énergie quand elle est mesurable », et le rapport la
donnait pour **un** run (0,46 Wh sur 31,6 s). Une seule mesure ne dit pas
si le tiers « petit modèle » coûte moins de joules que le grand : c'est
pourtant la question que pose E5.

Ce script relit un échantillonnage `nvidia-smi` (1 Hz) et les fenêtres des
runs, et sort des wattheures. Trois précautions, parce qu'un chiffre
d'énergie se croit facilement :

  * **la fenêtre est le run**, pas le processus : du `run.started` au
    `run.ended` (`t_real`), pas du lancement de `uv` à sa sortie ;
  * **le repos est soustrait** : la médiane des échantillons hors run est
    retirée, sinon on compte le bureau, le compositeur et le ventilateur
    comme du coût de simulation. Les deux sont publiés ;
  * **l'échantillon est grossier** : `power.draw` à 1 Hz, intégré par
    trapèzes. C'est une mesure de puissance moyenne, pas un compteur
    d'énergie ; l'écart-type entre runs le dit.

Usage :

    nvidia-smi --query-gpu=timestamp,power.draw --format=csv,noheader,nounits \\
        -l 1 >> /tmp/gpu_power.csv &
    uv run python scripts/energie.py --power /tmp/gpu_power.csv \\
        --experiments x12 x3m
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import statistics as st
from datetime import datetime
from pathlib import Path

_RUN = re.compile(r"^(run_\d{8}-\d{6})")
_SAMPLE = re.compile(
    r"^(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+),\s*([0-9.]+)"
)


def read_power(path: Path) -> list[tuple[float, float]]:
    """(epoch, watts), dans l'ordre du fichier."""
    out: list[tuple[float, float]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _SAMPLE.match(line.strip())
        if not match:
            continue
        stamp = datetime.strptime(match.group(1), "%Y/%m/%d %H:%M:%S.%f")
        out.append((stamp.timestamp(), float(match.group(2))))
    out.sort()
    return out


def run_window(directory: Path) -> tuple[float, float] | None:
    """(début, fin) en epoch, lus dans le nom du run et dans `run.ended`."""
    match = _RUN.match(directory.name)
    if not match:
        return None
    start = datetime.strptime(match.group(1), "run_%Y%m%d-%H%M%S").timestamp()
    ended = None
    events = directory / "events.jsonl"
    if not events.exists():
        return None
    for line in events.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "run.ended":
            ended = float(event.get("t_real") or 0.0)
    if ended is None:
        return None
    return start, start + ended


def integrate(
    samples: list[tuple[float, float]], start: float, end: float, *, idle: float
) -> tuple[float, float]:
    """(Wh au-dessus du repos, Wh totaux) sur [start, end]."""
    window = [(t, p) for t, p in samples if start <= t <= end]
    if len(window) < 2:
        return 0.0, 0.0
    total_j = 0.0
    active_j = 0.0
    for (t0, p0), (t1, p1) in itertools.pairwise(window):
        dt = t1 - t0
        total_j += 0.5 * (p0 + p1) * dt
        active_j += 0.5 * (max(p0 - idle, 0.0) + max(p1 - idle, 0.0)) * dt
    return active_j / 3600.0, total_j / 3600.0


def idle_baseline(
    samples: list[tuple[float, float]], windows: list[tuple[float, float]]
) -> float:
    """Puissance médiane hors de toute fenêtre de run."""
    outside = [
        p
        for t, p in samples
        if not any(start <= t <= end for start, end in windows)
    ]
    return st.median(outside) if outside else 0.0


def median_iqr(values: list[float]) -> str:
    if not values:
        return "—"
    if len(values) == 1:
        return f"{values[0]:.3f}"
    low, _, high = st.quantiles(sorted(values), n=4, method="inclusive")
    return f"{st.median(values):.3f} [{low:.3f}–{high:.3f}]"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--power", type=Path, required=True, help="CSV nvidia-smi")
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument(
        "--experiments",
        nargs="*",
        default=["x12", "x3m"],
        help="protocoles à détailler par bras",
    )
    parser.add_argument("--json", type=Path, help="écrire le détail par run")
    parser.add_argument(
        "--idle",
        type=float,
        help=(
            "puissance de repos en watts ; par défaut la médiane hors runs, "
            "qui est faussée pendant une campagne (le GPU ne retombe jamais "
            "au repos entre deux runs). Mesurer le repos à part : "
            "`nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits -l 1` "
            "pendant une minute sans run."
        ),
    )
    args = parser.parse_args()

    samples = read_power(args.power)
    if len(samples) < 10:
        raise SystemExit(f"échantillon trop court : {len(samples)} points")

    # Un run est rattaché à un bras par son nom (run_x12_deux_tiers_s0_…).
    windows: list[tuple[float, float]] = []
    per_run: list[dict] = []
    for directory in sorted(args.runs.glob("run_*")):
        window = run_window(directory)
        if window is None:
            continue
        windows.append(window)
        per_run.append({"run_id": directory.name, "start": window[0], "end": window[1]})

    idle = args.idle if args.idle is not None else idle_baseline(samples, windows)
    print(f"{len(samples)} échantillons, {len(per_run)} runs, repos médian {idle:.1f} W\n")

    by_arm: dict[tuple[str, str], list[tuple[float, float, float]]] = {}
    for row in per_run:
        start, end = row["start"], row["end"]
        active_wh, total_wh = integrate(samples, start, end, idle=idle)
        row.update(active_wh=active_wh, total_wh=total_wh, seconds=end - start)
        # `run_<protocole>_<bras>_s<graine>_<hash>`
        parts = row["run_id"].split("_")
        protocol = parts[1] if len(parts) > 2 else "?"
        arm = "_".join(parts[2:-2]) if len(parts) > 3 else "?"
        by_arm.setdefault((protocol, arm), []).append(
            (active_wh, total_wh, end - start)
        )

    print("| protocole | bras | n | Wh actifs (médiane [IQR]) | Wh totaux | durée médiane |")
    print("|---|---|---|---|---|---|")
    for (protocol, arm), rows in sorted(by_arm.items()):
        if protocol not in args.experiments:
            continue
        print(
            f"| {protocol} | {arm} | {len(rows)} | "
            f"{median_iqr([r[0] for r in rows])} | "
            f"{median_iqr([r[1] for r in rows])} | "
            f"{st.median([r[2] for r in rows]):.1f} s |"
        )

    if args.json:
        args.json.write_text(
            json.dumps({"idle_w": idle, "runs": per_run}, indent=2),
            encoding="utf-8",
        )
        print(f"\n-> {args.json}")


if __name__ == "__main__":
    main()
