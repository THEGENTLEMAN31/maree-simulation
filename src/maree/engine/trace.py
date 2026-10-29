"""Remonter d'un saut d'indicateur aux échanges qui l'ont précédé (B4).

Le journal porte `causation_id` (l'événement directement responsable) et
`correlation_id` (la racine de la chaîne). Ce module en fait deux choses :

    * `ancestors()` — la chaîne complète d'un événement, de la racine à lui ;
    * `report()` — pour la plus forte variation d'un indicateur, les
      décisions et les messages qui l'ont précédée, chacun avec sa chaîne.

Ce n'est pas un outil de confort : c'est la pièce qui permet de répondre à
« qu'est-ce qui a fait basculer la foule ? » autrement que par une
impression visuelle. Le client Godot peut l'appeler pour dessiner la
généalogie d'une décision.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from maree.domain.events import Event, EventType


@dataclass(frozen=True, slots=True)
class Step:
    """Un maillon lisible d'une chaîne causale."""

    seq: int
    tick: int
    type: str
    agent: str | None
    label: str
    cause: str | None
    correlation: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "tick": self.tick,
            "type": self.type,
            "agent": self.agent,
            "label": self.label,
            "cause": self.cause,
            "correlation": self.correlation,
        }


def _agent_of(event: Event) -> str | None:
    data = event.data
    for key in ("agent_id", "from"):
        if isinstance(data.get(key), str):
            return data[key]
    return None


def describe(event: Event) -> str:
    """Une phrase, pas un dict : c'est destiné à être lu par un humain."""
    d = event.data
    match event.type:
        case EventType.DECISION:
            target = d.get("intention", {}).get("target")
            return (
                f"{d.get('agent_id')} décide {d.get('intention', {}).get('kind')}"
                f"{' ' + str(target) if target else ''} ({d.get('trigger')}) — {d.get('reason')}"
            )
        case EventType.MESSAGE_SENT:
            return f"{d.get('from')} dit à {len(d.get('to') or [])} voisins : {d.get('content')}"
        case EventType.MESSAGE_HEARD:
            return f"{d.get('agent_id')} entend {d.get('from')} : {d.get('content')}"
        case EventType.BELIEF_UPDATED:
            beliefs = d.get("beliefs") or {}
            best = max(beliefs.items(), key=lambda kv: kv[1].get("confidence", 0), default=None)
            return f"{d.get('agent_id')} croit {best[0]} à {best[1].get('confidence', 0):.2f}" if best else f"{d.get('agent_id')} : aucune croyance"
        case EventType.EVACUATED:
            return f"{d.get('agent_id')} franchit une sortie"
        case EventType.WORLD_SMOKE:
            return "fumée visible près de la scène"
        case EventType.ANNOUNCEMENT:
            return f"annonce officielle : {d.get('text')}"
        case EventType.EXIT_CLOSED:
            return f"sortie {d.get('exit')} fermée"
        case _:
            return str(event.type)


def to_step(event: Event) -> Step:
    return Step(
        seq=event.seq,
        tick=event.t_prod,
        type=str(event.type),
        agent=_agent_of(event),
        label=describe(event),
        cause=event.causation_id,
        correlation=event.correlation_id,
    )


def index(events: list[Event]) -> dict[str, Event]:
    return {e.id: e for e in events}


def ancestors(events_by_id: dict[str, Event], event: Event, max_depth: int = 12) -> list[Event]:
    """Chaîne causale, de la racine à `event` (bornée : un journal peut boucler)."""
    chain: list[Event] = [event]
    seen = {event.id}
    current = event
    while current.causation_id and current.causation_id in events_by_id and len(chain) < max_depth:
        current = events_by_id[current.causation_id]
        if current.id in seen:
            break
        seen.add(current.id)
        chain.append(current)
    return list(reversed(chain))


def variation(
    events: list[Event], key: str = "I1_consensus"
) -> tuple[int, float, float] | None:
    """Tick de plus forte variation de `key`, avec les deux valeurs.

    Le dernier tick d'un run est dégénéré : tout le monde est sorti, donc
    I1/I2/I5/I6 valent 0. C'est le même piège que `metrics.summarise()` ;
    l'inclure ferait de « la foule s'est vidée » la plus forte variation de
    consensus, et masquerait le vrai basculement.
    """
    series: list[tuple[int, float]] = []
    for e in events:
        if e.type is not EventType.INDICATORS or key not in e.data:
            continue
        counts = e.data.get("counts") or {}
        agents = int(counts.get("agents") or 0)
        evacuated = int(counts.get("evacuated") or 0)
        if agents and evacuated >= agents:
            continue
        series.append((e.t_prod, float(e.data.get(key, 0.0))))
    best: tuple[int, float, float] | None = None
    for (_, previous), (tick, value) in pairwise(series):
        delta = value - previous
        if best is None or abs(delta) > abs(best[1] - best[2]):
            best = (tick, previous, value)
    return best


def preceding(events: list[Event], tick: int, lookback: int = 5) -> list[Event]:
    """Décisions et messages dans la fenêtre qui précède `tick`."""
    keep = {
        EventType.DECISION,
        EventType.MESSAGE_SENT,
        EventType.MESSAGE_HEARD,
        EventType.WORLD_SMOKE,
        EventType.ANNOUNCEMENT,
        EventType.EXIT_CLOSED,
    }
    return [
        e
        for e in events
        if e.type in keep and tick - lookback <= e.t_prod <= tick
    ]


def report(
    events: list[Event], *, key: str = "I1_consensus", lookback: int = 5
) -> dict[str, Any]:
    """Ce qui a précédé la plus forte variation d'un indicateur."""
    found = variation(events, key)
    if found is None:
        return {"indicator": key, "found": False, "reason": "moins de deux mesures"}
    tick, previous, value = found
    by_id = index(events)
    window = preceding(events, tick, lookback)
    return {
        "indicator": key,
        "found": True,
        "tick": tick,
        "from": round(previous, 4),
        "to": round(value, 4),
        "delta": round(value - previous, 4),
        "lookback": lookback,
        "events": [to_step(e).to_dict() for e in window],
        "chains": [
            [s.to_dict() for s in ancestors(by_id, e)]
            for e in window
            if e.type is EventType.DECISION
        ],
    }
