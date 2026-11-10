"""agents.policy — les politiques de décision (comportement.md §10).

En semaine 2 on livre la politique ``rules`` : déterministe, reproductible,
basée sur l'appraisal. Une ``Decision`` porte toujours une **explication
complète** — c'est le contrat d'audit du front (« pourquoi »).
Le registre de politiques (`hybrid`, `llm`, `decision_head`) sera branché
avec la semaine 4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from maree.v3.agents.appraisal import Action, Appraisal
from maree.v3.agents.knowledge import Knowledge
from maree.v3.agents.perception import Perception
from maree.v3.agents.social import SocialState
from maree.v3.agents.traits import Traits
from maree.v3.core.ids import Tick

#: Racines qui font d'une annonce ou d'un message un ordre d'évacuation
#: (couvre évacuer, évacuez, évacuation ; sortir, sortie ; quittez…).
#: Corollaire v2 : toute annonce ne vaut pas danger sans un ordre explicite.
_EVACUATION_WORDS = ("évacu", "sortir", "sortie", "quitte", "exécute")


@dataclass(frozen=True, slots=True)
class Decision:
    """La décision cognitive d'un agent : action + cible + explication."""

    action: Action
    tick: Tick
    #: cible de l'action : un ExitId, un nom de proche, ou None.
    target: str | None = None
    explanation: str = ""
    appraisal: Appraisal | None = None
    #: repli sur les règles (utilisé quand une autre politique échoue).
    fallback: bool = False
    raisons: dict[str, str] = field(default_factory=dict)


def _is_evacuation_order(announcement: str) -> bool:
    lowered = announcement.lower()
    return any(w in lowered for w in _EVACUATION_WORDS)


def _named_exit(announcement: str, known: set[str]) -> str | None:
    for token in announcement.upper().split():
        token = token.strip("«».:,!")
        for label in known:
            if token == label:
                return label
    return None


def rules_decide(
    *,
    perception: Perception,
    knowledge: Knowledge,
    social: SocialState,
    traits: Traits,
    appraisal: Appraisal,
    known_exits: frozenset[str],
    name: str,
) -> Decision:
    """La politique ``rules`` : choix protectif déterministe.

    Priorité de la logique :
    1. un proche non réuni + menace modérée  -> chercher le proche ;
    2. un ordre d'évacuation (annonce)       -> évacuer (vers la sortie nommée) ;
    3. une fumée / une menace haute          -> évacuer (sortie la plus sûre
       connue, sinon suivre si les autres partent) ;
    4. une forte preuve sociale + `herding`  -> suivre ;
    5. un altruisme marqué et peu de menace  -> aider ;
    6. sinon, rester / chercher de l'information.
    """
    tick = perception.tick
    appraisal_reasons = list(appraisal.raisons.values())
    # --- 1. proches ---
    if social.kin and appraisal.menace < 0.55:
        kin_name = str(sorted(str(k) for k in social.kin)[0])
        return Decision(
            action=Action.CHERCHER_PROCHE,
            tick=tick,
            target=kin_name,
            explanation=" et ".join(
                [f"{name} part chercher {kin_name}", *appraisal_reasons]
            ),
            appraisal=appraisal,
            raisons=appraisal.raisons,
        )

    # --- 2. ordre d'évacuation ---
    ann = perception.announcement
    if ann and _is_evacuation_order(ann):
        target = _named_exit(ann, set(known_exits))
        if target is None:
            # on évacue vers la sortie connue la plus confiante
            target = _most_confident_exit(knowledge)
        return Decision(
            action=Action.EVACUER,
            tick=tick,
            target=target,
            explanation=" et ".join(
                [f"{name} évacue suite à l'annonce", *appraisal_reasons]
            ),
            appraisal=appraisal,
            raisons=appraisal.raisons,
        )

    # --- 2bis. influence sociale : un message ordonne d'évacuer ---
    for m in perception.heard:
        if _is_evacuation_order(m.fact):
            target = _named_exit(m.fact, set(known_exits)) or _most_confident_exit(
                knowledge
            )
            return Decision(
                action=Action.EVACUER,
                tick=tick,
                target=target,
                explanation=" et ".join(
                    [f"{name} évacue car {m.from_agent} le dit", *appraisal_reasons]
                ),
                appraisal=appraisal,
                raisons=appraisal.raisons,
            )

    # --- 3. fumée / menace haute ---
    if perception.smoke_visible or appraisal.menace >= 0.6:
        target = _most_confident_exit(knowledge)
        if target is None and perception.heard:
            # je ne connais pas de sortie : je suis celui qui part
            return Decision(
                action=Action.SUIVRE,
                tick=tick,
                explanation=" et ".join(
                    [f"{name} suit la foule car menace", *appraisal_reasons]
                ),
                appraisal=appraisal,
                raisons=appraisal.raisons,
            )
        return Decision(
            action=Action.EVACUER,
            tick=tick,
            target=target,
            explanation=" et ".join(
                [f"{name} évacue (menace)", *appraisal_reasons]
            ),
            appraisal=appraisal,
            raisons=appraisal.raisons,
        )

    # --- 4. preuve sociale / suivre ---
    if appraisal.preuve_sociale >= 0.6 and traits.herding >= 0.5:
        return Decision(
            action=Action.SUIVRE,
            tick=tick,
            explanation=" et ".join(
                [f"{name} suis les autres", *appraisal_reasons]
            ),
            appraisal=appraisal,
            raisons=appraisal.raisons,
        )

    # --- 5. altruisme / aider ---
    if traits.altruism >= 0.7 and appraisal.menace < 0.4:
        return Decision(
            action=Action.AIDER,
            tick=tick,
            explanation=" et ".join(
                [f"{name} reste pour aider", *appraisal_reasons]
            ),
            appraisal=appraisal,
            raisons=appraisal.raisons,
        )

    # --- 6. défaut ---
    return Decision(
        action=Action.RESTER,
        tick=tick,
        explanation=" et ".join(
            [f"{name} reste en place", *appraisal_reasons]
        ),
        appraisal=appraisal,
        raisons=appraisal.raisons,
    )


def _most_confident_exit(knowledge: Knowledge) -> str | None:
    """La sortie connue la plus confiante, en ignorant celles croyues bloquées."""
    best: tuple[float, str] | None = None
    for key, belief in knowledge.beliefs.items():
        if not key.startswith("exit:"):
            continue
        label = key[len("exit:"):]
        if _believed_blocked(knowledge, label):
            continue
        cand = (belief.confidence, label)
        if best is None or cand[0] > best[0]:
            best = cand
    return best[1] if best else None


def _believed_blocked(knowledge: Knowledge, label: str) -> bool:
    """Vrai si l'agent croit la sortie ``label`` bloquée (croyance de danger)."""
    hazard = knowledge.beliefs.get(f"hazard:{label}")
    return hazard is not None and hazard.confidence >= 0.5


__all__ = [
    "_EVACUATION_WORDS",
    "Decision",
    "rules_decide",
]