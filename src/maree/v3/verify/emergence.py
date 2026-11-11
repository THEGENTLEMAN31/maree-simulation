"""verify.emergence — indicateurs d'émergence du contexte commun (B1–B3).

« Contexte commun » de MARÉE, défini en termes observables : la population
s'accorde sur laquelle des sorties est sûre, et cet accord s'est construit
par **ouï-dire** (reçus ENTENDU), pas imposé par une annonce ni par la
ressemblance du même modèle.

- ``consensus`` : 1 − entropie normalisée des sorties préférées (0..1) ;
- ``couplage`` : part d'agents dont la sortie préférée est renforcée par un
  reçu ENTENDU — c'est ce qui distingue *émergence construite* de *diffusion* ;
- ``emergence_flag`` : consensus ≥ τC ET couplage ≥ τK ;
- ``social_excess`` : l'excès au-dessus du null (⇔ la ressemblance du modèle
  est le null) : ``E_social = consensus_observé − consensus_null``.
"""

from __future__ import annotations

import math
from collections import Counter

from maree.v3.agents.agent import Agent
from maree.v3.agents.knowledge import Source

#: seuils par défaut (à calibrer sur pilote, cf. docs).
TAU_C = 0.7
TAU_K = 0.4


def preferred_exit(agent: Agent) -> str | None:
    """La sortie que l'agent préfère : la plus confiante, non croyue bloquée."""
    best: tuple[float, str] | None = None
    for key, belief in agent.knowledge.beliefs.items():
        if not key.startswith("exit:"):
            continue
        label = key[len("exit:"):]
        hazard = agent.knowledge.beliefs.get(f"hazard:{label}")
        if hazard is not None and hazard.confidence >= 0.5:
            continue
        if best is None or belief.confidence > best[0]:
            best = (belief.confidence, label)
    return best[1] if best else None


def consensus(agents: list[Agent]) -> tuple[float, dict[str, float]]:
    """Accord : 1 − entropie normalisée des sorties préférées."""
    chosen = [preferred_exit(a) or "aucune" for a in agents]
    counts = Counter(chosen)
    total = len(chosen)
    dist = {k: c / total for k, c in counts.items()}
    if total == 0 or len(dist) <= 1:
        return 0.0 if not dist else 1.0, dist
    entropy = -sum(p * math.log2(p) for p in dist.values())
    norm = entropy / math.log2(len(dist))
    return 1.0 - norm, dist


def couplage(agents: list[Agent]) -> float:
    """Part d'agents dont la sortie préférée est renforcée par ouï-dire."""
    coupled = 0
    for a in agents:
        label = preferred_exit(a)
        if label is None:
            continue
        belief = a.knowledge.beliefs.get(f"exit:{label}")
        if belief is not None and belief.source is Source.ENTENDU:
            coupled += 1
    return coupled / len(agents) if agents else 0.0


def emergence_report(agents: list[Agent]) -> dict[str, object]:
    c, dist = consensus(agents)
    k = couplage(agents)
    flag = c >= TAU_C and k >= TAU_K
    return {
        "consensus": round(c, 3),
        "couplage": round(k, 3),
        "emergence": flag,
        "distribution": {str(x): round(p, 3) for x, p in dist.items()},
    }


def social_excess(observed_consensus: float, null_consensus: float) -> float:
    """E_social = l'accord dans le monde − l'accord du même monde aux
    mémoires brouillées (le null). ≈ 0 ⇒ le « consensus » n'était qu'un
    artefact du modèle, pas une émergence construite."""
    return observed_consensus - null_consensus


__all__ = [
    "TAU_C",
    "TAU_K",
    "consensus",
    "couplage",
    "emergence_report",
    "preferred_exit",
    "social_excess",
]