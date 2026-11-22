"""api.frames — du journal (source de vérité) aux **trames d'affichage** (P4).

Chaque enveloppe publiée sur le bus est traduite en une trame lisible par le
front (Godot ou tout autre client), selon le contrat de
``docs/v3/donnees-et-api.md`` §5. Deux règles :

1. **aucun événement n'est perdu** : un type sans trame dédiée passe en
   ``event`` (enveloppe comprise) ;
2. **le temps simulé est celui de l'enveloppe** (``t_prod``/``t_trait``),
   jamais un horodatage d'horloge.
"""

from __future__ import annotations

from typing import Any, cast

from maree.v3.sim.bus import EventEnvelope
from maree.v3.sim.schemas import EVENT_SCHEMA_ID
from maree.v3.world.worldspec import WorldSpec

#: version de protocole WS (négociée par ``hello``)
PROTOCOL_VERSION = 3


def _base(env: EventEnvelope) -> dict[str, Any]:
    """Champs communs à toute trame (contrat §5.1)."""
    return {
        "v": PROTOCOL_VERSION,
        "schema": EVENT_SCHEMA_ID,
        "run_id": env.run_id,
        "seq": env.seq,
        "t_prod": env.t_prod,
        "t_trait": env.t_trait,
        "causation_id": env.causation_id,
    }


def hello_frame(run_id: str, world: WorldSpec, world_hash: str, nd_agents: int = 0) -> dict[str, Any]:
    """Première trame : identité du run et capacités du serveur."""
    return {
        "v": PROTOCOL_VERSION,
        "schema": EVENT_SCHEMA_ID,
        "type": "hello",
        "run_id": run_id,
        "world": {"id": world.id, "hash": world_hash, "levels": [lv.id for lv in world.levels]},
        "protocol_version": PROTOCOL_VERSION,
        "agents": nd_agents,
        "capabilities": ["snapshot", "event", "agent_dossier", "inject"],
    }


def world_frame(world: WorldSpec, world_hash: str) -> dict[str, Any]:
    """Géométrie brute pour le rendu (le front a déjà le glTF par ailleurs)."""
    return {
        "v": PROTOCOL_VERSION,
        "schema": EVENT_SCHEMA_ID,
        "type": "world",
        "world_id": world.id,
        "world_hash": world_hash,
        "levels": [
            {
                "id": lv.id,
                "exits": [
                    {"id": e.id, "segment": [list(p) for p in e.segment], "width": e.width}
                    for e in lv.exits
                ],
                "spaces": [
                    {"id": s.id, "kind": s.kind, "polygon": [list(p) for p in s.polygon]}
                    for s in lv.spaces
                ],
            }
            for lv in world.levels
        ],
    }


def end_frame(run_id: str, summary: dict[str, object]) -> dict[str, Any]:
    return {
        "v": PROTOCOL_VERSION,
        "schema": EVENT_SCHEMA_ID,
        "type": "end",
        "run_id": run_id,
        "summary": summary,
    }


def error_frame(run_id: str, code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {
        "v": PROTOCOL_VERSION,
        "schema": EVENT_SCHEMA_ID,
        "type": "error",
        "run_id": run_id,
        "error": {"code": code, "message": message, "retryable": retryable},
    }


def frame_for(env: EventEnvelope) -> dict[str, Any]:
    """Traduit une enveloppe en trame d'affichage (ou ``event`` en repli)."""
    t = env.type
    d = cast("dict[str, Any]", env.data)
    frame = _base(env)

    if t == "agent.decision":
        frame.update(
            type="decision",
            agent=d.get("agent"),
            archetype=d.get("archetype"),
            action=d.get("action"),
            target=d.get("target"),
            reason=d.get("explanation"),
            fallback=d.get("fallback"),
            fallback_cause=d.get("fallback_cause"),
            arm=d.get("arm"),
            escalation_cause=d.get("escalation_cause"),
            target_resolved=d.get("target_resolved", False),
            target_least_bad=d.get("target_least_bad", False),
            target_believed_blocked=d.get("target_believed_blocked", False),
        )
    elif t == "world.snapshot":
        frame.update(type="snapshot", tick=env.t_trait, agents=d.get("agents", {}))
    elif t == "world.smoke":
        frame.update(type="hazard", source="smoke", visible=d.get("visible", True))
    elif t == "world.announcement":
        frame.update(type="message", emitter="autorite", content=d.get("text"))
    elif t == "agent.evacuated":
        frame.update(type="evacuated", agent=d.get("agent"))
    elif t == "agent.incident":
        frame.update(type="incident", agent=d.get("agent"), cause=d.get("cause"))
    elif t == "indicator.emergence":
        frame.update(
            type="indicators",
            consensus=d.get("consensus"),
            couplage=d.get("couplage"),
            emergence=d.get("emergence"),
            null_consensus=d.get("null_consensus"),
            social_excess=d.get("social_excess"),
        )
    elif t == "indicator.crowd":
        # les I1–I7 de la foule, tels que le moteur les calcule (C4)
        frame.update(
            type="crowd",
            I1=d.get("I1_consensus"),
            I2=d.get("I2_entropy"),
            I3=d.get("I3_evacuated"),
            I4=d.get("I4_seconds"),
            I5=d.get("I5_max_density"),
            I6=d.get("I6_belief_gap"),
            I7=d.get("I7_delay_seconds"),
            closed_exits=d.get("closed_exits", []),
        )
    elif t == "agent.message":
        # la parole des agents (C7) et l'annonce officielle partagent le type
        # `message` : le client les distingue par `emitter`.
        frame.update(
            type="message",
            emitter=d.get("from"),
            content=d.get("fact"),
            to=d.get("to", []),
            confidence=d.get("confidence"),
            kind=d.get("kind"),
        )
    elif t == "agent.escalation":
        frame.update(
            type="escalation",
            agent=d.get("agent"),
            cause=d.get("cause"),
            detail=d.get("detail", {}),
        )
    elif t == "agent.reconsider":
        frame.update(type="reconsider", agent=d.get("agent"), reason=d.get("reason"))
    elif t == "world.exit_closed":
        frame.update(type="hazard", source="exit_closed", exit=d.get("exit"), visible=True)
    elif t == "indicator.incidents":
        frame.update(type="incident", total=d.get("total"), par_cause=d.get("par_cause"))
    else:
        # convention : aucun événement du journal n'est filtré
        frame.update(type="event", event_type=t, data=env.data)
    return frame


__all__ = [
    "PROTOCOL_VERSION",
    "end_frame",
    "error_frame",
    "frame_for",
    "hello_frame",
    "world_frame",
]
