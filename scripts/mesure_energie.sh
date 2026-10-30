#!/usr/bin/env bash
# E4 — mesure l'énergie d'un run hybride sur la RTX 3050.
#
# Ce n'est pas une mesure de laboratoire : `power.draw` est la puissance
# instantanée de la carte, échantillonnée toutes les 500 ms. On intègre
# sur la durée du run et on soustrait la puissance au repos mesurée avant.
set -euo pipefail

cd "$(dirname "$0")/.."
OUT="${1:-docs/resultats/sobriete-energie.json}"
RUN_ID="${2:-run_energie}"

idle_csv=$(mktemp)
run_csv=$(mktemp)

# 1. repos (5 s, machine au repos, modèles chargés)
nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits -lms 500 > "$idle_csv" &
IDLE_PID=$!
sleep 5
kill "$IDLE_PID" 2>/dev/null || true

# 2. run
nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits -lms 500 > "$run_csv" &
SAMPLE_PID=$!
START=$(date +%s.%N)
LANGCHAIN_TRACING_V2=false uv run maree run bus.backend=memory narrative.enabled=false \
  "run_id=$RUN_ID" > /tmp/opencode/energy_run.json 2>&1 || true
END=$(date +%s.%N)
kill "$SAMPLE_PID" 2>/dev/null || true
sleep 0.6

python3 - "$idle_csv" "$run_csv" "$START" "$END" "$OUT" "$RUN_ID" <<'PY'
import json
import statistics as st
import sys
from pathlib import Path

idle_csv, run_csv, start, end, out, run_id = sys.argv[1:]


def watts(path: str) -> list[float]:
    values = []
    for line in Path(path).read_text().splitlines():
        line = line.strip().replace(" W", "")
        if not line or line in {"N/A", "[N/A]"}:
            continue
        try:
            values.append(float(line))
        except ValueError:
            continue
    return values


idle = watts(idle_csv)
run = watts(run_csv)
duration = float(end) - float(start)
idle_w = st.median(idle) if idle else 0.0
run_w = st.mean(run) if run else 0.0
delta_w = max(0.0, run_w - idle_w)
energy_j = delta_w * duration
payload = {
    "run_id": run_id,
    "gpu": "NVIDIA RTX 3050 (4 Go)",
    "duration_s": round(duration, 1),
    "samples": len(run),
    "idle_w_median": round(idle_w, 1),
    "run_w_mean": round(run_w, 1),
    "delta_w": round(delta_w, 1),
    "energy_j": round(energy_j, 1),
    "energy_wh": round(energy_j / 3600.0, 3),
    "note": (
        "power.draw échantillonné à 0,5 s ; puissance au repos soustraite. "
        "Ordre de grandeur, pas mesure de laboratoire. CPU et RAM exclus."
    ),
}
Path(out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
print(json.dumps(payload, indent=2, ensure_ascii=False))
PY
