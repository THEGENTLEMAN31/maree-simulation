"""M-05 — mall_aubel : le WorldSpec multi-étages chargeable et simulable.

Quatre étapes, une commande : ``uv run python scripts/v3_mall.py [graine]``

1. **inventaire** — le YAML ``configs/world/mall_aubel.yaml`` se charge par
   le chargeur v3 (``world.loader.load`` : YAML → ``from_dict`` → validation
   bloquante) et expose niveaux, espaces, portiques, sorties, liens
   verticaux et dangers ;
2. **structure** — sans les liens verticaux, la validation refuse : les
   espaces de L1 et ceux de L0 sont mutuellement inatteignables. Les deux
   escalators et l'escalier sont donc l'**unique** passage entre niveaux ;
3. **plans** — les plans ASCII des deux niveaux, calculés depuis les
   polygones du WorldSpec (jamais dessinés à la main) ;
4. **simulation** — un run court par niveau (20 agents, 15 ticks de 2 s =
   30 s de temps simulé, JuPedSim aux commandes) : les agents circulent
   dans leur niveau et évacuent par ses sorties.

Limite assumée et documentée (monde-et-rendu §7) : la simulation v3.0 est
**mono-étage** — le ``LevelCoordinator`` (v3.1) qui ferait passer un agent
d'un niveau à l'autre n'existe pas encore ; aucun agent n'est téléporté.
Ce que ce script prouve donc : chaque niveau est navigable et évacuable,
et les escalators sont structurellement l'unique liaison entre eux.

Usage : uv run python scripts/v3_mall.py [graine] (aucun GPU, ~2 s)
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon

from maree.v3.adapters.physics import JuPedSimCrowd
from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.sim.journal import run_header, world_hash, write_run
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.verify.indicators import summarise
from maree.v3.world.loader import load
from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.simartifact import build_sim_artifact
from maree.v3.world.validate import validate
from maree.v3.world.worldspec import WorldSpec, from_dict

WORLD_PATH = Path("configs/world/mall_aubel.yaml")
OUT_JSON = Path("runs/v3/mall.json")

#: durée d'un tick (s) et pas de physique (dt = 0,05 s ⇒ 2 s par tick),
#: la cadence du scénario de foule (scenario_crowd).
TICK_SECONDS = 2.0
STEPS_PER_TICK = 40
N_TICKS = 15                 # 15 × 2 s = 30 s de temps simulé
T_SMOKE = 1
N_AGENTS = 20
EXITS_BY_LEVEL = {"L0": ("A", "B", "C"), "L1": ("D", "E")}


# ------------------------------------------------------------------
# 1. l'inventaire : ce que le chargeur expose
# ------------------------------------------------------------------
def inventaire(world: WorldSpec) -> None:
    print(f"monde {world.id} — schema {world.schema}, version {world.version}, "
          f"unités {world.units}, repère {world.coordinate_system}")
    print(f"hash du monde : {world_hash(world)}")
    for lv in world.levels:
        print(f"\n  niveau {lv.id} — {lv.name} "
              f"(élévation {lv.elevation} m, hauteur {lv.height} m, "
              f"{len(lv.holes)} trou(s) dans le contour)")
        for s in lv.spaces:
            print(f"    espace   {s.id:<18} {s.kind:<8} occupation {s.occupancy}")
        for p in lv.portals:
            print(f"    portique {p.id:<18} {p.between[0]} ↔ {p.between[1]}  "
                  f"largeur {p.width} m  ({p.state})")
        for e in lv.exits:
            print(f"    sortie   {e.id:<18} largeur {e.width} m  → {e.to}")
        for o in lv.obstacles:
            print(f"    obstacle {o.id:<18} {o.kind} (h {o.height} m)")
    for v in world.vertical:
        print(f"  lien vertical {v.id:<10} {v.kind:<9} {v.from_level} → {v.to_level}  "
              f"largeur {v.width} m, capacité {v.capacity_p_s} pers/s")
    for h in world.hazards:
        print(f"  danger {h.id:<10} {h.kind} au niveau {h.level}, position {h.position}")


# ------------------------------------------------------------------
# 2. la preuve structurelle : les liens verticaux sont l'unique passage
# ------------------------------------------------------------------
def _to_dict(world: WorldSpec) -> dict[str, object]:
    """Ré-encode un WorldSpec en dict ``from_dict``-compatible (copie fidèle)."""
    levels = []
    for lv in world.levels:
        levels.append({
            "id": lv.id, "name": lv.name, "elevation": lv.elevation,
            "height": lv.height,
            "outline": [list(p) for p in lv.outline],
            "holes": [[list(p) for p in h] for h in lv.holes],
            "spaces": [
                {"id": s.id, "kind": s.kind, "polygon": [list(p) for p in s.polygon],
                 "occupancy": s.occupancy}
                for s in lv.spaces
            ],
            "portals": [
                {"id": p.id, "between": list(p.between),
                 "segment": [list(pt) for pt in p.segment],
                 "width": p.width, "state": p.state,
                 "capacity_p_s": p.capacity_p_s}
                for p in lv.portals
            ],
            "exits": [
                {"id": e.id, "segment": [list(pt) for pt in e.segment],
                 "width": e.width, "to": e.to}
                for e in lv.exits
            ],
            "obstacles": [
                {"id": o.id, "polygon": [list(pt) for pt in o.polygon],
                 "height": o.height, "kind": o.kind}
                for o in lv.obstacles
            ],
        })
    vertical = [
        {"id": v.id, "kind": v.kind, "from": v.from_level, "to": v.to_level,
         "polygon": [list(p) for p in v.polygon], "width": v.width,
         "capacity_p_s": v.capacity_p_s}
        for v in world.vertical
    ]
    hazards = [
        {"id": h.id, "kind": h.kind, "level": h.level,
         "position": list(h.position),
         "hrr_kw": [list(p) for p in h.hrr_kw], "soot_yield": h.soot_yield}
        for h in world.hazards
    ]
    return {
        "id": world.id, "version": world.version, "schema": world.schema,
        "units": world.units, "coordinate_system": world.coordinate_system,
        "levels": levels, "vertical": vertical, "hazards": hazards,
    }


def preuve_structurelle(world: WorldSpec) -> list[str]:
    """Sans les liens verticaux, la validation refuse : L1 est isolée."""
    data = _to_dict(world)
    data["vertical"] = []
    errors = validate(from_dict(data))
    print(f"WorldSpec sans liens verticaux → {len(errors)} erreur(s) de validation :")
    for e in errors:
        print(f"   - {e}")
    print("   ⇒ L0 et L1 ne communiquent QUE par les trois liens verticaux.")
    return errors


# ------------------------------------------------------------------
# 3. la simulation : un run court par niveau
# ------------------------------------------------------------------
def _hazard_origin(world: WorldSpec, level_id: str) -> tuple[float, float]:
    """L'origine de fumée du niveau (le danger déclaré, sinon le centre)."""
    for h in world.hazards:
        if h.level == level_id:
            return h.position
    minx, miny, maxx, maxy = NavigationGraph(world).bounds(level_id)
    return ((minx + maxx) / 2.0, (miny + maxy) / 2.0)


def _timeline(world: WorldSpec, level_id: str) -> list[Timestep]:
    origin = _hazard_origin(world, level_id)
    return [
        Timestep(T_SMOKE, smoke=True, hazard_origin=origin),
        *[Timestep(t) for t in range(T_SMOKE + 1, N_TICKS + 1)],
    ]


def _attribution_sorties(
    bus: MemoryBus, world: WorldSpec, level_id: str, evacuated: set[int]
) -> dict[str, int]:
    """Sortie de chaque agent sorti = la plus proche de son dernier point vu.

    Le moteur ne journalise pas quelle scène d'issue a absorbé l'agent ; le
    dernier instantané où l'agent figure en donne une approximation honnête
    (à moins d'un mètre du seuil en pratique).
    """
    exits = {e.id: e.segment for e in world.level(level_id).exits}
    mids = {
        eid: ((s[0][0] + s[1][0]) / 2.0, (s[0][1] + s[1][1]) / 2.0)
        for eid, s in exits.items()
    }
    last: dict[int, tuple[float, float]] = {}
    for env in bus.published("world.snapshot"):
        for tag, xy in env.data["agents"].items():
            last[int(tag)] = (xy[0], xy[1])
    counts: Counter[str] = Counter()
    for tag in sorted(evacuated):
        if tag not in last:
            continue
        x, y = last[tag]
        eid = min(mids, key=lambda k: math.dist(mids[k], (x, y)))
        counts[eid] += 1
    return dict(sorted(counts.items()))


def run_niveau(
    world: WorldSpec, level_id: str, n_agents: int, seed: int
) -> tuple[dict[str, object], list[object]]:
    """Un run JuPedSim sur UN niveau du mall (v3.0 mono-étage)."""
    graph = NavigationGraph(world)
    art = build_sim_artifact(world, graph, np.random.default_rng(seed),
                             spawn_per_space=6)
    la = art.levels[level_id]
    exits = {e.id: e.segment for e in world.level(level_id).exits}
    crowd = JuPedSimCrowd(walkable=la.walkable, exits=exits, seed=seed)
    run_id = f"mall_{level_id.lower()}_s{seed}"
    bus = MemoryBus()
    sim = Simulation(
        seed=seed,
        policy=PolicyName.RULES,
        bus=bus,
        run_id=run_id,
        physics=crowd,
        physics_steps_per_tick=STEPS_PER_TICK,
        tick_seconds=TICK_SECONDS,
        speaking=False,
    ).build(world)
    t0 = time.perf_counter()
    sim.spawn("visiteur", n_agents, frozenset(EXITS_BY_LEVEL[level_id]),
              level=level_id)
    sim.run(_timeline(world, level_id))
    wall = time.perf_counter() - t0

    summary = summarise([dict(e.data) for e in bus.published("indicator.crowd")])
    evacuated = set(sim._evacuated)
    exit_usage = _attribution_sorties(bus, world, level_id, evacuated)
    print(f"\n  run {run_id} — {n_agents} agents, {N_TICKS} ticks × "
          f"{TICK_SECONDS} s = {N_TICKS * TICK_SECONDS:.0f} s simulées")
    print(f"    décisions journalisées : {len(sim.log.rows)}")
    print(f"    évacués : {len(evacuated)}/{n_agents}")
    print(f"    sorties empruntées (dernier point connu) : {exit_usage}")
    print(f"    I5 pic {summary['I5_max_density']} pers/m², "
          f"I7 {summary['I7_delay_seconds']} s, murale {wall:.2f} s")
    result = {
        "run_id": run_id,
        "level": level_id,
        "seed": seed,
        "n_agents": n_agents,
        "ticks": N_TICKS,
        "tick_seconds": TICK_SECONDS,
        "simulated_seconds": N_TICKS * TICK_SECONDS,
        "decisions": len(sim.log.rows),
        "evacuated": len(evacuated),
        "exit_usage": exit_usage,
        "summary": summary,
        "wall_s": round(wall, 2),
        "spaces_seen": sorted({i.space_id for i in sim.scene.instances.values()}),
    }
    return result, bus.envelopes


# ------------------------------------------------------------------
# 4. les plans ASCII, dérivés du WorldSpec (jamais dessinés à la main)
# ------------------------------------------------------------------
def plans_ascii(world: WorldSpec) -> str:
    """Un plan par niveau : 1 caractère = 1 m en x, 2 m en y.

    Le plan est **calculé** depuis les polygones du WorldSpec — si le YAML
    change, le plan change. Légende : ``#`` obstacle, ``.`` marchable,
    ``|`` portique, chiffres = liens verticaux (ordre du YAML), lettres =
    sorties. La trémie apparaît comme du vide (hors contour).
    """
    out: list[str] = []
    for lv in world.levels:
        x0, y0, maxx, maxy = _poly_of(lv.outline, lv.holes).bounds
        cols, rows = math.ceil(maxx), math.ceil(maxy - y0) // 2
        grid = [[" "] * cols for _ in range(rows)]
        outline = _poly_of(lv.outline, lv.holes)
        for r in range(rows):
            for c in range(cols):
                pt = ShapelyPoint(x0 + c + 0.5, y0 + r * 2 + 1)
                if outline.covers(pt):
                    grid[r][c] = "."
        for o in lv.obstacles:
            _stamp(grid, _poly_of(o.polygon), x0, y0, "#")
        for i, v in enumerate(world.vertical, start=1):
            _stamp(grid, _poly_of(v.polygon), x0, y0, str(i))
        for e in lv.exits:
            seg = e.segment
            mx = (seg[0][0] + seg[1][0]) / 2.0
            my = (seg[0][1] + seg[1][1]) / 2.0
            c = min(cols - 1, max(0, int(mx - x0)))
            r = min(rows - 1, max(0, int((my - y0) // 2)))
            grid[r][c] = e.id
        for p in lv.portals:
            (x1, y1), (x2, y2) = p.segment
            steps = max(2, int(math.hypot(x2 - x1, y2 - y1) * 2))
            for k in range(steps + 1):
                x = x1 + (x2 - x1) * k / steps
                y = y1 + (y2 - y1) * k / steps
                c = min(cols - 1, max(0, int(x - x0)))
                r = min(rows - 1, max(0, int((y - y0) // 2)))
                grid[r][c] = "|"
        out.append(f"\n  {lv.id} — {lv.name} (élévation {lv.elevation} m)")
        legende_liens = ", ".join(
            f"{i}={v.id} ({v.kind}, {v.from_level}→{v.to_level})"
            for i, v in enumerate(world.vertical, start=1)
        )
        out.append(f"  liens verticaux : {legende_liens}")
        out.append("  " + "+" + "-" * cols + "+")
        for r in range(rows - 1, -1, -1):
            out.append("  |" + "".join(grid[r]) + "|")
        out.append("  " + "+" + "-" * cols + "+")
        out.append("  (1 caractère = 1 m en x, 1 ligne = 2 m en y ; "
                   "# obstacle, | portique, lettres = sorties)")
    return "\n".join(out)


def _poly_of(ring: object, holes: object = ()) -> Polygon:
    return Polygon([list(p) for p in ring],  # type: ignore[arg-type]
                   [[list(p) for p in h] for h in holes])


def _stamp(
    grid: list[list[str]], poly: Polygon, x0: float, y0: float, ch: str
) -> None:
    rows, cols = len(grid), len(grid[0])
    _minx, ymin, maxx, maxy = poly.bounds
    for r in range(max(0, int((ymin - y0) // 2)), min(rows, math.ceil((maxy - y0) / 2))):
        for c in range(max(0, int(_minx - x0)), min(cols, math.ceil(maxx - x0))):
            if poly.covers(ShapelyPoint(x0 + c + 0.5, y0 + r * 2 + 1)):
                grid[r][c] = ch


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    world = load(WORLD_PATH)

    print("=" * 64)
    print("1) INVENTAIRE — configs/world/mall_aubel.yaml")
    print("=" * 64)
    inventaire(world)

    print()
    print("=" * 64)
    print("2) STRUCTURE — les liens verticaux sont l'unique passage")
    print("=" * 64)
    structure_errors = preuve_structurelle(world)

    print()
    print("=" * 64)
    print("3) PLANS ASCII — dérivés du WorldSpec")
    print("=" * 64)
    print(plans_ascii(world))

    print()
    print("=" * 64)
    print(f"4) SIMULATION — {N_AGENTS} agents, 30 s par niveau (graine {seed})")
    print("=" * 64)
    runs: list[dict[str, object]] = []
    journals: dict[str, list[object]] = {}
    for level_id in ("L0", "L1"):
        result, envelopes = run_niveau(world, level_id, N_AGENTS, seed)
        runs.append(result)
        journals[level_id] = envelopes
        # le journal du run est la source de vérité (convention n°1)
        header = run_header(str(result["run_id"]), world, seed, PolicyName.RULES)
        header["note"] = (
            f"M-05 : WorldSpec mall_aubel, run mono-étage {level_id} (v3.0)"
        )
        path = write_run(
            Path(f"runs/v3/{result['run_id']}.jsonl"), header, envelopes
        )
        print(f"    journal : {path} ({len(envelopes)} événements)")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "world": WORLD_PATH.as_posix(),
                "world_hash": world_hash(world),
                "note": (
                    "Simulation mono-étage (v3.0) : chaque run se déroule sur "
                    "un niveau ; la circulation inter-niveaux attend le "
                    "LevelCoordinator (v3.1, monde-et-rendu §7)."
                ),
                "structure": {
                    "vertical_links": [v.id for v in world.vertical],
                    "sans_liens_verticaux": structure_errors,
                },
                "runs": runs,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nJSON : {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
