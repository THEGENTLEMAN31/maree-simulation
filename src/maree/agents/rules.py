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

#: Au-delà de N ticks sans retrouver un proche, on renonce à chercher et
#: on évacue. Sans cette borne, un agent cherche indéfiniment et ne sort
#: jamais — 5 agents sur 60 dans un run hybride réel.
SEARCH_TICKS = 5

#: Verbes qui font d'une annonce un **ordre** d'évacuation.
#: « Veuillez rester calmes et suivre les indications » n'en est pas un :
#: la traiter comme telle rendait la clarté du message (H1) inobservable,
#: puisque les 48 agents à règles sortaient sur n'importe quelle annonce.
_EVACUATION_WORDS = ("évacu", "evacu", "rejoignez", "sortez", "quittez", "dirigez-vous")


def _announcement_is_order(text: str | None) -> bool:
    if not text:
        return False
    low = text.lower()
    return any(word in low for word in _EVACUATION_WORDS)


def _announced_exit(text: str | None, plan: Plan) -> ExitId | None:
    """La sortie que l'annonce nomme par son étiquette, s'il y en a une.

    « Rejoignez la sortie nord, Grand Quai » désigne A. Une annonce qui ne
    nomme aucune sortie laisse le choix au coût (distance, densité,
    étroitesse).
    """
    if not text:
        return None
    low = text.lower()
    for exit_id, ex in plan.exits.items():
        if ex.label and ex.label.lower() in low:
            return exit_id
    return None


def _known_open(plan: Plan, profile_id: str, percept: Percept) -> list[ExitId]:
    profile = get_profile(profile_id)
    return [
        e for e in plan.exits if e in percept.exits_open and profile.knows(e)
    ]


def rules_decide(percept: Percept, plan: Plan, *, profile: str) -> Intention:
    tick = percept.tick

    # 1. Un proche a disparu : on le cherche avant de fuir, mais pas
    #    indéfiniment. Passé SEARCH_TICKS, on renonce et on évacue.
    if (
        percept.missing_kin
        and profile in {"famille"}
        and percept.missing_kin_ticks <= SEARCH_TICKS
    ):
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
        or _announcement_is_order(percept.announcement)
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
    reason = f"{best} minimise distance + densité + étroitesse"
    announced = _announced_exit(percept.announcement, plan)
    if announced is not None and announced in candidates:
        best = announced
        reason = f"l'annonce nomme {best}"

    # 3. L'agent de sécurité guide au lieu de fuir seul.
    if profile == "securite" and percept.nearby:
        return Intention(
            IntentionKind.GUIDE,
            target=best,
            reason=f"orienter vers {best} : {reason}",
            tick=tick,
            confidence=0.85,
        )

    return Intention(
        IntentionKind.GO_EXIT,
        target=best,
        reason=reason,
        tick=tick,
        confidence=0.7,
    )
