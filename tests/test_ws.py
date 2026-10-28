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
    assert kinds == ["event", "snapshot", "indicators", "narrative", "snapshot", "end"]
    assert frames[0]["event"] == "run.started"
    assert frames[1]["tick"] == 0
    assert frames[4]["tick"] == 1


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


def _journal_cognition(tmp_path: Path) -> JsonlJournal:
    """Un run qui contient de la cognition, pas seulement des positions."""
    journal = JsonlJournal(tmp_path)
    events = [
        _event(
            1,
            EventType.RUN_STARTED,
            {"seed": 7, "config_hash": "abc", "plan": "port_aubel"},
        ),
        _event(2, EventType.WORLD_SMOKE, {"position": [44.0, 15.0], "radius": 15.0}, tick=1),
        _event(3, EventType.EXIT_CLOSED, {"exit": "A"}, tick=2),
        _event(4, EventType.ANNOUNCEMENT, {"text": "Évacuation."}, tick=3),
        _event(
            5,
            EventType.DECISION,
            {
                "agent_id": "A01",
                "kind": "llm",
                "trigger": "fumee",
                "reason": "je sors par B",
                "intention": {"kind": "go_exit", "target": "B"},
                "beliefs": {"B": {"confidence": 0.8}},
                "density": 1.2,
                "llm": {"prompt": "un prompt de trois kilo-octets", "response": "go_exit B"},
            },
            tick=1,
        ),
        _event(
            6,
            EventType.BELIEF_UPDATED,
            {"agent_id": "A01", "beliefs": {"B": {"confidence": 0.8}}},
            tick=1,
        ),
        _event(
            7,
            EventType.MESSAGE_SENT,
            {"from": "A01", "to": ["A02"], "content": "il faut sortir"},
            tick=1,
        ),
        _event(
            8,
            EventType.MESSAGE_HEARD,
            {"agent_id": "A02", "from": "A01", "content": "il faut sortir"},
            tick=1,
        ),
        _event(9, EventType.EVACUATED, {"agent_id": "A02", "kind": "exit"}, tick=2),
        _event(10, EventType.INJECTION, {"kind": "close_exit", "exit": "B"}, tick=2),
        _event(11, EventType.SNAPSHOT, {"tick": 2, "agents": []}, tick=2),
        _event(12, EventType.RUN_ENDED, {"ticks": 2}, tick=2),
    ]
    for event in events:
        journal.append(event)
    return journal


async def _frames_of(streamer: JournalStreamer) -> list[dict]:
    frames = []
    async for frame in streamer._frames():
        frames.append(frame)
        if len(frames) > 50:  # garde-fou : ne doit jamais boucler
            break
    return frames


async def test_les_evenements_de_cognition_sont_diffuses(tmp_path: Path) -> None:
    """Sans ces trames, le client ne peut montrer que des points qui bougent."""
    streamer = JournalStreamer(_journal_cognition(tmp_path), RUN, plan={}, speed=0)
    frames = await _frames_of(streamer)
    assert [f["type"] for f in frames] == [
        "event",      # run.started — aucun événement n'est filtré
        "world",      # fumée
        "world",      # sortie A fermée
        "world",      # annonce
        "decision",
        "belief",
        "message",
        "heard",
        "evacuated",
        "event",      # control.injection, type sans trame dédiée
        "snapshot",
        "end",
    ]
    kinds = [f.get("kind") for f in frames if f["type"] == "world"]
    assert kinds == ["smoke", "exit_closed", "announcement"]

    decision = next(f for f in frames if f["type"] == "decision")
    assert decision["agent_id"] == "A01"
    assert decision["tick"] == 1
    assert decision["intention"]["target"] == "B"

    message = next(f for f in frames if f["type"] == "message")
    assert message["to"] == ["A02"]


async def test_le_prompt_nest_pas_diffuse_par_defaut(tmp_path: Path) -> None:
    """~3 Ko par décision : inutile pour dessiner, donc hors du flux."""
    streamer = JournalStreamer(_journal_cognition(tmp_path), RUN, plan={}, speed=0)
    decision = next(f for f in await _frames_of(streamer) if f["type"] == "decision")
    assert "prompt" not in decision["llm"]
    assert decision["llm"]["response"] == "go_exit B"


async def test_le_prompt_est_diffuse_si_demande(tmp_path: Path) -> None:
    streamer = JournalStreamer(
        _journal_cognition(tmp_path), RUN, plan={}, speed=0, include_prompts=True
    )
    decision = next(f for f in await _frames_of(streamer) if f["type"] == "decision")
    assert decision["llm"]["prompt"] == "un prompt de trois kilo-octets"


async def test_aucun_evenement_nest_perdu(tmp_path: Path) -> None:
    """Tout le journal est diffusé : un type inconnu passe en `event`."""
    streamer = JournalStreamer(_journal_cognition(tmp_path), RUN, plan={}, speed=0)
    frames = await _frames_of(streamer)

    inject = next(f for f in frames if f.get("event") == "control.injection")
    assert inject["seq"] == 10
    assert inject["data"]["exit"] == "B"

    belief = next(f for f in frames if f["type"] == "belief")
    assert belief["agent_id"] == "A01"
    assert belief["beliefs"]["B"]["confidence"] == 0.8

    heard = next(f for f in frames if f["type"] == "heard")
    assert heard["agent_id"] == "A02"


def test_hello_porte_les_metadonnees_du_run(tmp_path: Path) -> None:
    streamer = JournalStreamer(_journal_cognition(tmp_path), RUN, plan={}, speed=0)
    assert streamer._run_meta() == {
        "seed": 7,
        "config_hash": "abc",
        "plan": "port_aubel",
    }
