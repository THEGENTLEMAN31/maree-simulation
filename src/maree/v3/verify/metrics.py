"""verify.metrics — métriques de divergence entre cohortes de jumeaux.

Mesure principale exigée par la mission 1 : la **divergence de KL** entre
les distributions de choix de sortie de deux cohortes, et des métriques
auxiliaires (accord, délai de première décision). Tout est déterministe et
testé — on ne publie un chiffre que s'il est reproductible.
"""

from __future__ import annotations

from collections import Counter
from math import log


def _smooth(distribution: dict[str, float], categories: tuple[str, ...]) -> dict[str, float]:
    """Assure une masse strictement positive sur toutes les catégories connues."""
    smoothed = {cat: distribution.get(cat, 0.0) + 1e-9 for cat in categories}
    total = sum(smoothed.values())
    return {cat: mass / total for cat, mass in smoothed.items()}


def kl_divergence(p: dict[str, float], q: dict[str, float]) -> float:
    """KL(P || Q) entre deux distributions sur un même univers de catégories."""
    categories = tuple(sorted(set(p) | set(q)))
    if not categories:
        return 0.0
    sp = _smooth(p, categories)
    sq = _smooth(q, categories)
    return sum(sp[cat] * log(sp[cat] / sq[cat]) for cat in categories)


def exit_distribution(exits: list[str | None], categories: tuple[str, ...]) -> dict[str, float]:
    """Distribution empirique des sorties choisies (ou ``*`` si aucune)."""
    counted: list[str] = [e if e is not None else "*" for e in exits]
    counter = Counter(counted)
    total = len(counted)
    if total == 0:
        return {}
    return {cat: counter.get(cat, 0) / total for cat in categories}


def agreement_ratio(left_exits: list[str | None], right_exits: list[str | None]) -> float:
    """Part des paires de jumeaux qui prennent la *même* sortie (0..1)."""
    pairs = list(zip(left_exits, right_exits, strict=True))
    if not pairs:
        return 0.0
    same = sum(1 for a, b in pairs if a == b)
    return same / len(pairs)


def first_decision_delay(first_moves: list[int | None]) -> dict[str, float]:
    """Distribution des ticks de première décision de mouvement.

    Les agents qui n'ont jamais bougé sont exclus (la distribution porte sur
    ceux qui se sont décidés) ; ``count`` signale le dénominateur.
    """
    moves = [t for t in first_moves if t is not None]
    if not moves:
        return {"count": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
    values = sorted(moves)
    mean = sum(values) / len(values)
    return {
        "count": float(len(values)),
        "mean": mean,
        "min": float(values[0]),
        "max": float(values[-1]),
    }


def divergence_report(
    left_exits: list[str | None],
    right_exits: list[str | None],
    categories: tuple[str, ...],
    *,
    left_first_moves: list[int | None] | None = None,
    right_first_moves: list[int | None] | None = None,
) -> dict[str, object]:
    """Assemble les métriques d'un run d'expérience des jumeaux."""
    p = exit_distribution(left_exits, categories)
    q = exit_distribution(right_exits, categories)
    return {
        "categories": list(categories),
        "left_distribution": p,
        "right_distribution": q,
        "kl_divergence": kl_divergence(p, q),
        "agreement_ratio": agreement_ratio(left_exits, right_exits),
        "n_pairs": len(list(zip(left_exits, right_exits, strict=True))),
        "left_first_delay": (
            first_decision_delay(left_first_moves) if left_first_moves else {}
        ),
        "right_first_delay": (
            first_decision_delay(right_first_moves) if right_first_moves else {}
        ),
    }


__all__ = [
    "agreement_ratio",
    "divergence_report",
    "exit_distribution",
    "first_decision_delay",
    "kl_divergence",
]