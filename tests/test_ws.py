"""Diffusion WebSocket : le journal relu, dans l'ordre.

On ne teste pas le réseau ici (c'est fait à la main contre `maree serve`) :
on teste la séquence de trames, qui est le contrat avec Godot.
"""

from __future__ import annotations

from pathlib import Path

from maree.adapters.journal.jsonl import JsonlJournal
from maree.adapters.ws import JournalStreamer
from maree.domain.events import Event, EventType

RUN = "run_ws"


def _event(seq: int, type_: EventType, data: dict, tick: int = 0) -> Event:
    return Event(
        seq=seq, run_id=RUN, type=type_, t_prod=tick, t_trait=tick, t_real=0.0, data=data
    )


def _journal(tmp_path: Path) -> JsonlJournal:
    journal = JsonlJournal(tmp_path)
    events = [
        _event(1, EventType.RUN_STARTED, {}),
        _event(2, EventType.SNAPSHOT, {"tick": 0, "agents": []}, tick=0),
        _event(3, EventType.INDICATORS, {"tick": 0, "I1_consensus": 0.0}, tick=0),
        _event(4, EventType.NARRATIVE, {"text": "début"}, tick=0),
        _event(5, EventType.SNAPSHOT, {"tick": 1, "agents": []}, tick=1),
        _event(6, EventType.RUN_ENDED, {"ticks": 1}, tick=1),
    ]
    for event in events:
        journal.append(event)
    return journal


async def test_sequence_des_trames(tmp_path: Path) -> None:
    streamer = JournalStreamer(
        _journal(tmp_path), RUN, plan={"exits": []}, speed=0
    )
    frames = []
    async for frame in streamer._frames():
        frames.append(frame)
        if len(frames) > 20:  # garde-fou : ne doit jamais boucler
            break
    kinds = [f["type"] for f in frames]
    assert kinds == ["snapshot", "indicators", "narrative", "snapshot", "end"]
    assert frames[0]["tick"] == 0
    assert frames[3]["tick"] == 1


async def test_les_instantanes_sont_dans_lordre(tmp_path: Path) -> None:
    streamer = JournalStreamer(_journal(tmp_path), RUN, plan={}, speed=0)
    ticks = [f["tick"] async for f in streamer._frames() if f["type"] == "snapshot"]
    assert ticks == [0, 1]


async def test_run_sans_fin_ne_bloque_pas_le_generateur(tmp_path: Path) -> None:
    """Un run en cours : le flux doit rendre la main et attendre."""
    journal = JsonlJournal(tmp_path)
    journal.append(_event(1, EventType.SNAPSHOT, {"tick": 0}, tick=0))
    streamer = JournalStreamer(journal, RUN, plan={}, speed=0)
    frames = streamer._frames()
    first = await anext(frames)
    assert first["type"] == "snapshot"
    await frames.aclose()
