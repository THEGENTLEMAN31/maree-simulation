"""Indicateurs I1–I5 (B2, B3 ; exigences C6, C7, F6).

Chaque valeur d'indicateur publiée référence la plage d'offsets Kafka des
événements qui l'ont produite (décision 16, F6).
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field


@dataclass
class IndicatorSet:
    """Vue agrégée de l'état pour le calcul des indicateurs."""

    tick: int
    # (agent_id, croyance sortie sûre, au courant du danger ?)
    beliefs: list[tuple[str, str | None, bool]] = field(default_factory=list)
    evacuated: int = 0
    trapped: int = 0
    total: int = 0
    ground_truth_safe_exit: str = "A"
    # (agent_id, destination) pour le suivi de meneur
    destinations: list[tuple[str, str]] = field(default_factory=list)
    temporal_violations: int = 0
    source_offsets: dict[str, int] = field(default_factory=dict)

    @property
    def informed(self) -> list[tuple[str, str | None, bool]]:
        return [b for b in self.beliefs if b[1] is not None]


class Indicators:
    """Calcule I1–I5 à partir d'une vue agrégée (déterministe)."""

    def compute(self, state: IndicatorSet) -> dict:
        informed = state.informed
        n = state.total or 1

        # I1 — Consensus sur la sortie sûre (part majoritaire + entropie).
        counts: dict[str, int] = {}
        for _, code, _ in informed:
            counts[code] = counts.get(code, 0) + 1
        if counts:
            total_informed = sum(counts.values())
            major = max(counts.values()) / total_informed
            entropy = -sum(
                (c / total_informed) * math.log2(c / total_informed) for c in counts.values()
            )
            i1 = major * (1 - entropy / math.log2(max(2, len(counts))))
        else:
            i1 = 0.0

        # I2 — Écart croyance/réalité : part des agents informés dont la
        # croyance de sortie sûre diffère de la vérité terrain.
        wrong = sum(
            1 for _, code, _ in informed if code != state.ground_truth_safe_exit
        )
        i2 = wrong / max(1, len(informed))

        # I3 — Évacuation (résultat physique).
        i3 = {
            "evacuated": state.evacuated,
            "trapped": state.trapped,
            "remaining": n - state.evacuated - state.trapped,
        }

        # I4 — Suivi de meneur : part des agents dont la destination est celle
        # d'un agent vu dans les 10 dernières secondes (approximé ici par la
        # sortie majoritaire parmi les destinations).
        dest_counts: dict[str, int] = {}
        for _, dst in state.destinations:
            dest_counts[dst] = dest_counts.get(dst, 0) + 1
        i4 = (max(dest_counts.values()) / max(1, state.evacuated)) if dest_counts else 0.0

        # I5 — Cohérence temporelle (attendu : zéro).
        i5 = state.temporal_violations

        return {
            "tick": state.tick,
            "I1_consensus": round(i1, 4),
            "I2_belief_gap": round(i2, 4),
            "I3_evacuation": i3,
            "I4_leader_follow": round(i4, 4),
            "I5_temporal_violations": i5,
            "sources": state.source_offsets,
        }