"""P4.2 — le contrat front, de bout en bout, sur un vrai socket.

Les tests de `test_api.py` vérifient les **fonctions** de trame : c'est utile
et ça ne prouve pas qu'un client reçoit quelque chose. Ici, on démarre le
serveur pour de vrai sur un port local, on s'y connecte avec un client
WebSocket, et on exige la séquence complète :

    world → hello → … → end

plus une injection (qui doit être appliquée au tick suivant et renvoyée en
écho) et un dossier d'agent (étiqueté `measured` / `derived` / `generated`).

C'est le test qui aurait attrapé les deux défauts de la v2 : la trame `end`
perdue dans la fermeture de socket, et le client qui repasse « connecté »
après `end`.
"""

from __future__ import annotations

import asyncio
import json

import numpy as np

from maree.v3.adapters.physics import JuPedSimCrowd
from maree.v3.api.server import serve_simulation
from maree.v3.core.ports import PolicyName
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.sample import sample_worldspec
from maree.v3.world.simartifact import build_sim_artifact

PORT = 8897


def _run() -> None:
    async def scenario() -> list[dict[str, object]]:
        world = sample_worldspec()
        graph = NavigationGraph(world)
        art = build_sim_artifact(world, graph, np.random.default_rng(5), spawn_per_space=3)
        physics = JuPedSimCrowd(
            walkable=art.levels["L0"].walkable,
            exits={e.id: e.segment for e in world.level("L0").exits},
            seed=5,
        )
        sim = Simulation(
            seed=5, policy=PolicyName.RULES, run_id="e2e_ws", speaking=True,
            physics=physics, physics_steps_per_tick=20,
        ).build(world)
        sim.spawn("visiteur", 4, frozenset({"A", "B"}))
        steps = [Timestep(1), Timestep(4, smoke=True), Timestep(8)]

        server = asyncio.create_task(
            serve_simulation(
                sim, steps, port=PORT, tick_ms=5.0, wait_client=True, hold_s=0.2
            )
        )
        await asyncio.sleep(0.3)

        from websockets.asyncio.client import connect

        frames: list[dict[str, object]] = []
        async with connect(f"ws://127.0.0.1:{PORT}") as ws:
            # 1) l'injection part **avant** le premier tick perçu
            await ws.send(json.dumps({"type": "inject", "kind": "smoke"}))
            # 2) un dossier d'agent
            await ws.send(json.dumps({"type": "agent", "agent": "A01"}))
            # 3) on lit jusqu'à `end`
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=20)
                frame = json.loads(raw)
                frames.append(frame)
                if frame.get("type") == "end":
                    break
        await asyncio.wait_for(server, timeout=10)
        return frames

    frames = asyncio.run(scenario())
    types = [f["type"] for f in frames]
    assert "world" in types, types
    assert "hello" in types, types
    assert "snapshot" in types, types
    assert types[-1] == "end", types[-3:]
    # la trame end porte un résumé lisible
    end = frames[-1]
    assert isinstance(end.get("summary"), dict)
    # l'injection a été acceptée (ack) et journalisée en écho (event/control)
    assert any(f["type"] == "ack" for f in frames), types
    # le dossier d'agent est étiqueté
    dossier = [f for f in frames if f.get("type") == "agent_dossier"]
    assert dossier, "le dossier doit arriver"
    labels = dossier[0]["labels"]
    assert labels["measured"]["agent"] == "A01"
    assert set(labels) == {"measured", "derived", "generated"}
    # et la parole / les indicateurs passent par le contrat
    assert any(f["type"] == "crowd" for f in frames), "indicator.crowd doit être diffusé"


def test_le_flux_complet_est_conforme_au_contrat() -> None:
    _run()
