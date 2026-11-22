"""agents.policy_head — le bras `decision_head` : un modèle System 1 pilote.

Différence de nature avec `llm` : on ne demande pas au modèle d'**écrire** une
décision en JSON (ce que le petit modèle ne sait pas faire, et ce que le grand
fait en bavardant), on lui demande une **probabilité par option** sur un
ensemble fermé. Conséquences, toutes mesurables :

- pas de parsing fragile, pas de cible inventée — les options sont celles que
  le moteur connaît ;
- la décision porte sa distribution : on sait si le modèle hésitait ;
- le coût est de quelques dizaines de jetons d'entrée et **zéro** de sortie.

Les options sont volontairement limitées à « rester » + une sortie par sortie
**connue** : le bras teste la lecture de l'état (fumée, dangers, annonce), pas
la créativité. Les sorties crues bloquées restent dans l'ensemble : c'est au
modèle de ne pas les choisir, sinon on ne mesure rien.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from maree.v3.adapters.decision_head import HeadAnswer, SystemOneHead
from maree.v3.agents.appraisal import Action, Appraisal
from maree.v3.agents.knowledge import Knowledge
from maree.v3.agents.memory import Memory
from maree.v3.agents.perception import Perception
from maree.v3.agents.policy import Decision, rules_decide
from maree.v3.agents.social import SocialState
from maree.v3.agents.traits import Traits
from maree.v3.core.ports import LLMMessage, LLMRequest, LLMResponse, LLMTrace

#: Consigne du bras. Mesuré sur Kev-4B : une consigne neutre (« si rien ne
#: menace, on reste ») laisse le modèle sur RESTER même sous fumée ; une
#: consigne qui nomme la fumée comme danger le fait sortir. Ce n'est pas du
#: réglage cosmétique : c'est la différence entre un modèle qui *classe* et un
#: modèle qui *raisonne* — et cela doit être dit dans le rapport.
INSTRUCTIONS = (
    "Choisis ce que fait le piéton. La fumée visible est un danger : le piéton "
    "évacue par une sortie sûre. Une sortie signalée dangereuse ne doit pas "
    "être choisie. Si rien ne menace, il reste sur place."
)


def state_text(perception: Perception, knowledge: Knowledge,
               known_exits: frozenset[str]) -> str:
    """L'état, en français, compact — ce que le modèle de décision lit.

    On y met ce qui change la décision : le danger perçu, l'annonce, ce qui a
    été **entendu**, les croyances de sortie et de danger, la distance au
    foyer, la densité. On n'y met pas les positions des autres agents (bruit).
    """
    lines: list[str] = []
    lines.append(f"Etage : {perception.zone.uid}")
    if perception.smoke_visible:
        distance = (
            "distance inconnue"
            if perception.distance_to_danger is None
            else f"a {perception.distance_to_danger:.0f} m"
        )
        # « Danger : … » et non « Fumée visible » : un modèle System 1 lit
        # l'étiquette, pas l'implication (mesuré : RESTER 0,42 contre
        # SORTIR 0,41 selon la formulation, à état identique).
        lines.append(f"Danger : fumee visible ({distance}).")
    else:
        lines.append("Pas de fumee visible.")
    if perception.announcement:
        lines.append(f"Annonce officielle : « {perception.announcement} »")
    if perception.heard:
        facts = "; ".join(m.fact for m in perception.heard[:3])
        lines.append(f"Messages entendus : {facts}")
    lines.append(
        "Densite locale : " + f"{perception.crowding:.2f}" + " personne par metre carre."
    )
    known = sorted(known_exits)
    lines.append("Sorties connues : " + (", ".join(known) if known else "aucune") + ".")
    blocked = []
    for label in known:
        hazard = knowledge.beliefs.get(f"hazard:{label}")
        if hazard is not None and hazard.confidence >= 0.5:
            blocked.append(label)
    if blocked:
        lines.append("Sorties signalees dangereuses : " + ", ".join(blocked) + ".")
    confidences = []
    for label in known:
        belief = knowledge.beliefs.get(f"exit:{label}")
        if belief is not None:
            confidences.append(f"{label} ({belief.confidence:.2f})")
    if confidences:
        lines.append("Confiance dans les sorties : " + ", ".join(confidences) + ".")
    return "\n".join(lines)


def criteria_for(known_exits: frozenset[str]) -> dict[str, str]:
    """L'ensemble fermé : rester, ou sortir par l'une des sorties connues."""
    criteria = {"RESTER": "rester sur place et attendre"}
    for label in sorted(known_exits):
        criteria[f"SORTIR {label}"] = f"evacuer par la sortie {label}"
    return criteria


#: Le head par défaut, branché au bootstrap (comme les fournisseurs de chat).
_DEFAULT_HEAD: SystemOneHead | None = None


def set_default_head(head: SystemOneHead | None) -> None:
    global _DEFAULT_HEAD
    _DEFAULT_HEAD = head


def default_head() -> SystemOneHead:
    if _DEFAULT_HEAD is None:
        raise RuntimeError(
            "aucun modèle de décision branché : appeler assembly (bootstrap) "
            "ou policy_head.set_default_head(...)"
        )
    return _DEFAULT_HEAD


@dataclass(frozen=True, slots=True)
class DecisionHeadPolicy:
    """Le bras `decision_head` : une distribution, puis l'argmax."""

    head: SystemOneHead

    def decide(
        self,
        *,
        perception: Perception,
        knowledge: Knowledge,
        social: SocialState,
        traits: Traits,
        appraisal: Appraisal,
        known_exits: frozenset[str],
        name: str,
        memory: Memory | None = None,
        rag: list[dict[str, object]] | None = None,
    ) -> Decision:
        del social, traits, memory, rag  # le modèle lit état + options, rien d'autre
        criteria = criteria_for(known_exits)
        state = state_text(perception, knowledge, known_exits)
        answer = self.head.choose(state, INSTRUCTIONS, criteria)
        trace = _trace(perception, state, criteria, answer)
        if not answer.ok:
            return _fallback(
                "no_response", perception, knowledge, known_exits, name, appraisal, trace
            )
        choice = answer.choice
        if choice == "RESTER":
            return Decision(
                action=Action.RESTER,
                tick=perception.tick,
                explanation=f"{name} (head {self.head.model}) : RESTER "
                f"p={answer.probabilities.get('RESTER', 0.0):.2f}",
                appraisal=appraisal,
                raisons=appraisal.raisons,
                llm_trace=trace,
            )
        if choice.startswith("SORTIR "):
            label = choice.split(" ", 1)[1].strip()
            if label in known_exits:
                return Decision(
                    action=Action.EVACUER,
                    tick=perception.tick,
                    target=label,
                    explanation=f"{name} (head {self.head.model}) : SORTIR {label} "
                    f"p={answer.probabilities.get(choice, 0.0):.2f}",
                    appraisal=appraisal,
                    raisons=appraisal.raisons,
                    llm_trace=trace,
                )
        return _fallback(
            "unknown_exit", perception, knowledge, known_exits, name, appraisal, trace
        )


def _trace(
    perception: Perception,
    state: str,
    criteria: dict[str, str],
    answer: HeadAnswer,
) -> LLMTrace:
    """Le journal garde la distribution : c'est la trace d'audit du bras."""
    payload = {
        "choice": answer.choice,
        "probabilities": {k: round(v, 4) for k, v in sorted(answer.probabilities.items())},
        "confidence": round(answer.confidence, 4),
        "margin": round(answer.margin(), 4),
        "criteria": sorted(criteria),
    }
    request = LLMRequest(
        messages=(LLMMessage("system", INSTRUCTIONS), LLMMessage("user", state)),
        temperature=0.0,
        max_tokens=0,
        provider="systemone",
        model="head",
    )
    response = LLMResponse(
        text=json_dumps(payload),
        provider="systemone",
        model="head",
        prompt_tokens=answer.input_tokens,
        completion_tokens=0,
        ok=answer.ok,
    )
    return LLMTrace(
        tick=perception.tick, request=request, response=response,
        fallback=not answer.ok, fallback_cause=answer.error,
    )


def json_dumps(payload: object) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _fallback(
    cause: str,
    perception: Perception,
    knowledge: Knowledge,
    known_exits: frozenset[str],
    name: str,
    appraisal: Appraisal,
    trace: LLMTrace,
) -> Decision:
    base = rules_decide(
        perception=perception,
        knowledge=knowledge,
        social=SocialState(),
        traits=Traits(),
        appraisal=appraisal,
        known_exits=known_exits,
        name=name,
    )
    return replace(
        base,
        explanation=f"repli regles ({cause}) — {base.explanation}",
        fallback=True,
        fallback_cause=cause,
        llm_trace=trace,
    )


__all__ = [
    "INSTRUCTIONS",
    "DecisionHeadPolicy",
    "criteria_for",
    "default_head",
    "set_default_head",
    "state_text",
]
