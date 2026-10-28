"""Digest du monde — ce que le chroniqueur a sous les yeux.

Le narrateur est omniscient, mais il ne reçoit pas 60 agents bruts : il
reçoit un résumé compact et **vérifiable**. C'est ce qui permet de
contrôler qu'il n'invente rien (voir `validate`).

Le digest est aussi la preuve de ce que le narrateur savait : son empreinte
est journalisée avec le texte produit.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from maree.domain.ids import ExitId
from maree.metrics.indicators import AgentState, Indicators


@dataclass(frozen=True, slots=True)
class WorldDigest:
    tick: int
    sim_time: str
    total: int
    evacuated: int
    remaining: int
    density_max: float
    open_exits: tuple[ExitId, ...]
    closed_exits: tuple[ExitId, ...]
    belief_shares: dict[str, float]
    unknown_share: float
    consensus: float
    recent_events: tuple[str, ...]

    # ---- rendu pour le modèle ---------------------------------
    def to_prompt(self) -> str:
        shares = ", ".join(
            f"sortie {k} {v:.0%}" for k, v in sorted(self.belief_shares.items())
        ) or "aucune croyance"
        return "\n".join(
            [
                f"Instant : {self.sim_time} (tick {self.tick}).",
                f"Évacués : {self.evacuated} sur {self.total} "
                f"({self.remaining} encore sur l'esplanade).",
                f"Densité maximale : {self.density_max:.1f} personnes par mètre carré.",
                f"Sorties ouvertes : {', '.join(self.open_exits) or 'aucune'}.",
                f"Sorties fermées : {', '.join(self.closed_exits) or 'aucune'}.",
                f"Croyances : {shares} ; sans croyance {self.unknown_share:.0%}.",
                f"Accord de la foule : {self.consensus:.0%}.",
                "Faits récents : "
                + (" | ".join(self.recent_events) if self.recent_events else "aucun"),
            ]
        )

    def digest_hash(self) -> str:
        payload = json.dumps(self.to_prompt(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def allowed_numbers(self) -> set[str]:
        """Nombres que le narrateur a le droit de citer."""
        hours, _, minutes = self.sim_time.partition(":")
        return {
            str(self.tick),
            str(self.total),
            str(self.evacuated),
            str(self.remaining),
            f"{self.density_max:.0f}",
            f"{self.density_max:.1f}",
            f"{self.consensus * 100:.0f}",
            f"{self.unknown_share * 100:.0f}",
            hours,
            str(int(minutes or 0)),
            *[f"{v * 100:.0f}" for v in self.belief_shares.values()],
        }


def build_digest(
    *,
    indicators: Indicators,
    agents: list[AgentState],
    open_exits: set[ExitId],
    all_exits: tuple[ExitId, ...],
    sim_time: str,
    recent_events: tuple[str, ...],
) -> WorldDigest:
    active = [a for a in agents if not a.evacuated]
    known = [a for a in active if a.belief_best is not None]
    shares: dict[str, float] = {}
    if known:
        for a in known:
            shares[a.belief_best] = shares.get(a.belief_best, 0.0) + 1.0  # type: ignore[index]
        shares = {k: v / len(active) for k, v in shares.items()}
    unknown = (len(active) - len(known)) / len(active) if active else 0.0
    return WorldDigest(
        tick=indicators.tick,
        sim_time=sim_time,
        total=len(agents),
        evacuated=indicators.counts.get("evacuated", 0),
        remaining=indicators.counts.get("remaining", 0),
        density_max=indicators.i5_max_density,
        open_exits=tuple(sorted(open_exits)),
        closed_exits=tuple(sorted(set(all_exits) - open_exits)),
        belief_shares=shares,
        unknown_share=unknown,
        consensus=indicators.i1_consensus,
        recent_events=recent_events,
    )
