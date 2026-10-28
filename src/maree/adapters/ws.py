"""Diffusion temps réel — le journal relu, rien d'autre.

Le serveur ne « pousse » pas l'état du moteur : il **relit le journal**
et diffuse les instantanés. Conséquence importante :

    * un client peut se connecter en cours de run (le fichier grandit) ;
    * un client peut rejouer un run terminé sans le moteur ;
    * si le serveur tombe, rien n'est perdu — le JSONL est toujours là.

C'est la même source de vérité que le rejeu E3, vue par un autre bout.

Protocole (JSON, un objet par trame) :

    {"type": "hello",      "run_id": …, "plan": {…}}
    {"type": "world",      "kind": "smoke"|"announcement"|"exit_closed", …}
    {"type": "decision",   "tick": …, "agent_id": …, "kind": "llm"|"rules", …}
    {"type": "message",    "tick": …, "from": …, "to": […], "content": …}
    {"type": "evacuated",  "tick": …, "agent_id": …, …}
    {"type": "snapshot",   "tick": …, "sim_time": …, "agents": […], …}
    {"type": "indicators", "I1_consensus": …, …}
    {"type": "narrative",  "text": …, "tick": …}
    {"type": "end",        "ticks": …}

L'ordre est celui du journal : pour un tick donné, les décisions et les
messages précèdent l'instantané, qui précède les indicateurs. Un client
peut donc animer « X décide » puis « voilà le nouvel état ».

Les trames `decision` portent le prompt LLM **seulement** si le serveur a
été lancé avec `--prompts` : ~3 Ko par décision, inutile pour dessiner.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from maree.domain.events import Event, EventType
from maree.ports import JournalPort

#: Événements de monde qui deviennent des trames `world` typées.
_WORLD_KINDS = {
    EventType.WORLD_SMOKE: "smoke",
    EventType.ANNOUNCEMENT: "announcement",
    EventType.EXIT_CLOSED: "exit_closed",
}


class JournalStreamer:
    def __init__(
        self,
        journal: JournalPort,
        run_id: str,
        *,
        plan: dict[str, Any],
        host: str = "0.0.0.0",
        port: int = 8765,
        speed: float = 5.0,
        include_prompts: bool = False,
    ) -> None:
        self._journal = journal
        self._run_id = run_id
        self._plan = plan
        self._host = host
        self._port = port
        #: ticks par seconde ; 0 = aussi vite que possible.
        self._speed = speed
        #: Inclure le prompt LLM dans les trames `decision` (~3 Ko chacune).
        self._include_prompts = include_prompts

    def _decision_frame(self, event: Event) -> dict[str, Any]:
        data = dict(event.data)
        if not self._include_prompts:
            llm = data.get("llm")
            if isinstance(llm, dict):
                data["llm"] = {k: v for k, v in llm.items() if k != "prompt"}
        return {"type": "decision", "tick": event.t_prod, **data}

    async def _frames(self) -> AsyncIterator[dict[str, Any]]:
        """Rejoue le journal, puis attend les événements suivants.

        Le délai est appliqué **par instantané**, pas par lot : sinon un
        run déjà terminé se déverserait d'un coup et l'animation
        n'existerait pas.
        """
        seen = 0
        delay = 1.0 / self._speed if self._speed > 0 else 0.0
        while True:
            events = self._journal.read(self._run_id)
            if seen >= len(events):
                await asyncio.sleep(0.2)
                continue
            for event in events[seen:]:
                seen += 1
                if event.type is EventType.SNAPSHOT:
                    yield {"type": "snapshot", **event.data}
                    if delay:
                        await asyncio.sleep(delay)
                elif event.type is EventType.INDICATORS:
                    yield {"type": "indicators", **event.data}
                elif event.type is EventType.DECISION:
                    yield self._decision_frame(event)
                elif event.type is EventType.MESSAGE_SENT:
                    yield {"type": "message", "tick": event.t_prod, **event.data}
                elif event.type is EventType.EVACUATED:
                    yield {"type": "evacuated", "tick": event.t_prod, **event.data}
                elif event.type in _WORLD_KINDS:
                    yield {
                        "type": "world",
                        "tick": event.t_prod,
                        "kind": _WORLD_KINDS[event.type],
                        **event.data,
                    }
                elif event.type is EventType.NARRATIVE:
                    yield {
                        "type": "narrative",
                        "tick": event.t_prod,
                        "text": event.data.get("text", ""),
                    }
                elif event.type is EventType.RUN_ENDED:
                    yield {"type": "end", **event.data}
                    return

    async def _handler(self, websocket) -> None:
        await websocket.send(
            json.dumps(
                {"type": "hello", "run_id": self._run_id, "plan": self._plan},
                ensure_ascii=False,
            )
        )
        try:
            async for frame in self._frames():
                await websocket.send(json.dumps(frame, ensure_ascii=False))
        except Exception:
            return
        # Godot abandonne les paquets encore en attente quand `poll()` voit
        # la socket fermée : sans ce délai, la dernière trame (`end`) était
        # perdue et le client affichait « déconnecté » sur une diffusion
        # pourtant terminée.
        await asyncio.sleep(0.3)
        await websocket.close()

    async def serve_forever(self) -> None:
        from websockets.asyncio.server import serve

        async with serve(self._handler, self._host, self._port):
            print(
                f"MARÉE — diffusion de {self._run_id} sur ws://{self._host}:{self._port} "
                f"({self._speed} ticks/s)"
            )
            await asyncio.Future()
