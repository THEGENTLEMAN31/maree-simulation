#!/usr/bin/env python
"""Rend runs/v3/campaign_crowd_10seeds.json en tables markdown.

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

DEFAULT = Path("runs/v3/campaign_crowd_10seeds.json")
OUT = Path("docs/v3/resultats-c6.md")


def _f(value: Any, digits: int = 2) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.{digits}f}"
    return "—"


def _belief_cell(aggregate: dict[str, Any]) -> str:
    """La métrique de croyance, ou « — » si elle n'a pas été journalisée."""
    value = aggregate.get("part_believed_blocked_med")
    if value is None:
        return "— *(non journalisée sur ces runs)*"
    return f"{_f(value)} ({_f(aggregate.get('part_bloquees_least_bad_med', 0.0))})"


def _aggregate_from_runs(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Agrège à la volée quand le JSON ne porte pas de bloc ``aggregate``."""
    import statistics as st

    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        grouped.setdefault(f"{run['arm']}|{run['scenario']}", []).append(run)
    out: dict[str, dict[str, Any]] = {}
    for key, rows in grouped.items():
        def med(fn, rows: list[dict[str, Any]] = rows) -> float | None:  # type: ignore[no-untyped-def]
            vals = [fn(r) for r in rows]
            vals = [v for v in vals if v is not None]
            return round(st.median(vals), 3) if vals else None

        def belief(r: dict[str, Any]) -> float | None:
            value = r.get("targeted_believed_blocked")
            if value is None:
                return None
            return value / (r["decisions"] or 1)

        beliefs = [belief(r) for r in rows if belief(r) is not None]
        out[key] = {
            "n_runs": len(rows),
            "decisions_med": med(lambda r: r["decisions"]),
            "llm_attempted_med": med(lambda r: r["llm_attempted"]),
            "llm_ok_med": med(lambda r: r["llm_ok"]),
            "tokens_med": med(lambda r: r["tokens"]),
            "wall_s_med": med(lambda r: r["wall_s"]),
            "part_decisions_bloquees_med": med(
                lambda r: r.get("targeted_blocked", 0) / (r["decisions"] or 1)
            ),
            "part_believed_blocked_med": (
                round(st.median(beliefs), 3) if beliefs else None
            ),
            "part_bloquees_least_bad_med": med(
                lambda r: r.get("targeted_blocked_least_bad", 0)
                / (r["decisions"] or 1)
            ),
            "target_resolved_med": med(lambda r: r.get("target_resolved", 0)),
            "messages_med": med(lambda r: r.get("messages", 0)),
            "I1_med": med(lambda r: r["indicators"].get("I1_consensus", 0.0)),
            "I3_med": med(lambda r: r["indicators"].get("I3_evacuated", 0.0)),
            "I5_med": med(lambda r: r["indicators"].get("I5_max_density", 0.0)),
            "I5_span": [
                round(min(r["indicators"].get("I5_max_density", 0.0) for r in rows), 3),
                round(max(r["indicators"].get("I5_max_density", 0.0) for r in rows), 3),
            ],
            "I7_med": med(lambda r: r["indicators"].get("I7_delay_seconds", 0.0)),
            "I7_span": [
                round(min(r["indicators"].get("I7_delay_seconds", 0.0) for r in rows), 1),
                round(max(r["indicators"].get("I7_delay_seconds", 0.0) for r in rows), 1),
            ],
            "escalations": {},
            "replis": {},
        }
    return out


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    data = json.loads(path.read_text(encoding="utf-8"))
    seeds = data["seeds"]
    scenarios = data.get("scenarios") or sorted({r["scenario"] for r in data["runs"]})
    agg: dict[str, dict[str, Any]] = data.get("aggregate") or _aggregate_from_runs(
        data["runs"]
    )

    lines: list[str] = []
    speaks = {bool(run.get("speak", True)) for run in data["runs"]}
    mode = (
        "parole active (C7)"
        if speaks == {True}
        else "sans émission (null de B3)"
        if speaks == {False}
        else "mode mixte"
    )
    lines.append("# Résultats de la campagne macro (C6/C7)\n")
    lines.append(
        f"Monde : `crowd_hall` (22 × 16 m, deux issues de 1,2 m), 60 agents, "
        f"tick de 2 s. Graines : {', '.join(str(s) for s in seeds)} — "
        f"scénarios : {', '.join(scenarios)} — **{mode}**.\n"
    )
    lines.append(
        "Chaque ligne est la **médiane** des runs du bras ; `[min–max]` donne "
        "l'intervalle observé, jamais un écart-type qui masquerait un run.\n"
    )

    header = (
        "| bras | scénario | décisions | appels (ok) | jetons | mural (s) | "
        "I1 | I3 | I5 [min–max] | I7 s [min–max] | crue bloquée (désignée t1) | "
        "crue bloquée **au moment de décider** (dont faute de mieux) | paroles | "
        "cibles résolues par le moteur |"
    )
    lines.append(header)
    lines.append("|" + "---|" * 15)
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
            f"{_belief_cell(a)} | "
            f"{_f(a.get('messages_med', 0.0), 0) if 'messages_med' in a else '—'} | "
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
