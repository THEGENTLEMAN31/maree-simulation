"""agents.prehistory — la préhistoire J−3 (A1, héritée de la v2, réécrite).

Chaque run commence *avant* l'évacuation : des échanges datés en tick
**négatif** (J−3 = −25 920, J−2 = −17 280, J−1 = −8 640 à 10 s/tick) passent
par les **mêmes** événements et la **même** mémoire que le run. Un agent
doit pouvoir « se souvenir d'un échange vieux de plusieurs jours simulés »
et l'invoquer dans sa justification : c'est la preuve A1.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from maree.v3.agents.knowledge import Belief, Knowledge, Source
from maree.v3.agents.memory import EpisodeKind, Memory
from maree.v3.core.ids import Tick

#: tick à 10 s : 1 jour simulé = 8 640 ticks.
J_3 = -3 * 8_640
J_2 = -2 * 8_640
J_1 = -1 * 8_640


@dataclass(frozen=True, slots=True)
class PrehistoryMessage:
    """Un échange préalable, daté d'un tick négatif, ciblé sur un arcétype."""

    tick: Tick
    speaker: str       # qui parle (profil / rôle)
    target: str        # archétype qui reçoit (visiteur, famille…)
    fact: str
    source: Source
    confidence: float = 0.8


#: Les échanges du cadrage (docs/cadrage-maree.md) — aux dates négatives.
PREHISTORY_MAREE: tuple[PrehistoryMessage, ...] = (
    PrehistoryMessage(
        J_3, "habitué", "visiteur",
        "la sortie C existe et évite la passerelle", Source.ENTENDU,
    ),
    PrehistoryMessage(
        J_2, "agent_de_securite", "famille",
        "la sortie B se bouche dès qu'il y a du monde", Source.GUIDE,
    ),
    PrehistoryMessage(
        J_1, "voisin", "famille",
        "la sortie A avait été fermée l'an dernier", Source.RUMEUR,
    ),
)


def seed_prehistory(
    memory: Memory,
    exchanges: Sequence[PrehistoryMessage],
) -> None:
    """Inscrit les échanges préalables dans la mémoire (mêmes mécanismes).

    L'ordre est chronologique (tick négatif croissant) pour un déterminisme
    total ; chaque échange laisse un **reçu** et un **épisode** sourcés.
    """
    for ex in sorted(exchanges, key=lambda e: e.tick):
        memory.learn(ex.fact, ex.source, ex.tick, ex.confidence)
        memory.log_episode(ex.tick, EpisodeKind.ENTENDU, ex.fact, ex.speaker)


#: Mots qui font d'un souvenir une **exclusion** (la sortie se bouche, ferme).
_BLOCKING = ("bouche", "bloqu", "ferm", "ferme", "pleine", "sature")


def seed_knowledge(agent: object, exchanges: Sequence[PrehistoryMessage]) -> int:
    """Inscrit les faits J−3 dans les **croyances** de l'agent (pas seulement
    dans ses reçus).

    Pourquoi c'est nécessaire : `seed_prehistory` écrit des reçus, que seul le
    prompt du grand modèle lit. Pour les règles — et donc pour la mission n°1 —
    un souvenir qui ne touche pas `knowledge` est décoratif. On ne crée jamais
    de croyance sur une sortie **inconnue** (garde C3 : la géographie ne
    s'apprend pas par ouï-dire) : un fait qui nomme une sortie inconnue reste
    un simple reçu.

    Rend le nombre de croyances écrites (mesure, pas décoration).
    """
    knowledge: Knowledge = agent.knowledge  # type: ignore[attr-defined]
    known: frozenset[str] = agent.known_exits  # type: ignore[attr-defined]
    written = 0
    for ex in sorted(exchanges, key=lambda e: e.tick):
        lowered = ex.fact.lower()
        blocking = any(word in lowered for word in _BLOCKING)
        labels = {
            token
            for token in re.findall(r"\b[A-Z](?:\d{1,2})?\b", ex.fact.upper())
            if not token.isdigit()
        }
        for label in sorted(labels & set(known)):
            if blocking:
                knowledge.set(
                    f"hazard:{label}",
                    Belief("sortie à éviter (souvenir)", ex.confidence, ex.source, ex.tick),
                )
            else:
                knowledge.set(
                    f"exit:{label}",
                    Belief(label, ex.confidence, ex.source, ex.tick),
                )
            written += 1
    return written


#: Les échanges destinés à un archétype (utilitaire de population).
def prehistory_for(archetype: str) -> tuple[PrehistoryMessage, ...]:
    return tuple(m for m in PREHISTORY_MAREE if m.target == archetype)


__all__ = [
    "J_1",
    "J_2",
    "J_3",
    "PREHISTORY_MAREE",
    "PrehistoryMessage",
    "prehistory_for",
    "seed_knowledge",
    "seed_prehistory",
]