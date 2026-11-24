"""P1.1 — les écarts entre bras sont-ils des écarts, ou du bruit ?

Lit les JSON de campagne (`runs/v3/campaign_crowd*.json`), apparie **par
graine** (même monde, même tirage de positions) et rend, pour chaque paire de
bras :

- les médianes, l'écart des médianes ;
- un **intervalle bootstrap** de cet écart (10 000 tirages, percentile 95 %) ;
- un **test de Wilcoxon signé** (exact pour n ≤ 10, approximé au-delà) ;
- la taille d'échantillon, et le nombre de graines où le sens est le même
  (robustesse).

Pourquoi Wilcoxon signé et pas un t-test : on apparie par graine, les écarts
ne sont pas gaussiens (proportions bornées), et n = 10. Le test approximatif
suffit à dire « ce n'est pas du bruit » — pas à prétendre à trois décimales.

Usage : uv run python scripts/v3_stats.py [fichier.json ...]
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

from scipy.stats import wilcoxon

#: Les campagnes comparables entre elles (même code, mêmes graines).
DEFAULT = (
    Path("runs/v3/campaign_crowd_10seeds.json"),
    Path("runs/v3/campaign_crowd_silence.json"),
    Path("runs/v3/campaign_decision_head.json"),
    Path("runs/v3/campaign_regles.json"),
)
METRIC = "targeted_believed_blocked"


def load(paths: list[Path]) -> dict[tuple[str, str, int], dict[str, object]]:
    """(bras, scénario, graine) -> run. Le dernier fichier gagne."""
    runs: dict[tuple[str, str, int], dict[str, object]] = {}
    for path in paths:
        if not path.exists():
            continue
        for run in json.loads(path.read_text(encoding="utf-8"))["runs"]:
            key = (str(run["arm"]), str(run["scenario"]), int(run["seed"]))
            runs[key] = run
    return runs


def metric(run: dict[str, object]) -> float:
    """Part des décisions dont la cible était crue bloquée au moment de décider."""
    if METRIC not in run:
        raise SystemExit(
            f"champ {METRIC!r} absent d'un run : le JSON date d'avant P0.1, "
            "il faut refaire la campagne (pas comparer des versions de code)."
        )
    decisions = int(run["decisions"]) or 1
    return float(run.get(METRIC, 0)) / decisions


def paired(
    runs: dict[tuple[str, str, int], dict[str, object]],
    left: str,
    right: str,
    scenario: str,
    *,
    draws: int = 10_000,
    seed: int = 7,
) -> dict[str, object] | None:
    seeds = sorted(
        s for (arm, sc, s) in runs if arm == left and sc == scenario
        and (right, scenario, s) in runs
    )
    if len(seeds) < 3:
        return None
    diffs = [metric(runs[(left, scenario, s)]) - metric(runs[(right, scenario, s)]) for s in seeds]
    left_vals = [metric(runs[(left, scenario, s)]) for s in seeds]
    right_vals = [metric(runs[(right, scenario, s)]) for s in seeds]

    rng = random.Random(seed)
    boot = sorted(
        statistics.median(rng.choices(diffs, k=len(diffs))) for _ in range(draws)
    )
    lo, hi = boot[int(0.025 * draws)], boot[int(0.975 * draws) - 1]

    nonzero = [d for d in diffs if abs(d) > 1e-12]
    if len(nonzero) >= 1:
        try:
            stat = wilcoxon(nonzero, alternative="two-sided")
            p_value = float(stat.pvalue)
        except ValueError:
            p_value = 1.0
    else:
        p_value = 1.0
    same_sign = sum(1 for d in diffs if d > 0) if statistics.median(diffs) > 0 else sum(
        1 for d in diffs if d < 0
    )
    return {
        "gauche": left,
        "droite": right,
        "scenario": scenario,
        "n": len(seeds),
        "mediane_gauche": round(statistics.median(left_vals), 3),
        "mediane_droite": round(statistics.median(right_vals), 3),
        "ecart": round(statistics.median(diffs), 3),
        "ic95": [round(lo, 3), round(hi, 3)],
        "p_wilcoxon": round(p_value, 4),
        "graines_dans_le_sens": f"{same_sign}/{len(diffs)}",
    }


def main() -> int:
    paths = [Path(a) for a in sys.argv[1:]] or list(DEFAULT)
    runs = load(paths)
    if not runs:
        print("aucun run lisible dans", [str(p) for p in paths])
        return 1
    arms = sorted({arm for (arm, _sc, _s) in runs})
    scenarios = sorted({sc for (_a, sc, _s) in runs})
    print(f"{len(runs)} runs, bras {arms}, scénarios {scenarios}\n")

    pairs = [
        ("llm_grand", "regles"),
        ("hybride", "regles"),
        ("llm_petit", "regles"),
        ("decision_head", "regles"),
        ("llm_grand", "hybride"),
        ("decision_head", "llm_grand"),
    ]
    rows = []
    for scenario in scenarios:
        for left, right in pairs:
            if left not in arms or right not in arms:
                continue
            result = paired(runs, left, right, scenario)
            if result is None:
                continue
            rows.append(result)
            print(
                f"  {scenario:<14} {left:<14} − {right:<12} "
                f"médianes {result['mediane_gauche']:.2f} vs {result['mediane_droite']:.2f} "
                f"| écart {result['ecart']:+.2f} "
                f"IC95 [{result['ic95'][0]:+.2f} ; {result['ic95'][1]:+.2f}] "
                f"p={result['p_wilcoxon']:.4f} "
                f"| {result['graines_dans_le_sens']} même sens"
            )
    out = Path("runs/v3/stats.json")
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nJSON :", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
