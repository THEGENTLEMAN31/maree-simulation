"""verify.emergence — indicateurs d'émergence du contexte commun (B1–B3).

« Contexte commun » de MARÉE, défini en termes observables : la population
s'accorde sur laquelle des sorties est sûre, et cet accord s'est construit
par **ouï-dire** — un message a *changé* la préférence, il ne l'a pas
seulement confirmée.

- ``consensus`` : 1 − entropie normalisée des sorties préférées (0..1) ;
- ``couplage`` : part d'agents dont la sortie préférée a **changé** après un
  ouï-dire (B2). « La croyance vient d'un ENTENDU » ne suffit pas : un
  message qui confirme la sortie déjà préférée est de la diffusion, pas une
  construction sociale ;
- ``emergence_flag`` : consensus ≥ τC ET couplage ≥ τK ;
- ``social_excess`` : l'excès au-dessus du null des **mémoires brouillées**
  (les croyances personnelles sont permutées entre agents) : la ressemblance
  du modèle est le null, pas une émergence. ``E_social = consensus_observé −
  consensus_null``.

Le consensus se lit sur les agents **actifs** (non sortis) : inclure les
sortis ferait valoir 1,0 à un run où tout le monde a quitté le champ.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from typing import Any, cast

from maree.v3.agents.agent import Agent
from maree.v3.agents.knowledge import Belief, Source
from maree.v3.agents.preference import preferred_exit, preferred_from_beliefs

#: seuils par défaut (à calibrer sur pilote, cf. docs).
TAU_C = 0.7
TAU_K = 0.4


def _agreement(chosen: list[str]) -> float:
    """1 − entropie normalisée d'une distribution de choix (0..1)."""
    if not chosen:
        return 0.0
    counts = Counter(chosen)
    if len(counts) <= 1:
        return 1.0
    total = len(chosen)
    entropy = -sum(
        (c / total) * math.log2(c / total) for c in counts.values()
    )
    return 1.0 - entropy / math.log2(len(counts))


def consensus(agents: list[Agent]) -> tuple[float, dict[str, float]]:
    """Accord : 1 − entropie normalisée des sorties préférées."""
    chosen = [preferred_exit(a) or "aucune" for a in agents]
    counts = Counter(chosen)
    total = len(chosen)
    dist = {k: c / total for k, c in counts.items()}
    return _agreement(chosen), dist


def couplage(agents: list[Agent]) -> float:
    """Part d'agents dont la préférence a **changé** après un ouï-dire."""
    if not agents:
        return 0.0
    coupled = sum(1 for a in agents if a.preference_changed_by_hearsay)
    return coupled / len(agents)


def consensus_without_hearsay(agents: list[Agent]) -> float:
    """Le null : le même monde **sans ce qui a été appris des autres**.

    On ne permute pas les mémoires — une permutation laisserait la
    distribution des préférences identique (le choix ne dépend que du
    contenu), donc un null toujours égal à l'observé. On retire les
    croyances de source ``ENTENDU`` et ``ANNONCE`` : c'est le contre-factuel
    « la rumeur n'a pas circulé ». Si l'accord survit, il ne venait pas de
    la communication.
    """
    kept: list[Mapping[str, Belief]] = [
        {
            key: belief
            for key, belief in a.knowledge.beliefs.items()
            if belief.source not in (Source.ENTENDU, Source.ANNONCE)
        }
        for a in agents
    ]
    if not kept:
        return 0.0
    chosen = [preferred_from_beliefs(mem) or "aucune" for mem in kept]
    return _agreement(chosen)


def emergence_report(agents: list[Agent], seed: int = 0) -> dict[str, object]:
    """Rapport d'émergence d'un instant (agents **actifs** seulement).

    ``seed`` reste accepté pour la signature des campagnes : le null n'en a
    plus besoin (il n'est pas aléatoire).
    """
    del seed
    c, dist = consensus(agents)
    k = couplage(agents)
    null = consensus_without_hearsay(agents)
    flag = c >= TAU_C and k >= TAU_K
    return {
        "consensus": round(c, 3),
        "couplage": round(k, 3),
        "emergence": flag,
        "social_excess": round(c - null, 3),
        "null_consensus": round(null, 3),
        "distribution": {str(x): round(p, 3) for x, p in dist.items()},
    }


def active_agents(sim: Any) -> list[Agent]:
    """Les agents **encore dans le champ** (les sortis ne votent plus).

    Inclure les sortis faisait valoir 1,0 à un run où tout le monde avait
    quitté la scène : le consensus mesurait alors une absence, pas un accord.
    """
    evacuated: set[int] = getattr(sim, "_evacuated", set())
    return [
        inst.agent
        for agent_id, inst in sim.scene.instances.items()
        if agent_id.uid not in evacuated
    ]


def social_excess(observed_consensus: float, null_consensus: float) -> float:
    """E_social = l'accord dans le monde − l'accord du même monde aux
    mémoires brouillées (le null). ≈ 0 ⇒ le « consensus » n'était qu'un
    artefact du modèle, pas une émergence construite."""
    return observed_consensus - null_consensus


def e_social(observed_report: dict[str, object], null_report: dict[str, object]) -> float:
    """E_social entre un monde et son contre-factuel (le null).

    ``observed_report`` = émergence du monde réel ; ``null_report`` = émergence
    du même monde aux mémoires personnelles brouillées (ou communication coupée).
    """
    return social_excess(
        float(cast("float", observed_report["consensus"])),
        float(cast("float", null_report["consensus"])),
    )


__all__ = [
    "TAU_C",
    "TAU_K",
    "active_agents",
    "consensus",
    "consensus_without_hearsay",
    "couplage",
    "e_social",
    "emergence_report",
    "preferred_exit",
    "social_excess",
]
