"""Enveloppe d'événements — la brique dont dépend tout le reste.

Décisions respectées :

    1  le journal (JSONL append-only) est la source de vérité ;
    2  double horodatage : `t_prod` (tick de production) et `t_trait`
       (tick de traitement), plus `t_real` réservé au journal ;
    3  aucun appel à l'horloge système dans la logique du monde ;
    4  `schema_version` + `causation_id` ;
   16  chaque événement porte son `seq`, l'ordre canonique est le tri.

Le champ `causation_id` n'était jamais rempli en v1 (exigence B4 non
tenue). Ici, `Event.child()` le remplit mécaniquement : un événement
sait toujours quel événement l'a causé.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from maree.domain.ids import RunId, Seq, Tick

SCHEMA_VERSION = "2.0.0"


class EventType(StrEnum):
    # cycle de vie
    RUN_STARTED = "run.started"
    RUN_ENDED = "run.ended"
    TICK = "tick"
    SNAPSHOT = "world.snapshot"
    # monde
    WORLD_SMOKE = "world.smoke"
    EXIT_CLOSED = "world.exit_closed"
    ANNOUNCEMENT = "world.announcement"
    INJECTION = "control.injection"
    #: A1 — la préhistoire (J-3 .. J-1) est journalisée comme un fait du
    #: monde, pas comme une initialisation silencieuse : sans cela, on ne
    #: pourrait pas dire ce que l'agent savait avant t0.
    MEMORY_SEEDED = "memory.seeded"
    # agents
    DECISION = "agent.decision"
    EVACUATED = "agent.evacuated"
    BELIEF_UPDATED = "agent.belief"
    MESSAGE_SENT = "agent.message.sent"
    MESSAGE_HEARD = "agent.message.heard"
    # dérives de modèle (A4)
    INCIDENT = "agent.incident"
    # mesure et récit
    INDICATORS = "metrics.indicators"
    NARRATIVE = "narrative.generated"
    # cohérence (C6)
    TEMPORAL_VIOLATION = "temporal.violation"
    # erreurs (F4)
    INVALID = "dlq.invalid"


@dataclass(frozen=True, slots=True)
class Event:
    seq: Seq
    run_id: RunId
    type: EventType
    t_prod: Tick
    t_trait: Tick
    t_real: float
    causation_id: str | None = None
    correlation_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    @property
    def id(self) -> str:
        return f"{self.run_id}:{self.seq:06d}"

    def child(
        self,
        *,
        seq: Seq,
        type: EventType,
        t_trait: Tick,
        t_real: float,
        data: dict[str, Any],
        t_prod: Tick | None = None,
    ) -> Event:
        """Événement dérivé : la causalité est établie automatiquement (B4).

        `causation_id` pointe l'événement **directement** responsable ;
        `correlation_id` est la racine de la chaîne, donc toute une
        arborescence causale se retrouve d'un seul filtre.

        `t_prod` est le tick où l'effet se produit, qui n'est pas celui de
        la cause (un message lu trois ticks plus tard, une décision
        appliquée après le retour du modèle) : C3 exige de distinguer les
        deux, on ne les confond donc pas ici.
        """
        return Event(
            seq=seq,
            run_id=self.run_id,
            type=type,
            t_prod=self.t_prod if t_prod is None else t_prod,
            t_trait=t_trait,
            t_real=t_real,
            causation_id=self.id,
            correlation_id=self.correlation_id or self.id,
            data=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "run_id": self.run_id,
            "type": str(self.type),
            "t_prod": self.t_prod,
            "t_trait": self.t_trait,
            "t_real": round(self.t_real, 6),
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "schema_version": self.schema_version,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Event:
        return cls(
            seq=int(d["seq"]),
            run_id=d["run_id"],
            type=EventType(d["type"]),
            t_prod=int(d["t_prod"]),
            t_trait=int(d["t_trait"]),
            t_real=float(d.get("t_real", 0.0)),
            causation_id=d.get("causation_id"),
            correlation_id=d.get("correlation_id"),
            data=d.get("data") or {},
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )


# ============================================================
# Schémas par type (F4) — ce qui doit exister pour qu'un
# événement soit lisible par le rejeu et par le client.
# ============================================================
#: Champs obligatoires dans `data`, par type. Ce n'est pas un schéma
#: exhaustif (JSON Schema serait plus lourd que le besoin) : c'est le
#: contrat minimal que le rejeu et l'interface consomment. Un événement
#: qui n'a pas ces clés est isolé, jamais écrit dans le journal principal.
SCHEMAS: dict[EventType, tuple[str, ...]] = {
    EventType.RUN_STARTED: ("config_hash", "seed", "plan"),
    EventType.RUN_ENDED: ("ticks", "llm_calls", "evacuated", "total"),
    EventType.SNAPSHOT: ("tick", "agents"),
    EventType.WORLD_SMOKE: ("position", "radius"),
    EventType.EXIT_CLOSED: ("exit",),
    EventType.ANNOUNCEMENT: ("text",),
    EventType.INJECTION: ("kind",),
    EventType.MEMORY_SEEDED: ("agents", "days"),
    EventType.DECISION: ("agent_id", "kind", "trigger", "intention"),
    EventType.EVACUATED: ("agent_id", "kind"),
    EventType.BELIEF_UPDATED: ("agent_id", "beliefs"),
    EventType.MESSAGE_SENT: ("from", "to", "content"),
    EventType.MESSAGE_HEARD: ("agent_id", "from", "content"),
    EventType.INCIDENT: ("agent_id", "kind"),
    EventType.INDICATORS: ("tick", "I1_consensus", "I3_evacuated"),
    EventType.NARRATIVE: ("text", "valid"),
    EventType.TEMPORAL_VIOLATION: ("agent_id", "reason"),
    EventType.INVALID: ("type", "problems"),
}


def validate(event: Event) -> list[str]:
    """Problèmes de forme et de temps d'un événement ; liste vide = valide.

    Deux familles, volontairement séparées :

      * **forme** — les clés que le rejeu et le client lisent ;
      * **temps** — `t_prod <= t_trait` (C3). Un événement produit après
        son traitement est une incohérence d'horloge, pas un détail.
    """
    problems: list[str] = []
    if event.seq <= 0:
        problems.append(f"seq non positif : {event.seq}")
    if event.t_prod > event.t_trait:
        problems.append(f"t_prod ({event.t_prod}) > t_trait ({event.t_trait})")
    required = SCHEMAS.get(event.type, ())
    missing = [key for key in required if key not in event.data]
    if missing:
        problems.append(f"champs manquants : {', '.join(missing)}")
    return problems
