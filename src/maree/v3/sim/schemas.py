"""sim.schemas — les schémas **versionnés** des événements du bus (F4).

Un client (Godot, notebook, autre service) ne doit pas deviner la forme des
trames. Chaque enveloppe porte ``schema: "maree.event/<version>"`` et chaque
type connu déclare ses champs **obligatoires** dans ``data``. La validation
est un **diagnostic** : elle ne filtre rien (convention : aucun événement du
journal n'est filtré), elle dit seulement ce qui manque à une trame.
"""

from __future__ import annotations

#: version du contrat d'événement — à incrémenter dès qu'un champ obligatoire
#: change de nom ou de sens (les clients comparent cette chaîne).
SCHEMA_VERSION = "1.0"
EVENT_SCHEMA_ID = f"maree.event/{SCHEMA_VERSION}"

#: champs obligatoires de ``data`` par type d'événement connu.
SCHEMAS: dict[str, tuple[str, ...]] = {
    "agent.decision": (
        "agent", "archetype", "action", "target", "fallback",
        "fallback_cause", "explanation",
    ),
    "agent.evacuated": ("agent",),
    "agent.incident": ("agent", "cause"),
    "world.smoke": ("visible",),
    "world.announcement": ("text",),
    "world.snapshot": ("agents",),
    "indicator.emergence": ("consensus", "couplage", "emergence"),
    "indicator.incidents": ("total", "par_cause"),
}


def is_known(event_type: str) -> bool:
    """Le type figure-t-il au contrat versionné ?"""
    return event_type in SCHEMAS


def schema_for(event_type: str) -> tuple[str, ...] | None:
    """Champs obligatoires d'un type, ou ``None`` si le type n'est pas schématisé."""
    return SCHEMAS.get(event_type)


def validate(event_type: str, data: dict[str, object]) -> list[str]:
    """Erreurs de schéma d'une trame (liste vide = conforme).

    Un type inconnu est signalé (le client ne saura pas le lire), mais cela
    n'empêche ni la publication ni le journal.
    """
    required = SCHEMAS.get(event_type)
    if required is None:
        return [f"type non schématisé : {event_type}"]
    return [f"champ manquant : {name}" for name in required if name not in data]


__all__ = [
    "EVENT_SCHEMA_ID",
    "SCHEMAS",
    "SCHEMA_VERSION",
    "is_known",
    "schema_for",
    "validate",
]
