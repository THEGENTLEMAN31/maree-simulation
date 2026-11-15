#!/usr/bin/env python
"""La mission au vrai LLM : deux groupes reçoivent des messages opposés, ils divergent.

Un hall généré, 4 visiteurs + 2 habitués. À t=2, la moitié entend « B est
bloquée », l'autre « B est libre ». Puis fumée (t10) : chacun choisit et
**se déplace** (JuPedSim) vers la sortie qu'il juge sûre. On mesure :
décisions, sortie choisie par groupe, évacuation, consensus/couplage.

Usage : uv run python scripts/v3_divergence.py   (après make v3-llm-up)
"""

from __future__ import annotations

import os

os.environ.setdefault("MAREE_LLM_URL", "http://127.0.0.1:8081/v1")

import numpy as np

from maree.v3 import bootstrap

bootstrap.assemble()

from maree.v3.adapters.physics import JuPedSimCrowd  # noqa: E402
from maree.v3.agents.perception import Message  # noqa: E402
from maree.v3.core.ids import AgentId  # noqa: E402
from maree.v3.core.ports import PolicyName  # noqa: E402
from maree.v3.sim.orchestrator import Simulation, Timestep  # noqa: E402
from maree.v3.verify.emergence import emergence_report  # noqa: E402
from maree.v3.world.generate import build  # noqa: E402
from maree.v3.world.navgraph import NavigationGraph  # noqa: E402
from maree.v3.world.simartifact import build_sim_artifact  # noqa: E402


def main() -> int:
    world = build("hall_3")
    graph = NavigationGraph(world)
    art = build_sim_artifact(world, graph, np.random.default_rng(0), spawn_per_space=8)
    lv0 = art.levels["L0"]
    phys = JuPedSimCrowd(walkable=lv0.walkable,
                         exits={e.id: e.segment for e in world.level("L0").exits}, seed=1)

    sim = Simulation(seed=7, policy=PolicyName.LLM, physics=phys,
                     physics_steps_per_tick=20, run_id="divergence_real").build(world)
    sim.spawn("visiteur", 4, frozenset({"A", "B"}))      # uids 1..4
    sim.spawn("habitue", 2, frozenset({"A", "B", "C"}))  # uids 5..6
    # messages personnels opposés (la moitié de B bloquée/libre)
    msgs = (
        (1, Message("B est bloquée", AgentId(99), 3)),
        (2, Message("B est bloquée", AgentId(99), 3)),
        (3, Message("B est libre", AgentId(99), 3)),
        (4, Message("B est libre", AgentId(99), 3)),
    )
    sim.run([
        Timestep(2, messages=msgs),
        Timestep(10, smoke=True),
        Timestep(20), Timestep(30), Timestep(40),
    ])
    rows = sim.log.rows
    for r in rows:
        g = ("B bloquée" if r.agent in ("A01", "A02")
             else "B libre" if r.agent in ("A03", "A04") else "habitué")
        print(f"  t{r.tick:>3} {r.agent:<6} [{g:<9}] {r.action:<22} -> {r.target}{'  ✔ évac' if r.agent in {f'A{t:02d}' for t in sim._evacuated} else ''}")
    report = emergence_report([inst.agent for inst in sim.scene.instances.values()])
    print(f"\nÉVACUÉS : {sorted(sim._evacuated)} | consensus={report['consensus']} "
          f"couplage={report['couplage']} émergence={report['emergence']}")
    print("Message: groupes 'B bloquée' vs 'B libre' → choix de sortie différents au REAL modèle ?")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())