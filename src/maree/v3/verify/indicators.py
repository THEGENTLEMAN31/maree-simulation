"""verify.indicators — I1..I7 portés de la v2, avec les leçons déjà payées.

Chaque indicateur est une fonction pure d'un état d'agents à un tick. Le
moteur les calcule **pendant** le run et publie ``indicator.crowd`` ; la
campagne les résume ensuite. Le même code sert donc au direct et au rejeu.

    I1  consensus        part des agents actifs qui partagent la croyance majoritaire
    I2  entropie         incertitude moyenne des croyances (normalisée 0..1)
    I3  évacués          part des agents sortis
    I4  temps            tick × 10 s — une horloge, pas une durée
    I5  densité max      noyau circulaire de 2 m (pers/m²) — le goulot
    I6  écart            part des agents croyant en une sortie réellement fermée
    I7  délai            premier signal de danger → dernier sorti (s)

Trois règles apprises en v2 et conservées ici :

- **I5 n'est pas une grille.** Une cellule de 1 m saturait à 2 agents et
  l'indicateur valait 2,0 partout ; le noyau de 2 m varie.
- **le dernier tick est dégénéré** (plus personne : I1/I2/I5/I6 = 0). La
  moyenne se fait sur la partie *active*, le pic pour I5/I6.
- **I4 et I7 ne mesurent pas la même chose.** I4 est l'horloge depuis t0
  (elle se fige au plafond `max_ticks` si une partie de la foule ne sort
  pas) ; I7 part du premier signal de danger du **monde** et reste défini
  sous censure.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from maree.v3.agents.agent import Agent
from maree.v3.agents.preference import preferred_from_beliefs
from maree.v3.world.worldspec import Point

#: durée d'un tick en secondes (cohérent avec la préhistoire J−3).
TICK_SECONDS = 10.0
#: rayon du noyau de densité (m) — même définition que la perception (C2).
DENSITY_RADIUS = 2.0

#: clés publiées, dans l'ordre du contrat de trame.
KEYS = (
    "I1_consensus",
    "I2_entropy",
    "I3_evacuated",
    "I4_seconds",
    "I5_max_density",
    "I6_belief_gap",
    "I7_delay_seconds",
)


@dataclass(frozen=True, slots=True)
class AgentState:
    """Vue minimale d'un agent, suffisante pour tous les indicateurs."""

    agent_id: str
    profile: str
    position: Point
    belief_best: str | None = None
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
    i7_delay_seconds: float = 0.0
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
            "I7_delay_seconds": round(self.i7_delay_seconds, 1),
            "counts": self.counts,
        }


# ---------------------------------------------------------------------------
# briques pures
# ---------------------------------------------------------------------------
def consensus(beliefs: Iterable[str | None]) -> float:
    """I1 — part de la croyance majoritaire parmi les agents qui croient."""
    known = [b for b in beliefs if b is not None]
    if not known:
        return 0.0
    return Counter(known).most_common(1)[0][1] / len(known)


def mean_entropy(entropies: Iterable[float], n_exits: int) -> float:
    """I2 — entropie moyenne normalisée : 0 = tous sûrs, 1 = tous perdus."""
    values = list(entropies)
    if not values:
        return 0.0
    ceiling = math.log2(n_exits) if n_exits > 1 else 1.0
    return min(1.0, (sum(values) / len(values)) / ceiling)


def belief_entropy(agent: Agent, n_exits: int) -> float:
    """Entropie (bits) des croyances de sortie, hors sorties crues bloquées.

    Aucune croyance = incertitude maximale ``log2(n_exits)`` : ne rien savoir
    n'est pas être certain. Une seule sortie = 0 bit.
    """
    confidences: list[float] = []
    for key, belief in agent.knowledge.beliefs.items():
        if not key.startswith("exit:"):
            continue
        label = key[len("exit:"):]
        hazard = agent.knowledge.beliefs.get(f"hazard:{label}")
        if hazard is not None and hazard.confidence >= 0.5:
            continue
        confidences.append(max(0.0, belief.confidence))
    total = sum(confidences)
    ceiling = math.log2(n_exits) if n_exits > 1 else 1.0
    if total <= 0.0 or len(confidences) <= 1:
        return 0.0 if total > 0.0 else ceiling
    return -sum((c / total) * math.log2(c / total) for c in confidences)


def max_density(
    states: Iterable[AgentState], radius: float = DENSITY_RADIUS
) -> float:
    """I5 — densité locale max, noyau circulaire de ``radius`` mètres."""
    points = [s.position for s in states if not s.evacuated]
    if len(points) < 2:
        return 0.0
    area = math.pi * radius * radius
    radius_sq = radius * radius
    best = 0.0
    for i, (x, y) in enumerate(points):
        neighbours = 0
        for j, (u, v) in enumerate(points):
            if i == j:
                continue
            if (u - x) ** 2 + (v - y) ** 2 <= radius_sq:
                neighbours += 1
        best = max(best, neighbours / area)
    return best


def belief_gap(states: Iterable[AgentState], open_exits: set[str]) -> float:
    """I6 — part des agents actifs croyant en une sortie réellement fermée.

    Sans fermeture dans le scénario, I6 vaut 0 **par construction** : ne pas
    le déclarer comme un résultat.
    """
    considered = [
        s for s in states if not s.evacuated and s.belief_best is not None
    ]
    if not considered:
        return 0.0
    trapped = sum(1 for s in considered if s.belief_best not in open_exits)
    return trapped / len(considered)


def from_agents(
    pairs: Iterable[tuple[Agent, Point, bool]],
    *,
    n_exits: int,
) -> list[AgentState]:
    """Adaptateur ``v3.Agent → AgentState`` (position et sortie = faits)."""
    states: list[AgentState] = []
    for agent, position, evacuated in pairs:
        best = preferred_from_beliefs(agent.knowledge.beliefs)
        confidence = (
            0.0
            if best is None
            else agent.knowledge.beliefs[f"exit:{best}"].confidence
        )
        states.append(
            AgentState(
                agent_id=agent.name,
                profile=agent.archetype,
                position=position,
                belief_best=best,
                belief_confidence=confidence,
                belief_entropy=belief_entropy(agent, n_exits),
                evacuated=evacuated,
            )
        )
    return states


def compute(
    states: Sequence[AgentState],
    *,
    n_exits: int,
    open_exits: set[str],
    tick: int,
    signal_tick: int | None = None,
    last_exit_tick: int | None = None,
) -> Indicators:
    active = [s for s in states if not s.evacuated]
    by_belief: dict[str, int] = {}
    for s in active:
        key = s.belief_best or "aucune"
        by_belief[key] = by_belief.get(key, 0) + 1
    delay = 0.0
    if signal_tick is not None and last_exit_tick is not None:
        delay = max(0.0, (last_exit_tick - signal_tick) * TICK_SECONDS)
    return Indicators(
        tick=tick,
        i1_consensus=consensus(s.belief_best for s in active),
        i2_entropy=mean_entropy((s.belief_entropy for s in active), n_exits),
        i3_evacuated=(
            len(states) - len(active)
        ) / len(states) if states else 0.0,
        i4_seconds=tick * TICK_SECONDS,
        i5_max_density=max_density(active),
        i6_belief_gap=belief_gap(states, open_exits),
        i7_delay_seconds=delay,
        counts={
            "agents": len(states),
            "evacuated": len(states) - len(active),
            "remaining": len(active),
            "by_belief": by_belief,
        },
    )


def summarise(series: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Résume une série d'indicateurs pour comparer deux bras.

    Le dernier tick est **dégénéré** : quand tout le monde est sorti, I1, I2,
    I5 et I6 valent 0 par construction. On garde donc :

        I3, I4   au dernier tick (évacuation finale, temps écoulé)
        I5, I6   au pic (le pire moment — c'est le piège qu'on étudie)
        I1, I2   en moyenne temporelle sur la partie **active** du run
        I7       au dernier tick (délai signal de danger → dernier sorti)

    Le tick dégénéré est exclu de la moyenne : sinon un run de 19 ticks
    compte un zéro sur 19 et un run de 55 ticks un zéro sur 55.
    """
    if not series:
        return {key: 0.0 for key in KEYS}

    def values(key: str) -> list[float]:
        return [float(sample.get(key, 0.0) or 0.0) for sample in series]

    def active(key: str) -> list[float]:
        kept = [
            float(s.get(key, 0.0) or 0.0)
            for s in series
            if float(s.get("I3_evacuated", 0.0) or 0.0) < 1.0
        ]
        return kept or values(key)

    last = series[-1]
    i1, i2 = active("I1_consensus"), active("I2_entropy")
    return {
        "I1_consensus": sum(i1) / len(i1),
        "I2_entropy": sum(i2) / len(i2),
        "I3_evacuated": float(last.get("I3_evacuated", 0.0) or 0.0),
        "I4_seconds": float(last.get("I4_seconds", 0.0) or 0.0),
        "I5_max_density": max(values("I5_max_density")),
        "I6_belief_gap": max(values("I6_belief_gap")),
        "I7_delay_seconds": float(last.get("I7_delay_seconds", 0.0) or 0.0),
    }


__all__ = [
    "DENSITY_RADIUS",
    "KEYS",
    "TICK_SECONDS",
    "AgentState",
    "Indicators",
    "belief_entropy",
    "belief_gap",
    "compute",
    "consensus",
    "from_agents",
    "max_density",
    "mean_entropy",
    "summarise",
]
