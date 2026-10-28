"""Indicateurs I1..I6.

Chaque indicateur est une fonction pure d'un état d'agents + du plan.
Aucun ne lit le journal : c'est le rôle de `engine/replay.py` de fournir
l'état. Ainsi, le même code sert au direct et au rejeu (décision 16).

    I1  consensus        part des agents qui partagent la croyance majoritaire
    I2  entropie         incertitude moyenne des croyances (normalisée 0..1)
    I3  évacués          part des agents sortis
    I4  temps            durée d'évacuation observée (s)
    I5  densité max      densité locale maximale (pers/m²) — le goulot
    I6  écart            part des agents croyant en une sortie fermée
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from maree.domain.geometry import Plan
from maree.domain.ids import AgentId, ExitId, Point


@dataclass(frozen=True, slots=True)
class AgentState:
    """Vue minimale d'un agent, suffisante pour tous les indicateurs."""

    agent_id: AgentId
    profile: str
    position: Point
    belief_best: ExitId | None = None
    belief_confidence: float = 0.0
    belief_entropy: float = 0.0
    evacuated: bool = False


@dataclass(frozen=True, slots=True)
class Indicators:
    tick: int
    i1_consensus: float
    i2_entropy: float
    i3_evacuated: float
    i4_seconds: float
    i5_max_density: float
    i6_belief_gap: float
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, float | int | dict[str, int]]:
        return {
            "tick": self.tick,
            "I1_consensus": round(self.i1_consensus, 4),
            "I2_entropy": round(self.i2_entropy, 4),
            "I3_evacuated": round(self.i3_evacuated, 4),
            "I4_seconds": round(self.i4_seconds, 1),
            "I5_max_density": round(self.i5_max_density, 3),
            "I6_belief_gap": round(self.i6_belief_gap, 4),
            "counts": self.counts,
        }


def consensus(beliefs: Iterable[ExitId | None]) -> float:
    """I1 — part de la croyance majoritaire parmi les agents qui croient.

    Répond littéralement à la question du sujet : « comment mesurer qu'une
    foule s'accorde sans que personne ne l'ait décidé ? »
    """
    known = [b for b in beliefs if b is not None]
    if not known:
        return 0.0
    counts = Counter(known)
    return counts.most_common(1)[0][1] / len(known)


def mean_entropy(entropies: Iterable[float], n_exits: int) -> float:
    """I2 — entropie moyenne normalisée : 0 = tous sûrs, 1 = tous perdus."""
    values = list(entropies)
    if not values:
        return 0.0
    ceiling = math.log(n_exits) if n_exits > 1 else 1.0
    return min(1.0, (sum(values) / len(values)) / ceiling)


def max_density(agents: Iterable[AgentState], cell: float = 1.0) -> float:
    """I5 — densité locale max sur une grille de `cell` mètres.

    C'est la mesure du goulot : elle ne dit pas « il y a du monde », elle
    dit « à cet endroit précis, on est à 4,2 personnes au mètre carré ».
    """
    grid: Counter[tuple[int, int]] = Counter()
    for a in agents:
        if a.evacuated:
            continue
        grid[(int(a.position[0] // cell), int(a.position[1] // cell))] += 1
    if not grid:
        return 0.0
    return max(grid.values()) / (cell * cell)


def belief_gap(agents: Iterable[AgentState], open_exits: set[ExitId]) -> float:
    """I6 — part des agents qui croient en une sortie réellement fermée.

    La croyance partagée qui sauve à t10 et piège à t40 : c'est ce nombre.
    """
    considered = [a for a in agents if not a.evacuated and a.belief_best is not None]
    if not considered:
        return 0.0
    trapped = sum(1 for a in considered if a.belief_best not in open_exits)
    return trapped / len(considered)


def compute(
    agents: list[AgentState],
    plan: Plan,
    open_exits: set[ExitId],
    tick: int,
    elapsed_s: float,
) -> Indicators:
    n_exits = len(plan.exits)
    active = [a for a in agents if not a.evacuated]
    return Indicators(
        tick=tick,
        i1_consensus=consensus(a.belief_best for a in active),
        i2_entropy=mean_entropy((a.belief_entropy for a in active), n_exits),
        i3_evacuated=(len(agents) - len(active)) / len(agents) if agents else 0.0,
        i4_seconds=elapsed_s,
        i5_max_density=max_density(active),
        i6_belief_gap=belief_gap(agents, open_exits),
        counts={
            "agents": len(agents),
            "evacuated": len(agents) - len(active),
            "remaining": len(active),
        },
    )
