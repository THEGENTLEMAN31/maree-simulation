"""Fusionne des campagnes en un seul artefact publiable.

Pourquoi ce script existe : le fichier qui porte les chiffres du rapport
(`runs/v3/campaign_crowd_10seeds.json`) est le **résultat de plusieurs
campagnes** — trois bras lancés ensemble, le classifieur lancé à part (il
demande un autre serveur), et le bras `regles` relancé avec le champ de
croyance. Sans fusion outillée, cet artefact n'était pas reproductible : il
avait été assemblé à la main.

Règle : la **dernière** campagne gagne pour une clé (bras, scénario, graine).
Un champ absent (`None`) n'écrase pas un champ présent.

Usage :
    uv run python scripts/v3_merge_campaigns.py \
        --out runs/v3/campaign_crowd_10seeds.json \
        runs/v3/campaign_regles-hybride-llm_grand.json \
        runs/v3/campaign_decision_head.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    out: Path | None = None
    inputs: list[Path] = []
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--out" and i + 1 < len(args):
            out = Path(args[i + 1])
            i += 2
            continue
        inputs.append(Path(args[i]))
        i += 1
    if out is None or not inputs:
        print(__doc__)
        return 2

    merged: dict[tuple[str, str, int], dict[str, object]] = {}
    for path in inputs:
        if not path.exists():
            print(f"absent : {path}")
            return 1
        for run in json.loads(path.read_text(encoding="utf-8"))["runs"]:
            key = (str(run["arm"]), str(run["scenario"]), int(run["seed"]))
            previous = merged.get(key)
            if previous is not None:
                # un None n'écrase pas une valeur mesurée
                run = {
                    k: (previous.get(k) if v is None and previous.get(k) is not None else v)
                    for k, v in {**previous, **run}.items()
                }
            merged[key] = run

    runs = list(merged.values())
    payload = {
        "seeds": sorted({k[2] for k in merged}),
        "arms": sorted({k[0] for k in merged}),
        "sources": [str(p) for p in inputs],
        "runs": runs,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(runs)} runs fusionnés -> {out}")
    print("bras :", payload["arms"], "| graines :", payload["seeds"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
