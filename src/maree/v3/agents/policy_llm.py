"""agents.policy_llm — politique ``llm`` et ``hybrid`` (comportement.md §10).

La politique ``llm`` : construit un prompt auditable depuis la perception et
l'appraisal, appelle ``ChatModelPort``, parse une réponse JSON *contrôlée*,
**valide la cible** contre les sorties connues (leçon v2 : une cible invalide
= repli), et en cas de panne/parse/validité → **repli sur les règles** avec
une cause nommée.

La politique ``hybrid`` : règles d'abord ; on ne monte au LLM que si les
règles produisent de l'*ambiguïté* (menace sans sortie confiante). C'est le
défaut choisi pour la reproductibilité.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from maree.v3.agents.appraisal import Action, Appraisal
from maree.v3.agents.catalog import chat_for
from maree.v3.agents.knowledge import Knowledge
from maree.v3.agents.memory import Memory
from maree.v3.agents.perception import Perception
from maree.v3.agents.policy import Decision, rules_decide
from maree.v3.agents.social import SocialState
from maree.v3.agents.traits import Traits
from maree.v3.core.ports import ChatModelPort, LLMMessage, LLMRequest, LLMTrace

SYSTEM_PROMPT = (
    "Tu es un piéton en évacuation dans un bâtiment. Décide une action, et si tu "
    "évacues, choisis la sortie la plus sûre en pesant TOUTES tes croyances : ne "
    "jamais emprunter une sortie citée dans 'dangers' (bloquée), et préfère celle "
    "de 'sorties_connues' avec la plus haute confiance. Réponds UNIQUEMENT en JSON "
    "valide au format {\"action\": \"evacuer|rester|chercher|suivre|aider|"
    "chercher_proche\", \"cible\": \"<une sortie connue> ou null\", "
    "\"confiance\": 0..1}."
)


def _schema_messages(inputs: dict[str, object]) -> tuple[LLMMessage, ...]:
    user = json.dumps(inputs, ensure_ascii=False, sort_keys=True)
    return (
        LLMMessage("system", SYSTEM_PROMPT),
        LLMMessage("user", user),
    )


def build_inputs(
    *,
    perception: Perception,
    traits: Traits,
    appraisal: Appraisal,
    knowledge: Knowledge,
    memory: Memory | None = None,
) -> dict[str, object]:
    """Le contexte compact et auditable envoyé au modèle.

    ``memory`` rend le **memorandum** personnel : les reçus de l'agent
    (fait, source, tick, confiance) que le modèle doit intégrer. C'est ce
    qui rend la mémoire *visible dans le comportement* — la mission.
    """
    known = sorted(
        (k[5:], round(b.confidence, 2), b.source.value, b.tick)
        for k, b in knowledge.beliefs.items()
        if k.startswith("exit:")
    )
    hazards = sorted(
        (k[7:], b.fact) for k, b in knowledge.beliefs.items() if k.startswith("hazard:")
    )
    heard = [
        {"fact": m.fact, "from": str(m.from_agent), "tick": m.tick, "confiance": m.confidence}
        for m in perception.heard
    ]
    memo = []
    if memory is not None:
        # reçus ordonnés par confiance décroissante (le plus retenu d'abord)
        for fact, r in sorted(
            memory.receipts.items(), key=lambda kv: kv[1].confidence, reverse=True
        ):
            memo.append(
                {
                    "fait": fact,
                    "source": r.source.value,
                    "tick": r.tick,
                    "confiance": round(r.confidence, 2),
                }
            )
    return {
        "tick": perception.tick,
        "smoke": perception.smoke_visible,
        "annonce": perception.announcement,
        "menace": {k: round(v, 2) for k, v in appraisal.dimensions.items()},
        "sorties_connues": known,
        "dangers": hazards,
        "messages_recus": heard,
        "memoire": memo,
        "stress": round(perception.state.stress, 2),
        "herding": traits.herding,
    }


@dataclass(frozen=True, slots=True)
class LLMPolicy:
    """Décide via le modèle de ``alias`` (defaut le tier ``decision``)."""

    alias: str = "decision"
    port: ChatModelPort | None = None  # injecté au bootstrap ; sinon résolus

    def _port(self) -> tuple[ChatModelPort, str, str]:
        if self.port is not None:
            return self.port, self.port.__class__.__name__, self.alias
        port, spec = chat_for(self.alias)
        return port, spec.provider, spec.model

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
    ) -> Decision:
        port, provider, model = self._port()
        inputs = build_inputs(
            perception=perception,
            traits=traits,
            appraisal=appraisal,
            knowledge=knowledge,
            memory=memory,
        )
        request = LLMRequest(
            messages=_schema_messages(inputs),
            temperature=0.0,
            max_tokens=200,
            model=model,
            provider=provider,
        )
        response = port.complete(request)
        llm_trace = LLMTrace(
            tick=perception.tick,
            request=request,
            response=response,
        )
        if not response.ok:
            return _fallback(
                "no_response", perception, knowledge, social, traits, appraisal,
                known_exits, name, llm_trace,
            )
        parsed = _parse(response.text, known_exits)
        if parsed is None:
            return _fallback(
                "unparseable", perception, knowledge, social, traits, appraisal,
                known_exits, name, llm_trace,
            )
        action, target = parsed
        # ici le raisonnement passe par le template : l'action issue du LLM
        # est mappée sur le vocabulaire du moteur.
        decision = Decision(
            action=action,
            tick=perception.tick,
            target=target,
            explanation=f"{name} (LLM {model}) : {action.value} -> {target}",
            appraisal=appraisal,
            raisons=appraisal.raisons,
            llm_trace=llm_trace,
        )
        return decision


def _parse(text: str, known_exits: frozenset[str]) -> tuple[Action, str | None] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # tente d'extraire le premier objet JSON d'un flot bavard
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    action_str = str(data.get("action", "")).strip().lower()
    action = {
        "evacuer": Action.EVACUER,
        "rester": Action.RESTER,
        "chercher": Action.CHERCHER,
        "suivre": Action.SUIVRE,
        "aider": Action.AIDER,
        "chercher_proche": Action.CHERCHER_PROCHE,
        "revirer": Action.REVIRER,
    }.get(action_str)
    if action is None:
        return None
    target = data.get("cible")
    target = str(target).strip() if target else None
    if action is Action.EVACUER and (target is None or target not in known_exits):
        # validation de cible (leçon v2) : on n'évacue que vers une sortie connue
        return None
    return action, target


def _fallback(
    cause: str,
    perception: Perception,
    knowledge: Knowledge,
    social: SocialState,
    traits: Traits,
    appraisal: Appraisal,
    known_exits: frozenset[str],
    name: str,
    llm_trace: LLMTrace | None,
) -> Decision:
    decision = rules_decide(
        perception=perception,
        knowledge=knowledge,
        social=social,
        traits=traits,
        appraisal=appraisal,
        known_exits=known_exits,
        name=name,
    )
    decision = Decision(
        action=decision.action,
        tick=decision.tick,
        target=decision.target,
        explanation=f"repli règles ({cause}) — {decision.explanation}",
        appraisal=appraisal,
        fallback=True,
        raisons=decision.raisons,
        llm_trace=llm_trace,
        fallback_cause=cause,
    )
    return decision


def hybrid_decide(
    *,
    perception: Perception,
    knowledge: Knowledge,
    social: SocialState,
    traits: Traits,
    appraisal: Appraisal,
    known_exits: frozenset[str],
    name: str,
    memory: Memory | None = None,
) -> Decision:
    """Règles d'abord ; on monte au LLM seulement en ambiguïté."""
    base = rules_decide(
        perception=perception,
        knowledge=knowledge,
        social=social,
        traits=traits,
        appraisal=appraisal,
        known_exits=known_exits,
        name=name,
    )
    # ambiguïté : menace mais aucune sortie confiante, ou hérdage sans cible.
    uncertain = (
        appraisal.menace >= 0.4
        and base.action in (Action.RESTER, Action.CHERCHER)
    ) or base.action == Action.SUIVRE
    if uncertain:
        policy = LLMPolicy().decide(
            perception=perception,
            knowledge=knowledge,
            social=social,
            traits=traits,
            appraisal=appraisal,
            known_exits=known_exits,
            name=name,
            memory=memory,
        )
        return policy
    return base


__all__ = ["SYSTEM_PROMPT", "LLMPolicy", "build_inputs", "hybrid_decide"]