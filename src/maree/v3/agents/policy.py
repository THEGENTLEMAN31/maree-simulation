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
from maree.v3.core.ports import LLMTrace

#: Racines qui font d'une annonce ou d'un message un ordre d'évacuation
#: (couvre évacuer, évacuez, évacuation ; sortir, sortie ; quittez…).
#: Corollaire v2 : toute annonce ne vaut pas danger sans un ordre explicite.
_EVACUATION_WORDS = ("évacu", "sortir", "sortie", "quitte", "exécute")

#: Racines d'une **notice de fermeture** : « la sortie A est bloquée » informe,
#: ce n'est pas un ordre d'évacuer *vers A* (défaut mesuré le 2026-11-17).
_CLOSURE_WORDS = ("bloqu", "ferm", "close", "inaccessible")


def _mentions_closure(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in _CLOSURE_WORDS)


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
    #: trace du (éventuel) appel LLM — audit et coût (semaine 4).
    llm_trace: LLMTrace | None = None
    fallback_cause: str | None = None
    #: cause d'escalade vers le modèle (bras hybride) — None si routine.
    escalation_cause: str | None = None
    escalation_detail: dict[str, object] = field(default_factory=dict)
    #: vrai si la cible a été **résolue par le moteur** (le petit modèle a dit
    #: « sortir » sans nommer de porte). Une mesure qui compte ce choix comme
    #: un exploit du modèle mesure le moteur.
    target_resolved: bool = False
    #: vrai si la cible a été prise **faute de mieux** : toutes les sorties
    #: connues étaient crues bloquées. Ce n'est pas une erreur de politique.
    target_least_bad: bool = False
    #: vrai si, **au moment de décider**, l'agent croyait la cible bloquée.
    #: C'est le seul compteur qui distingue « se trompe » de « ne croit plus
    #: que c'est fermé » : la croyance s'oublie (0,98/décision) et un ouï-dire
    #: peut la repasser sous le seuil 0,5.
    target_believed_blocked: bool = False


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
    if ann and _is_evacuation_order(ann) and not _mentions_closure(ann):
        target = _named_exit(ann, set(known_exits))
        least_bad = False
        if target is None:
            # on évacue vers la sortie connue la plus confiante
            target, least_bad = _exit_choice(knowledge)
        return Decision(
            action=Action.EVACUER,
            tick=tick,
            target=target,
            target_least_bad=least_bad,
            explanation=" et ".join(
                [f"{name} évacue suite à l'annonce", *appraisal_reasons]
            ),
            appraisal=appraisal,
            raisons=appraisal.raisons,
        )

    # --- 2bis. influence sociale : un message ordonne d'évacuer ---
    for m in perception.heard:
        if _is_evacuation_order(m.fact) and not _mentions_closure(m.fact):
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
        target, least_bad = _exit_choice(knowledge)
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
            target_least_bad=least_bad,
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


def _exit_choice(knowledge: Knowledge) -> tuple[str | None, bool]:
    """(sortie choisie, était-ce la « moins mauvaise » faute de mieux ?).

    Si **toutes** les sorties connues sont crues bloquées, on ne se fige pas :
    on prend la **moins mauvaise** (la croyance de danger la plus faible).
    Une foule qui reste immobile parce qu'elle croit tout fermé n'est pas un
    comportement de foule, c'est un arrêt de la simulation — mesuré le
    2026-11-18 : 22 sortis sur 60 dès que les agents se transmettent les
    fermetures.

    Le second drapeau est une **mesure**, pas un détail : une foule qui croit
    toutes les portes fermées et prend la moins mauvaise n'a pas mal choisi,
    elle n'a plus de choix. Compter ces décisions comme des erreurs de
    politique ferait passer une spirale de rumeur pour un défaut de décision.
    """
    best: tuple[float, str] | None = None
    fallback: tuple[float, str] | None = None
    for key, belief in knowledge.beliefs.items():
        if not key.startswith("exit:"):
            continue
        label = key[len("exit:"):]
        if _believed_blocked(knowledge, label):
            hazard = knowledge.beliefs[f"hazard:{label}"]
            cand_blocked = (hazard.confidence, label)
            if fallback is None or cand_blocked[0] < fallback[0]:
                fallback = cand_blocked
            continue
        cand = (belief.confidence, label)
        if best is None or cand[0] > best[0]:
            best = cand
    if best is not None:
        return best[1], False
    return (fallback[1], True) if fallback else (None, False)


def _most_confident_exit(knowledge: Knowledge) -> str | None:
    """La sortie retenue (voir ``_exit_choice`` pour le cas « tout est fermé »)."""
    return _exit_choice(knowledge)[0]


def _believed_blocked(knowledge: Knowledge, label: str) -> bool:
    """Vrai si l'agent croit la sortie ``label`` bloquée (croyance de danger)."""
    hazard = knowledge.beliefs.get(f"hazard:{label}")
    return hazard is not None and hazard.confidence >= 0.5


__all__ = [
    "_EVACUATION_WORDS",
    "Decision",
    "rules_decide",
]