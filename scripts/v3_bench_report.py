#!/usr/bin/env python
"""Banc d'évaluation des politiques (S4) — compare rules / llm / hybrid.

Écrit le tableau comparatif dans ``docs/resultats/v3/``. Note : le fournisseur
LLM de ce rapport est un **stub** (déterminisme sans GPU) ; la colonne ``llm``
mesure donc le *mécanisme* (prompt → JSON → validation → repli), pas un
modèle réel. Le branchement d'un modèle natif suivra (voir docs/v3).
"""

from __future__ import annotations

from pathlib import Path

from maree.v3.verify.bench import (
    SITUATIONS,
    hybrid_decider,
    llm_decider,
    rules_decider,
    run_bench,
)

OUT = Path(__file__).resolve().parents[1] / "docs" / "resultats" / "v3"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    # recalcule pour un affichage déterministe (compare_policies fait pareil
    # mais en une passe) : on s'appuie sur le catalogue déjà câblé.
    from maree.v3.adapters.chat_stub import StubChat
    from maree.v3.agents.catalog import register_provider

    register_provider(
        "llamacpp",
        StubChat(lambda _r: '{"action": "evacuer", "cible": "A", "confiance": 0.8}'),
    )

    rows = "| situation | attente | rules | llm (stub) | hybrid |\n|---|---|---|---|---|\n"
    for s in SITUATIONS:
        rd = run_bench(rules_decider, (s,))["par_situation"][s.name]
        ld = run_bench(llm_decider, (s,))["par_situation"][s.name]
        hd = run_bench(hybrid_decider, (s,))["par_situation"][s.name]
        rows += (
            f"| {s.name} | {s.expected.value} | {rd['obtenu']}{'⚠' if not rd['correct'] else ''} "
            f"| {ld['obtenu']}{'⚠' if not ld['correct'] else ''} "
            f"| {hd['obtenu']}{'⚠' if not hd['correct'] else ''} |\n"
        )

    DECIDERS = {
        "rules": rules_decider,
        "llm": llm_decider,
        "hybrid": hybrid_decider,
    }
    agg = ""
    for policy, decider in DECIDERS.items():
        r = run_bench(decider)
        agg += (
            f"**{policy}** — justesse {r['taux_justesse']:.0%}, "
            f"résolution {r['taux_resolution']:.0%}\n"
        )

    OUT.joinpath("tableau-politiques-semaine4.md").write_text(
        "# Politiques — comparaison (semaine 4)\n\n"
        "*Banc local (stub LLM) : justesse et résolution par situation.*\n\n"
        + rows
        + "\n## Synthèse\n\n"
        + agg,
        encoding="utf-8",
    )
    print(rows)
    print(agg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())