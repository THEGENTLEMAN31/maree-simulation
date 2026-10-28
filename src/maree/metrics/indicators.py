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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

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
    counts: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
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


def density_cells(points: Iterable[Point], cell: float = 1.0) -> list[dict[str, float]]:
    """Grille de densité, telle que le client la dessine.

    Chaque cellule occupée est donnée par son **origine** en mètres et son
    effectif. Le client n'a donc aucune grille à recalculer : il divise par
    `cell²` s'il veut des personnes au mètre carré, ou colore directement
    selon `n`. Les cellules vides ne sont pas transmises.
    """
    grid: Counter[tuple[int, int]] = Counter()
    for p in points:
        grid[(int(p[0] // cell), int(p[1] // cell))] += 1
    return [
        {"x": gx * cell, "y": gy * cell, "n": n}
        for (gx, gy), n in sorted(grid.items())
    ]


def max_density(agents: Iterable[AgentState], cell: float = 1.0) -> float:
    """I5 — densité locale max sur une grille de `cell` mètres.

    C'est la mesure du goulot : elle ne dit pas « il y a du monde », elle
    dit « à cet endroit précis, on est à 4,2 personnes au mètre carré ».
    """
    cells = density_cells((a.position for a in agents if not a.evacuated), cell)
    if not cells:
        return 0.0
    return max(c["n"] for c in cells) / (cell * cell)


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
    # Répartition des croyances : ce que le client dessine en barres
    # empilées. « aucune » est explicite — un agent qui ne sait rien n'est
    # pas un agent qui croit à une sortie de plus.
    by_belief: dict[str, int] = {str(e): 0 for e in plan.exits}
    by_belief["aucune"] = 0
    for a in active:
        key = str(a.belief_best) if a.belief_best is not None else "aucune"
        by_belief[key] = by_belief.get(key, 0) + 1
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
            "by_belief": by_belief,
        },
    )


def summarise(series: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Résume une série d'indicateurs pour comparer deux bras.

    Le dernier tick est **dégénéré** : quand tout le monde est sorti, I1,
    I2, I5 et I6 valent 0 par construction (il n'y a plus d'agent actif).
    Prendre `series[-1]` comme résultat d'expérience ne mesurerait donc
    rien. On garde :

        I3, I4   au dernier tick (évacuation finale, durée)
        I5, I6   au pic (le pire moment — c'est le piège qu'on étudie)
        I1, I2   en moyenne temporelle (état moyen de la croyance)
    """
    if not series:
        return {
            "I1_consensus": 0.0,
            "I2_entropy": 0.0,
            "I3_evacuated": 0.0,
            "I4_seconds": 0.0,
            "I5_max_density": 0.0,
            "I6_belief_gap": 0.0,
        }

    def values(key: str) -> list[float]:
        return [float(sample.get(key, 0.0) or 0.0) for sample in series]

    last = series[-1]
    i1, i2 = values("I1_consensus"), values("I2_entropy")
    return {
        "I1_consensus": sum(i1) / len(i1),
        "I2_entropy": sum(i2) / len(i2),
        "I3_evacuated": float(last.get("I3_evacuated", 0.0) or 0.0),
        "I4_seconds": float(last.get("I4_seconds", 0.0) or 0.0),
        "I5_max_density": max(values("I5_max_density")),
        "I6_belief_gap": max(values("I6_belief_gap")),
    }
