"""P3.3 — parole ou rumeur ? Trois modes, même monde, même politique.

Le résultat de C7 (« la parole construit l'accord et dégrade la décision »)
mélange deux choses : le fait que des agents **s'informent**, et le fait que
**n'importe qui raconte n'importe quoi**. Ici on sépare les deux :

    none    : personne ne parle (null de B3)
    guards  : seuls les agents de sécurité parlent (4 présents dans la salle)
    all     : tout le monde parle, comme dans C7

Bras `règles` uniquement (la parole est le sujet, pas le modèle) ; scénario
`split` (moitié « A bloquée », moitié « B bloquée »), sans modèle, sans GPU.

Ce qu'on attend, et ce que l'on mesure même si c'est l'inverse :

- si `guards` remonte l'accord autant que `all`, c'est l'**autorité** qui
  construit le consensus ;
- si `guards` ne change presque rien et que `all` dégrade les décisions, c'est
  la **rumeur** — et il faut le dire ainsi.

Usage : uv run python scripts/v3_speech.py [graines...]
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.verify import scenario_crowd as sc

SEEDS = tuple(int(a) for a in sys.argv[1:]) or (1, 2, 3, 4, 5)
#: (nom, mode, nombre de gardes)
MODES = (
    ("none", "none", 0),
    ("guards", "guards", 4),
    ("all", "all", 4),
)


def one(mode: str, guards: int, seed: int) -> dict[str, object]:
    bus = MemoryBus()
    sim = sc.build_sim(
        PolicyName.RULES, seed=seed, bus=bus, guards=guards, speaking_mode=mode
    )
    sim.run(sc.split_timeline(seed))
    crowd = [dict(e.data) for e in bus.published("indicator.crowd")]
    summary = sc.summarise_series(crowd)
    rows = sim.log.rows
    decisions = [r for r in rows if r.action.startswith("évacuer")]
    believed_blocked = sum(1 for r in decisions if r.target_believed_blocked)
    return {
        "mode": mode,
        "guards": guards,
        "seed": seed,
        "I1": summary["I1_consensus"],
        "decisions": len(rows),
        "messages": len(bus.published("agent.message")),
        "part_crue_bloquee": (
            round(believed_blocked / len(decisions), 3) if decisions else 0.0
        ),
        "evacuated": len(sim._evacuated),
    }


def main() -> int:
    rows = [one(mode, guards, seed) for _name, mode, guards in MODES for seed in SEEDS]
    by_mode: dict[str, list[dict[str, object]]] = {}
    for r in rows:
        by_mode.setdefault(str(r["mode"]), []).append(r)

    print(f"{'mode':>7} {'I1':>5} {'décisions':>10} {'messages':>9} "
          f"{'crue bloquée':>13} {'sortis':>7}")
    for mode, _guards, _ in MODES:
        group = by_mode[mode]
        print(
            f"{mode:>7} "
            f"{statistics.median(float(r['I1']) for r in group):>5.2f} "  # type: ignore[arg-type]
            f"{statistics.median(float(r['decisions']) for r in group):>10.0f} "  # type: ignore[arg-type]
            f"{statistics.median(float(r['messages']) for r in group):>9.0f} "  # type: ignore[arg-type]
            f"{statistics.median(float(r['part_crue_bloquee']) for r in group):>13.2f} "  # type: ignore[arg-type]
            f"{min(int(r['evacuated']) for r in group):>7}"  # type: ignore[arg-type]
        )

    out = Path("runs/v3/speech_modes.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nJSON :", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
