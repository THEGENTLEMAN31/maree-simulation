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
    # I4 : une observation par décision — l'agent a-t-il choisi la sortie
    # majoritaire parmi ses voisins visibles ? (mesuré, pas déduit)
    follow_observations: list[bool] = field(default_factory=list)
    temporal_violations: int = 0
    # F6 / décision 16 : plage d'offsets Kafka par topic, et identifiants
    # des événements qui ont produit cette valeur. `sources` reste un dict
    # sérialisable JSON : {topic: {partition, from, to, events}}.
    source_offsets: dict[str, dict] = field(default_factory=dict)
    source_event_ids: list[str] = field(default_factory=list)

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

        # I4 — Suivi de meneur : part des décisions où l'agent a choisi la
        # sortie majoritaire parmi ses voisins visibles au moment de décider.
        # Sans observation (aucun voisin), l'indicateur vaut 0 et non 1 : on
        # ne prétend pas mesurer un suivi qui n'a pas eu lieu.
        if state.follow_observations:
            i4 = sum(state.follow_observations) / len(state.follow_observations)
        else:
            i4 = 0.0

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
            "source_events": state.source_event_ids,
        }