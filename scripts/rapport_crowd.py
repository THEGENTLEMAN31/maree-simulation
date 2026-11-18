#!/usr/bin/env python
"""Rend runs/v3/campaign_crowd.json en tables markdown (C6).

Usage : uv run python scripts/rapport_crowd.py [chemin.json]
Sortie : docs/v3/resultats-c6.md (remplacé), et le tableau sur stdout.

Aucune valeur n'est calculée ici : tout vient du JSON produit par
scripts/v3_crowd_campaign.py. Ce script ne fait que mettre en forme, pour que
le rapport ne puisse pas diverger des mesures.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DEFAULT = Path("runs/v3/campaign_crowd.json")
OUT = Path("docs/v3/resultats-c6.md")


def _f(value: Any, digits: int = 2) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "—"


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    data = json.loads(path.read_text(encoding="utf-8"))
    seeds = data["seeds"]
    scenarios = data["scenarios"]
    agg: dict[str, dict[str, Any]] = data["aggregate"]

    lines: list[str] = []
    lines.append("# Résultats de la campagne macro (C6)\n")
    lines.append(
        f"Monde : `crowd_hall` (22 × 16 m, deux issues de 1,2 m), 60 agents, "
        f"tick de 2 s. Graines : {', '.join(str(s) for s in seeds)} — "
        f"scénarios : {', '.join(scenarios)}.\n"
    )
    lines.append(
        "Chaque ligne est la **médiane** des runs du bras ; `[min–max]` donne "
        "l'intervalle observé, jamais un écart-type qui masquerait un run.\n"
    )

    header = (
        "| bras | scénario | décisions | appels (ok) | jetons | mural (s) | "
        "I1 | I3 | I5 [min–max] | I7 s [min–max] | décisions vers porte crue bloquée | "
        "cibles résolues par le moteur |"
    )
    lines.append(header)
    lines.append("|" + "---|" * 13)
    for key in sorted(agg):
        arm, scenario = key.split("|")
        a = agg[key]
        span5 = a["I5_span"]
        span7 = a["I7_span"]
        lines.append(
            f"| `{arm}` | {scenario} | {_f(a['decisions_med'], 0)} | "
            f"{_f(a['llm_attempted_med'], 0)} ({_f(a['llm_ok_med'], 0)}) | "
            f"{_f(a['tokens_med'], 0)} | {_f(a['wall_s_med'], 1)} | "
            f"{_f(a['I1_med'])} | {_f(a['I3_med'])} | "
            f"{_f(a['I5_med'])} [{_f(span5[0])}–{_f(span5[1])}] | "
            f"{_f(a['I7_med'], 0)} [{_f(span7[0], 0)}–{_f(span7[1], 0)}] | "
            f"{_f(a['part_decisions_bloquees_med'])} | "
            f"{_f(a['target_resolved_med'], 0)} |"
        )

    lines.append("\n## Escalades et replis, par cause et par bras\n")
    lines.append("| bras | scénario | escalades | replis |")
    lines.append("|---|---|---|---|")
    for key in sorted(agg):
        arm, scenario = key.split("|")
        a = agg[key]
        lines.append(
            f"| `{arm}` | {scenario} | {a['escalations'] or '—'} | {a['replis'] or '—'} |"
        )

    lines.append(
        "\n## Ce que ces tables ne disent pas\n\n"
        "- I6 n'apparaît pas : aucune porte ne ferme dans ce scénario, donc I6 "
        "vaut 0 **par construction**.\n"
        "- Les temps absolus ne sont pas des temps de terrain : ce modèle passe "
        "≈3,2 pers/(m·s) par mètre de porte contre ≈1,3 en littérature "
        "(ADR-015). Les comparaisons entre bras, elles, tiennent.\n"
        "- Une « cible résolue par le moteur » n'est pas une réussite du modèle : "
        "le tier petit dit « sortir » sans nommer la porte, et le moteur choisit "
        "parmi les sorties connues et non crues bloquées.\n"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nécrit : {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
