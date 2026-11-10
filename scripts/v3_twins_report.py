#!/usr/bin/env python
"""Expérience des jumeaux — génère le premier rapport de divergence (S3).

Déroule l'expérience pour plusieurs archétypes et configurations
(avec / sans mémoire) et écrit un rapport Markdown reproductible dans
``docs/resultats/v3/``. Chiffres déterministes : le CSV/tableau se compare
d'un run à l'autre.
"""

from __future__ import annotations

import json
from pathlib import Path

from maree.v3.agents.perception import Message
from maree.v3.core.ids import AgentId
from maree.v3.verify.twins import (
    PublicEvent,
    TwinHistory,
    run_twins_experiment,
)

OUT = Path(__file__).resolve().parents[1] / "docs" / "resultats" / "v3"


def time_ligne(*events: PublicEvent) -> tuple[PublicEvent, ...]:
    return events


def _histoire_neg(bloque: str) -> TwinHistory:
    return TwinHistory(
        name=f"« {bloque} bloquée »",
        messages=[(2, Message(f"{bloque} est bloquée", AgentId(3), 2))],
    )


def _histoire_pos(ouverte: str) -> TwinHistory:
    return TwinHistory(
        name=f"« {ouverte} libre »",
        messages=[(2, Message(f"{ouverte} est libre", AgentId(3), 2))],
    )


SCENARIOS = {
    "fumee_seule": time_ligne(
        PublicEvent(1, announcement="Veuillez rester calmes"),
        PublicEvent(10, smoke=True),
        PublicEvent(20, smoke=True),
    ),
    "annonce_puis_fumee": time_ligne(
        PublicEvent(1),
        PublicEvent(5, announcement="Veuillez évacuer par la sortie A"),
        PublicEvent(10, smoke=True),
        PublicEvent(20, smoke=True),
    ),
}

CONFIGS = [
    ("blocages_croises", _histoire_neg("A"), _histoire_neg("B")),
    ("inertie_et_reassurance", TwinHistory("aucune"), _histoire_pos("A")),
    ("deux_herings", _histoire_pos("A"), _histoire_pos("B")),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    for archetype in ("visiteur", "habitue"):
        for scen_name, timeline in SCENARIOS.items():
            for cfg, left_h, right_h in CONFIGS:
                for memory_on in (True, False):
                    rep = run_twins_experiment(
                        timeline=timeline,
                        left_history=left_h,
                        right_history=right_h,
                        archetype=archetype,
                        known_exits=frozenset({"A", "B", "C"}),
                        n_pairs=8,
                        memory_on=memory_on,
                    )
                    rows.append(
                        {
                            "archetype": archetype,
                            "scenario": scen_name,
                            "config": cfg,
                            "memoire": "on" if memory_on else "off",
                            "KL": round(float(rep["kl_divergence"]), 4),
                            "accord": round(float(rep["agreement_ratio"]), 3),
                            "gauche_A": round(float(rep["left_distribution"].get("A", 0)), 3),
                            "droite_B": round(float(rep["right_distribution"].get("B", 0)), 3),
                        }
                    )

    report = _render(rows)
    OUT.joinpath("rapport-divergence-semaine3.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


def _render(rows: list[dict[str, object]]) -> str:
    header = (
        "| archétype | scénario | config | mémoire | KL | accord | gauche→A | droite→B |\n"
        "|---|---|---|---|---:|---:|---:|---:|\n"
    )
    lines = [header]
    for r in rows:
        lines.append(
            "| {archetype} | {scenario} | {config} | {memoire} | {KL} | {accord} | "
            "{gauche_A} | {droite_B} |".format(**r)
        )
    body = "\n".join(lines)
    return (
        "# Rapport — expérience des jumeaux (semaine 3)\n\n"
        "*Généré de façon déterministe. La KL mesure la divergence des "
        "distributions de sortie ; l'accord, la part de paires qui prennent "
        "la même sortie. Mémoire `off` = ablation.*\n\n"
        + body
        + "\n\n```json\n"
        + json.dumps(rows, ensure_ascii=False, indent=1)
        + "\n```\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())