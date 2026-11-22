"""P2.3 / P2.4 — deux tiers en foule, et la courbe du quota ε.

Deux expériences, un seul script parce qu'elles partagent la même question :
**que paie-t-on pour quoi ?**

**Deux tiers** (`scenario_crowd.build_two_tier`) : 40 visiteurs sur le petit
modèle, 20 habitués sur le grand — exactement la configuration revendiquée
pour la sobriété. Mesures : I1–I7, décisions, appels par taille, jetons,
temps mural. On la compare au grand seul et au petit seul (mêmes graines,
même monde).

**Courbe ε** : le bras hybride escalade déjà sur des faits du monde. Le quota
ε ajoute une escalade **aléatoire** (tirage SHA-256) sur la routine. Si la
qualité ne bouge pas quand ε monte, l'escalade ciblée suffit — et ε n'a pas
de raison d'exister. S'il faut ε pour retrouver la qualité du modèle seul,
c'est l'inverse : le ciblage ne suffit pas.

Usage : uv run python scripts/v3_bands.py [graines...]
Prérequis : serveurs 8081 (grand) + 8082 (petit).
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from maree.v3 import bootstrap

bootstrap.assemble()

from maree.v3.core.ports import PolicyName  # noqa: E402
from maree.v3.sim.bus import MemoryBus  # noqa: E402
from maree.v3.verify import scenario_crowd as sc  # noqa: E402

SEEDS = tuple(int(a) for a in sys.argv[1:]) or (1, 2, 3)


def _stats(sim, bus, label: str, extra: dict[str, object] | None = None) -> dict[str, object]:
    crowd = [dict(e.data) for e in bus.published("indicator.crowd")]
    summary = sc.summarise_series(crowd)
    rows = sim.log.rows
    evac = [r for r in rows if r.action.startswith("évacuer")]
    per_model = Counter(r.llm_model or "aucun" for r in rows if r.llm_attempted)
    return {
        "bras": label,
        "decisions": len(rows),
        "appels": sum(1 for r in rows if r.llm_attempted),
        "jetons": sum(r.prompt_tokens + r.completion_tokens for r in rows),
        "par_modele": dict(per_model),
        "I1": round(float(summary["I1_consensus"]), 3),
        "I3": round(float(summary["I3_evacuated"]), 3),
        "I5": round(float(summary["I5_max_density"]), 3),
        "I7": round(float(summary["I7_delay_seconds"]), 1),
        "crue_bloquee": round(
            sum(1 for r in evac if r.target_believed_blocked) / len(evac), 3
        ) if evac else 0.0,
        "sortis": len(sim._evacuated),
        **(extra or {}),
    }


def _run(policy: PolicyName, seed: int, label: str, *, alias: str | None = None,
         epsilon: float | None = None) -> dict[str, object]:
    bus = MemoryBus()
    if label.startswith("deux_tiers"):
        sim = sc.build_two_tier(seed=seed, bus=bus)
        if epsilon is not None:
            sim.epsilon = epsilon
    else:
        sim = sc.build_sim(policy, seed=seed, bus=bus, alias=alias)
    sim.run(sc.split_timeline(seed))
    return _stats(sim, bus, label, {"seed": seed, "epsilon": epsilon})


def main() -> int:
    rows: list[dict[str, object]] = []
    print("=== deux tiers vs monolithic ===")
    for seed in SEEDS:
        for policy, alias, label in (
            (PolicyName.RULES, None, "regles"),
            (PolicyName.LLM, "decision", "grand_seul"),
            (PolicyName.LLM, "petit", "petit_seul"),
        ):
            rows.append(_run(policy, seed, label, alias=alias))
        rows.append(_run(PolicyName.LLM, seed, "deux_tiers"))
    for r in rows:
        print(f"  {r['bras']:<12} s{r['seed']} déc={r['decisions']:>3} "
              f"appels={r['appels']:>3} jetons={r['jetons']:>7} "
              f"I7={r['I7']:>4} crue_bloq={r['crue_bloquee']:.2f} "
              f"{r['par_modele']}")

    print("\n=== courbe epsilon (hybride, même monde) ===")
    eps_rows: list[dict[str, object]] = []
    for epsilon in (0.0, 0.25, 0.5):
        for seed in SEEDS:
            bus = MemoryBus()
            sim = sc.build_sim(PolicyName.HYBRID, seed=seed, bus=bus, alias="decision")
            sim.epsilon = epsilon
            sim.run(sc.split_timeline(seed))
            r = _stats(sim, bus, f"eps={epsilon}", {"seed": seed, "epsilon": epsilon})
            eps_rows.append(r)
            print(f"  eps={epsilon:<5} s{seed} appels={r['appels']:>3} "
                  f"jetons={r['jetons']:>7} I1={r['I1']:.2f} "
                  f"crue_bloq={r['crue_bloquee']:.2f}")

    out = Path("runs/v3/bands.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"deux_tiers": rows, "epsilon": eps_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("\nJSON :", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
