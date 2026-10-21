"""Serveur WebSocket pour Godot (décision 9 : Godot est un consommateur pur).

Le serveur diffuse l'état du monde (instantanés agrégés) et reçoit les
commandes de contrôle (injection d'événements D3) et les requêtes
d'inspection d'agent (D2). Aucune logique de simulation ici.

`enabled=False` : aucun socket (utilisé par les tests et le replay
hors-ligne — Godot n'étant pas connecté, la diffusion est no-op).
"""
from __future__ import annotations

import asyncio
import json

import websockets


class WSRelay:
    """Relais bidirectionnel Python <-> Godot."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        *,
        enabled: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.enabled = enabled
        self.clients: set = set()
        self.on_command = None
        self._server = None
        # Dernier message diffusé par type : un client qui se connecte après
        # le début du run doit voir l'état courant, pas un écran vide.
        self._last: dict[str, dict] = {}

    async def start(self) -> None:
        if not self.enabled:
            return
        self._server = await websockets.serve(self._handler, self.host, self.port)

    async def _handler(self, ws) -> None:
        self.clients.add(ws)
        print(f"[ws] client connecté ({len(self.clients)} connecté(s))", flush=True)
        # Rejoue l'état courant au nouvel arrivant (état + indicateurs).
        for kind in ("state", "indicators"):
            cached = self._last.get(kind)
            if cached:
                try:
                    await ws.send(json.dumps(cached))
                except Exception:  # pragma: no cover - client déjà parti
                    pass
        try:
            async for message in ws:
                await self._dispatch(ws, message)
        except websockets.ConnectionClosed:
            # Déconnexion brutale de Godot (quit, redémarrage) : normal.
            pass
        finally:
            self.clients.discard(ws)
            print(f"[ws] client déconnecté ({len(self.clients)} restant(s))", flush=True)

    async def _dispatch(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return
        kind = data.get("type")
        if kind == "command" and self.on_command is not None:
            # injection d'événement depuis Godot (D3)
            await self.on_command(data)
        elif kind == "inspect":
            if self.on_command is not None:
                await self.on_command(data)
        elif kind == "ping":
            await ws.send(json.dumps({"type": "pong"}))

    async def broadcast(self, payload: dict) -> None:
        if not self.enabled:
            return
        kind = payload.get("type")
        if kind:
            self._last[kind] = payload
        if not self.clients:
            return
        data = json.dumps(payload)
        await asyncio.gather(
            *(c.send(data) for c in self.clients), return_exceptions=True
        )

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None