#!/usr/bin/env python
"""Campagne « sortie bloquée » (A5/H2) — le scénario où le petit peut échouer.

Le banc est ``maree.v3.verify.scenario_blocked`` (monde fixe, quatre
visiteurs, message « la sortie X est bloquée » à t2, fumée seule à t10).
La bonne réponse est de **contourner** la sortie crue bloquée :
A01/A02 → B, A03/A04 → A. Le défaut (A, la sortie la plus confiante) est
faux pour la moitié des agents, donc une politique de position plafonne à
0,50 **par construction** (vérifié sans GPU par
``tests/v3/test_scenario_blocked.py``).

Hypothèses écrites avant mesure :
  - règles               : 1,00 (elles ignorent toute sortie crue bloquée) ;
  - grand (e2b)          : > 0,50 attendu, non garanti — c'est ce qu'on mesure ;
  - petit (qwen)         : 0,50 attendu (politique de position, pas de lecture) ;
  - grand **sans** dangers : ablation, pas un concurrent. Si le grand reste à
                           1,00, il lit ``messages_recus``/``memoire`` et pas
                           ``dangers`` ; s'il tombe à 0,50, c'est le champ
                           ``dangers`` qui porte la décision.

Note de méthode : le monde est fixe, la température vaut 0 et le prompt ne
dépend pas de la position. Les graines vérifient donc la **stabilité**, pas
la variance — c'est dit, pas caché.

Usage : uv run python scripts/v3_campaign_blocked.py [seeds]
Prérequis : serveurs 8081 (grand) et 8082 (petit).
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

os.environ.setdefault("MAREE_LLM_URL", "http://127.0.0.1:8081/v1")
os.environ.setdefault("MAREE_LLM_SMALL_URL", "http://127.0.0.1:8082/v1")

from maree.v3 import bootstrap

bootstrap.assemble()

from maree.v3.agents import policy_llm  # noqa: E402
from maree.v3.core.ports import PolicyName  # noqa: E402
from maree.v3.sim.bus import MemoryBus  # noqa: E402
from maree.v3.verify import scenario_blocked as sb  # noqa: E402
from maree.v3.verify.emergence import emergence_report  # noqa: E402

SEEDS = [int(a) for a in sys.argv[1:]] or [1, 2, 3, 4, 5]
#: (nom, politique, alias, ablation du champ ``dangers``)
CONFIGS = [
    ("regles", PolicyName.RULES, None, False),
    ("grand", PolicyName.LLM, "decision", False),
    ("petit", PolicyName.LLM, "petit", False),
    ("grand_sans_dangers", PolicyName.LLM, "decision", True),
]

_ORIGINAL_INPUTS = policy_llm.build_inputs


def _inputs_without_dangers(**kwargs: Any) -> dict[str, object]:
    """Ablation : le même prompt, amputé du champ ``dangers``."""
    payload = _ORIGINAL_INPUTS(**kwargs)
    payload["dangers"] = []
    return payload


def run(
    config: str, policy: PolicyName, alias: str | None, ablate: bool, seed: int
) -> dict[str, object]:
    policy_llm.build_inputs = _inputs_without_dangers if ablate else _ORIGINAL_INPUTS
    try:
        sim = sb.build(seed=seed, policy=policy, alias=alias, bus=MemoryBus())
        sim.run(sb.timeline())
    finally:
        policy_llm.build_inputs = _ORIGINAL_INPUTS

    result = sb.score(sim)
    # le contexte réellement envoyé au modèle (audit : dangers y figure-t-il ?)
    danger_in_prompt: dict[str, bool] = {}
    tokens = 0
    for agent_name in sorted(sb.BLOCKED):
        agent = next(
            i.agent for i in sim.scene.instances.values() if i.agent.name == agent_name
        )
        decision = agent._last_decision
        trace = decision.llm_trace if decision else None
        if trace is None:
            continue
        tokens += trace.response.prompt_tokens + trace.response.completion_tokens
        try:
            payload = json.loads(trace.request.messages[-1].content)
        except ValueError:
            continue
        danger_in_prompt[agent_name] = bool(payload.get("dangers"))

    report = emergence_report([i.agent for i in sim.scene.instances.values()])
    return {
        "config": config,
        "seed": seed,
        "evite_bloquee": result.accuracy,
        "choix": result.choices,
        "bloquees": dict(sb.BLOCKED),
        "danger_dans_prompt": danger_in_prompt,
        "consensus": report["consensus"],
        "couplage": report["couplage"],
        "llm_calls": sum(1 for r in sim.log.rows if r.llm_model),
        "replis": sum(1 for r in sim.log.rows if r.fallback),
        "incidents": dict(sorted(sim.incidents.items())),
        "tokens": tokens,
    }


def main() -> int:
    print(f"graines {SEEDS} — la bonne réponse est d'éviter la sortie crue bloquée")
    rows: list[dict[str, object]] = []
    t0 = time.time()
    for config, policy, alias, ablate in CONFIGS:
        for seed in SEEDS:
            r = run(config, policy, alias, ablate, seed)
            rows.append(r)
            print(
                f"  {config:<18} s{seed}  evite={r['evite_bloquee']:.2f} "
                f"calls={r['llm_calls']:>2} repli={r['replis']} "
                f"tokens={r['tokens']:>4} danger_prompt={r['danger_dans_prompt']} "
                f"choix={r['choix']}"
            )
    print(f"durée murale : {time.time() - t0:.0f}s")

    by: dict[str, list[dict[str, object]]] = defaultdict(list)
    for r in rows:
        by[str(r["config"])].append(r)
    print("\n=== AGRÉGAT (médiane) ===")
    for config, rs in by.items():
        evite = statistics.median(float(r["evite_bloquee"]) for r in rs)  # type: ignore[arg-type]
        dangers = sum(
            sum(1 for v in r["danger_dans_prompt"].values() if v)  # type: ignore[union-attr]
            for r in rs
        )
        print(
            f"  {config:<18} evite={evite:.2f} "
            f"[{min(float(r['evite_bloquee']) for r in rs):.2f}–"  # type: ignore[arg-type]
            f"{max(float(r['evite_bloquee']) for r in rs):.2f}] "  # type: ignore[arg-type]
            f"appels={statistics.median(int(r['llm_calls']) for r in rs):.0f} "  # type: ignore[arg-type]
            f"tokens={statistics.median(int(r['tokens']) for r in rs):.0f} "  # type: ignore[arg-type]
            f"replis_tot={sum(int(r['replis']) for r in rs)} "  # type: ignore[arg-type]
            f"prompts_avec_danger={dangers}"
        )

    out = Path("runs/v3")
    out.mkdir(parents=True, exist_ok=True)
    (out / "campaign_blocked.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("\nJSON : runs/v3/campaign_blocked.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
