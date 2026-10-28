"""Agents à règles — le bras de comparaison X4.

Volontairement simples, volontairement déterministes : ils ne constituent
pas une foule réaliste, ils constituent une **référence**. Toute
différence mesurée entre ce bras et le bras LLM est imputable à la
cognition, pas au hasard (leur variance est nulle par construction, ce
qui est un argument, pas une faiblesse).

Règle : parmi les sorties connues du profil et ouvertes, minimiser

    distance + 6 × densité_locale + 12 × (sortie saturée ?)

avec un biais de profil (le vendeur protège son stand, le parent cherche
son proche, l'agent de sécurité guide).
"""

from __future__ import annotations

import math

from maree.agents.profiles import get_profile
from maree.agents.triggers import Percept
from maree.domain.geometry import Plan
from maree.domain.ids import ExitId
from maree.domain.intentions import Intention, IntentionKind

#: Au-delà, on considère la sortie saturée.
SATURATION = 2.5


def _known_open(plan: Plan, profile_id: str, percept: Percept) -> list[ExitId]:
    profile = get_profile(profile_id)
    return [
        e for e in plan.exits if e in percept.exits_open and profile.knows(e)
    ]


def rules_decide(percept: Percept, plan: Plan, *, profile: str) -> Intention:
    tick = percept.tick

    # 1. Un proche a disparu : on le cherche avant de fuir.
    if percept.missing_kin and profile in {"famille"}:
        return Intention(
            IntentionKind.SEARCH,
            target=None,
            reason="proche non retrouvé, recherche prioritaire",
            tick=tick,
            confidence=0.9,
        )

    # 2. Sans signal de danger, on ne fuit pas. Une foule ne s'évacue pas
    #    parce qu'elle est arrivée : il faut la fumée, une annonce, un
    #    voisin qui parle, ou un proche manquant. C'est ce qui donne au
    #    scénario sa phase « avant » — et ce qui rend la fumée de t10
    #    causale au lieu d'être décorative.
    danger = (
        percept.smoke_visible
        or bool(percept.announcement)
        or bool(percept.messages)
        or percept.missing_kin
    )
    if not danger:
        return Intention(
            IntentionKind.STAY,
            target=None,
            reason="aucun signal de danger, je reste où je suis",
            tick=tick,
            confidence=0.6,
        )

    candidates = _known_open(plan, profile, percept)
    if not candidates:
        return Intention(
            IntentionKind.STAY,
            target=None,
            reason="aucune sortie connue n'est ouverte",
            tick=tick,
            confidence=0.4,
        )

    def cost(exit_id: ExitId) -> tuple[float, str]:
        ex = plan.exit(exit_id)
        dist = math.dist(percept.position, ex.center)
        # Une sortie étroite évacue moins vite : pénalité en 1/largeur.
        narrow = 1.0 / max(ex.width, 0.5)
        # La densité DEVANT la sortie, pas celle de l'agent : c'est elle
        # qui distingue deux issues également distantes.
        density = percept.exit_density.get(exit_id, 0.0)
        saturated = density >= SATURATION
        total = dist + 6.0 * density + 12.0 * (1.0 if saturated else 0.0) + 4.0 * narrow
        return (total, exit_id)

    best = min(candidates, key=cost)

    # 3. L'agent de sécurité guide au lieu de fuir seul.
    if profile == "securite" and percept.nearby:
        return Intention(
            IntentionKind.GUIDE,
            target=best,
            reason=f"orienter vers {best}, la sortie la mieux dégagée",
            tick=tick,
            confidence=0.85,
        )

    return Intention(
        IntentionKind.GO_EXIT,
        target=best,
        reason=f"{best} minimise distance + densité + étroitesse",
        tick=tick,
        confidence=0.7,
    )
