"""Enveloppe d'événements et schémas.

Décisions 1, 2, 3, 4 :
- le journal Kafka est la source de vérité (chaque sortie LLM y est enregistrée) ;
- double horodatage : t_prod (production) et t_trait (traitement), + heure réelle ;
- déterminisme : ordre canonique, aucune horloge système dans la logique du monde ;
- enveloppe commune versionnée : run_id, event_id, type, schema_version,
  agent_id, t_prod, t_trait, causation_id.

Tous les événements sont sérialisables en JSON (compatible Avro/JSON Schema, F4).
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """Enveloppe commune à tout événement du journal (décisions 2, 3, 4)."""

    schema_version: int = 1
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str
    type: str
    agent_id: str | None = None
    # Séquence monotone globale (décision 3 : ordre canonique du journal).
    # Assignée par le RunLogger ; jamais générée dans la logique du monde.
    seq: int = 0
    # Temps simulé (ticks) — la seule échelle de temps de la logique du monde.
    t_prod: int  # tick où l'événement se produit dans le monde simulé
    t_trait: int  # tick où l'événement est traité (consommé)
    # Heure réelle (horloge de la machine) — uniquement pour le suivi de coût
    # et les latences réelles (E4, C7) ; jamais utilisée dans la logique.
    t_real_ms: int = Field(default_factory=lambda: int(time.time() * 1000))
    # Chaîne de causalité (B4, F6) : événement parent qui a déclenché celui-ci.
    causation_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Types d'événements du MARÉE (F4 : jeux de types documentés et versionnés).
# ---------------------------------------------------------------------------

EVENT_TYPES: dict[str, int] = {
    # monde
    "world.smoke_update": 1,
    "world.announcement": 1,
    "world.exit_state": 1,
    "world.false_info": 1,
    "world.exit_closed": 1,
    # agents
    "agent.spawn": 1,
    "agent.perception": 1,
    "agent.message": 1,
    "agent.belief_change": 1,
    "agent.decision": 1,  # sortie LLM ou règle (décision 1 : toujours journalisée)
    "agent.drift": 1,  # dérive tracée (A4) : sortie de rôle, JSON invalide, timeout…
    "agent.memory_set": 1,  # écriture de mémoire (A1)
    "agent.rag_retrieval": 1,  # traçabilité RAG (décision 12)
    "oracle.violation": 1,  # incohérence temporelle (C6 / I5)
    # mouvement
    "movement.zone_enter": 1,
    "movement.evacuated": 1,
    "movement.trapped": 1,
    "movement.snapshot": 1,  # instantané agrégé des positions (C1)
    # métriques
    "metrics.indicators": 1,
    # contrôle
    "control.inject": 1,
    # erreurs
    "dlq.invalid": 1,
}


def new_envelope(
    run_id: str,
    type_: str,
    t_prod: int,
    t_trait: int,
    *,
    agent_id: str | None = None,
    causation_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> EventEnvelope:
    """Fabrique une enveloppe en vérifiant le type (F4)."""
    if type_ not in EVENT_TYPES:
        raise ValueError(f"type d'événement inconnu : {type_!r}")
    return EventEnvelope(
        run_id=run_id,
        type=type_,
        agent_id=agent_id,
        t_prod=t_prod,
        t_trait=t_trait,
        causation_id=causation_id,
        data=data or {},
    )


def now_iso() -> str:
    """Horodatage ISO UTC (métadonnées uniquement, pas dans la logique)."""
    return datetime.now(timezone.utc).isoformat()