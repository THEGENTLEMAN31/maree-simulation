"""api.server — le serveur de trames WebSocket (P4).

Il ne contient **aucune logique de simulation** : il lit le bus (journal
diffusé) et envoie les trames du contrat. Deux sens :

- **serveur → client** : ``hello``, ``world``, ``decision``, ``snapshot``,
  ``hazard``, ``message``, ``evacuated``, ``indicators``, ``incident``,
  ``event`` (tout ce qui n'a pas de trame dédiée), puis ``end`` ;
- **client → serveur** : ``inject`` (fumée, annonce, message), ``agent``
  (dossier étiqueté), ``hello`` (renégociation).

L'injection n'est appliquée qu'au **tick suivant** (file du moteur) : tous les
agents perçoivent le même instant (convention v2 conservée).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from maree.v3.api.dossier import agent_dossier
from maree.v3.api.frames import (
    PROTOCOL_VERSION,
    end_frame,
    error_frame,
    frame_for,
    hello_frame,
    world_frame,
)
from maree.v3.sim.journal import world_hash
from maree.v3.sim.orchestrator import Simulation


class Broadcaster:
    """Diffuse les trames aux clients connectés et traite leurs commandes."""

    def __init__(self, sim: Simulation) -> None:
        self.sim = sim
        self.clients: set[Any] = set()
        self.connected = asyncio.Event()
        self._last: dict[str, Any] = {}
        self._last_snapshot: dict[str, Any] | None = None

    def world(self) -> Any:
        assert self.sim.world is not None, "simulation non construite (build)"
        return self.sim.world

    async def send(self, websocket: Any, frame: dict[str, Any]) -> None:
        await websocket.send(json.dumps(frame, ensure_ascii=False))

    async def broadcast(self, frame: dict[str, Any]) -> None:
        self._last = frame
        if frame.get("type") == "snapshot":
            self._last_snapshot = frame
        if not self.clients:
            return
        dead = []
        for ws in self.clients:
            try:
                await self.send(ws, frame)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    def last_frame(self) -> dict[str, Any]:
        """Dernière trame diffusée (utile au client qui se connecte en cours)."""
        return self._last

    async def handler(self, websocket: Any) -> None:
        self.clients.add(websocket)
        self.connected.set()
        await self.send(websocket, hello_frame(
            self.sim.run_id, self.world(), world_hash(self.world()),
            nd_agents=len(self.sim.scene.instances),
        ))
        # un client qui arrive en cours de run reçoit la géométrie et le dernier
        # instantané (pas de trou d'affichage), puis le flux à partir de maintenant.
        await self.send(websocket, world_frame(self.world(), world_hash(self.world())))
        if self._last_snapshot is not None:
            await self.send(websocket, self._last_snapshot)
        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except (TypeError, ValueError):
                    await self.send(websocket, error_frame(self.sim.run_id, "bad_json", "trame invalide"))
                    continue
                await self._command(websocket, msg)
        finally:
            self.clients.discard(websocket)

    async def _command(self, websocket: Any, msg: dict[str, Any]) -> None:
        t = msg.get("type")
        if t == "hello":
            await self.send(websocket, hello_frame(
                self.sim.run_id, self.world(), world_hash(self.world()),
                nd_agents=len(self.sim.scene.instances),
            ))
        elif t == "inject":
            payload = {k: v for k, v in msg.items() if k != "type"}
            self.sim.submit(payload)
            await self.send(websocket, {
                "v": PROTOCOL_VERSION,
                "type": "ack",
                "run_id": self.sim.run_id,
                "queued": payload,
                "at_tick": self.sim.scene.tick + 1,
            })
        elif t in ("agent", "agent_dossier"):
            name = str(msg.get("agent", ""))
            dossier = agent_dossier(self.sim, name)
            if not dossier:
                await self.send(websocket, error_frame(
                    self.sim.run_id, "agent_not_found", f"agent inconnu : {name!r}",
                ))
            else:
                await self.send(websocket, dossier)
        else:
            await self.send(websocket, error_frame(
                self.sim.run_id, "unknown_command", f"commande inconnue : {t!r}",
            ))


async def serve_simulation(
    sim: Simulation,
    timesteps: list[Any],
    *,
    host: str = "127.0.0.1",
    port: int = 8766,
    tick_ms: float = 0.0,
    wait_client: bool = False,
    hold_s: float = 1.5,
) -> None:
    """Sert un run en direct : une trame par événement, cadencée par tick."""
    from websockets.asyncio.server import serve

    broadcaster = Broadcaster(sim)
    cursor = 0
    first_tick: int | None = None
    async with serve(broadcaster.handler, host, port):
        print(f"ws://{host}:{port} — run {sim.run_id}")
        await broadcaster.broadcast(world_frame(broadcaster.world(), world_hash(broadcaster.world())))
        if wait_client:
            await broadcaster.connected.wait()
        for tick in sim.iter_ticks(timesteps):
            if first_tick is None:
                first_tick = tick
            envelopes = getattr(sim.bus, "envelopes", [])
            while cursor < len(envelopes):
                await broadcaster.broadcast(frame_for(envelopes[cursor]))
                cursor += 1
            if tick_ms > 0:
                await asyncio.sleep(tick_ms / 1000.0)
        summary = {
            "ticks": sim.scene.tick - (first_tick or 0),
            "decisions": len(sim.log.rows),
            "evacuated": len(sim._evacuated),
            "incidents": dict(sorted(sim.incidents.items())),
        }
        await broadcaster.broadcast(end_frame(sim.run_id, summary))
        await asyncio.sleep(hold_s)


__all__ = ["Broadcaster", "serve_simulation"]
