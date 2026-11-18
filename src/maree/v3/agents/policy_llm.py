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
import re
from dataclasses import dataclass, field, replace

from maree.v3.agents.appraisal import Action, Appraisal
from maree.v3.agents.catalog import chat_for
from maree.v3.agents.knowledge import Knowledge
from maree.v3.agents.memory import Memory
from maree.v3.agents.perception import Perception
from maree.v3.agents.policy import (
    Decision,
    _is_evacuation_order,
    _mentions_closure,
    _most_confident_exit,
    rules_decide,
)
from maree.v3.agents.schedule import escalation_cause, labels_in
from maree.v3.agents.social import SocialState
from maree.v3.agents.traits import Traits
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import (
    ChatModelPort,
    LLMMessage,
    LLMRequest,
    LLMTrace,
    PolicyName,
)

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


#: Protocole du tier « petit » (0,6 Md). Quatre formats ont été essayés en
#: v2 : JSON à vocabulaire ouvert (il recopie le gabarit, jamais une sortie),
#: liste de mots-clés (il choisit **la première option**, quel que soit le
#: contexte), question binaire (instable, vire au OUI). Ce qui marche : une
#: **règle écrite** et deux drapeaux.
#:
#: Trois détails mesurés le 2026-11-18 sur qwen3-0-6b, et non devinés :
#:
#: - le gabarit ``SORTIR <lettre de la sortie>`` **reste** dans le prompt
#:   système : sans lui le modèle répond RESTER à tout (3 essais sur 3 dans
#:   les deux cas de fumée et d'annonce) ; avec lui il dit SORTIR mais
#:   recopie souvent le placeholder au lieu de la lettre ;
#: - la fumée doit être le **dernier** drapeau : avec « Fumée visible : oui »
#:   en tête, la ligne « Annonce d'évacuation : non » la neutralisait et il
#:   répondait RESTER sous fumée 6 fois sur 6 ;
#: - l'ordre des mots de la règle compte : « fumée = oui OU annonce = oui ⇒
#:   tu sors » tient ; une formulation en phrases le fait retomber sur RESTER.
#:
#: Résultat mesuré (6 essais par cas) : calme RESTER 6/6, fumée SORTIR 6/6,
#: annonce SORTIR 6/6, annonce sans ordre RESTER 6/6. La **lettre** de la
#: sortie n'est pas lue de façon fiable (il rend le placeholder) : c'est au
#: moteur de choisir la porte parmi celles que l'agent connaît et ne croit pas
#: bloquées. Ce tier applique une politique ; il ne juge pas la géographie.
SMALL_SYSTEM = (
    "Tu es un piéton dans un bâtiment.\n"
    "Règle : fumée = oui OU annonce = oui ⇒ tu sors. Sinon tu restes.\n"
    "Réponds une seule ligne : RESTER, ou SORTIR <lettre de la sortie>."
)


def small_messages(
    perception: Perception, known_exits: frozenset[str]
) -> tuple[LLMMessage, ...]:
    """Le prompt à drapeaux : deux faits, pas un contrat JSON.

    Donner le contrat JSON du grand modèle au petit le faisait répondre
    ``oui`` à t1 sans fumée (les deux consignes mêlées). Ici chaque ligne est
    un fait vérifiable, et la règle est écrite avant.
    """
    announcement = perception.announcement or ""
    is_order = (
        bool(announcement)
        and _is_evacuation_order(announcement)
        and not _mentions_closure(announcement)
    )
    named = ""
    if is_order:
        found = labels_in(announcement, known_exits)
        named = found[0] if found else ""
    lines = [
        f"Annonce d'évacuation : {'oui' if is_order else 'non'}",
        f"Sortie indiquée : {named or 'aucune'}",
        # la fumée est le **dernier** drapeau : un petit modèle pèse la fin du
        # prompt (mesuré 2026-11-18 : avec la fumée en tête, « annonce : non »
        # la neutralisait et il répondait RESTER sous fumée 6/6).
        f"Fumée visible : {'oui' if perception.smoke_visible else 'non'}",
        f"Sorties connues : {', '.join(sorted(known_exits)) or 'aucune'}",
        "Décide :",
    ]
    return (
        LLMMessage("system", SMALL_SYSTEM),
        LLMMessage("user", "\n".join(lines)),
    )


def parse_choice(
    text: str, known_exits: frozenset[str]
) -> tuple[Action, str | None] | None:
    """Lit ``RESTER`` / ``SORTIR <sortie>`` (le tier petit ne produit pas de JSON).

    Une sortie nommée mais **inconnue** de l'agent rend ``None`` : c'est un
    repli avec cause ``unknown_exit``, pas une évacuation devinée. Un
    ``SORTIR`` sans étiquette (le petit modèle recopie souvent le gabarit
    ``SORTIR <sortie>``) rend ``(EVACUER, None)`` : la politique a décidé de
    sortir, c'est au moteur de choisir la porte parmi celles que l'agent
    connaît — le petit modèle **applique** une politique, il ne juge pas la
    géographie.
    """
    upper = text.upper()
    if "RESTER" in upper:
        return Action.RESTER, None
    if "SORTIR" in upper or "ÉVACUER" in upper or "EVACUER" in upper:
        found = labels_in(text, known_exits)
        if found:
            return Action.EVACUER, found[0]
        # une étiquette citée mais inconnue n'est pas une évacuation devinée
        cited = {
            token
            for token in re.findall(r"\b[A-Z](?:\d{1,2})?\b", upper)
            if not token.isdigit()
        }
        if cited - known_exits:
            return None
        # pas d'étiquette (ou le gabarit « SORTIR <sortie> ») : à résoudre
        return Action.EVACUER, None
    return None


def build_inputs(
    *,
    perception: Perception,
    traits: Traits,
    appraisal: Appraisal,
    knowledge: Knowledge,
    memory: Memory | None = None,
    rag: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Le contexte compact et auditable envoyé au modèle.

    ``memory`` rend le **memorandum** personnel : les reçus de l'agent
    (fait, source, tick, confiance) que le modèle doit intégrer. C'est ce
    qui rend la mémoire *visible dans le comportement* — la mission.
    ``rag`` porte les passages **retrouvés** (id, titre, collection,
    contenu) : la base de connaissances consultée, pas seulement le prompt.
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
        "contexte_rag": rag or [],
        "stress": round(perception.state.stress, 2),
        "herding": traits.herding,
        # C2 : la perception entre dans le prompt. Sans cela, un changement
        # de densité ou de voisinage n'était pas « perceptible » par le modèle.
        "perception": {
            "voisins_vus": len(perception.seen_agents),
            "densite_locale": round(perception.crowding, 2),
            "distance_danger": (
                None
                if perception.distance_to_danger is None
                else round(perception.distance_to_danger, 1)
            ),
            "sorties_visibles": sorted(perception.exits_visible),
            "sorties_fermees": sorted(perception.closed_exits),
            "fatigue": round(perception.state.fatigue, 2),
            "visibilite": round(perception.state.visibility, 1),
        },
    }


@dataclass(frozen=True, slots=True)
class LLMPolicy:
    """Décide via le modèle de ``alias`` (defaut le tier ``decision``).

    ``small_protocol`` choisit le format du prompt. ``None`` le déduit du
    catalogue : un modèle tagué ``small`` reçoit une **règle + deux
    drapeaux**, pas le contrat JSON — les deux consignes mêlées faisaient
    répondre ``oui`` au petit modèle sans aucune fumée (leçon v2).
    """

    alias: str = "decision"
    port: ChatModelPort | None = None  # injecté au bootstrap ; sinon résolus
    small_protocol: bool | None = None

    def _port(self) -> tuple[ChatModelPort, str, str]:
        if self.port is not None:
            return self.port, self.port.__class__.__name__, self.alias
        port, spec = chat_for(self.alias)
        return port, spec.provider, spec.model

    def _is_small(self) -> bool:
        if self.small_protocol is not None:
            return self.small_protocol
        if self.port is not None:
            return False
        try:
            _, spec = chat_for(self.alias)
        except KeyError:
            return False
        return "small" in spec.tags

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
        port, provider, model = self._port()
        small = self._is_small()
        if small:
            messages = small_messages(perception, known_exits)
            max_tokens = 16
        else:
            inputs = build_inputs(
                perception=perception,
                traits=traits,
                appraisal=appraisal,
                knowledge=knowledge,
                memory=memory,
                rag=rag,
            )
            messages = _schema_messages(inputs)
            max_tokens = 200
        request = LLMRequest(
            messages=messages,
            temperature=0.0,
            max_tokens=max_tokens,
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
        parsed = (
            parse_choice(response.text, known_exits)
            if small
            else _parse(response.text, known_exits)
        )
        if parsed is None:
            cause = "unknown_exit" if small and "SORTIR" in response.text.upper() else "unparseable"
            return _fallback(
                cause, perception, knowledge, social, traits, appraisal,
                known_exits, name, llm_trace,
            )
        action, target = parsed
        resolved_by_engine = False
        if small and action is Action.EVACUER and target is None:
            # le petit a dit « sortir » sans nommer de porte : la politique est
            # appliquée, le choix de la porte reste au moteur (parmi les
            # sorties que l'agent connaît et ne croit pas bloquées).
            target = _most_confident_exit(knowledge)
            resolved_by_engine = True
            if target is None:
                return _fallback(
                    "unknown_exit", perception, knowledge, social, traits,
                    appraisal, known_exits, name, llm_trace,
                )
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
            target_resolved=resolved_by_engine,
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
    rag: list[dict[str, object]] | None = None,
    alias: str = "decision",
    run_id: str = "v3",
    epsilon: float = 0.0,
    agent: object | None = None,
) -> Decision:
    """Règles d'abord ; le modèle ne parle que si le **monde** est ambigu.

    L'escalade n'est pas « les règles ne savent pas quoi faire » (critère
    circulaire, 0 appel mesuré) : elle est calculée par
    ``schedule.escalation_cause`` sur des faits du monde — contradiction,
    annonce ambiguë, situation inédite, revue, quota instrumenté.
    """
    base = rules_decide(
        perception=perception,
        knowledge=knowledge,
        social=social,
        traits=traits,
        appraisal=appraisal,
        known_exits=known_exits,
        name=name,
    )
    context = agent if agent is not None else _ScheduleContext(
        knowledge=knowledge,
        known_exits=known_exits,
        memory=memory or Memory(),
        name=name,
    )
    escalation = escalation_cause(
        context,  # type: ignore[arg-type]
        perception,
        base=base,
        appraisal=appraisal,
        epsilon=epsilon,
        run_id=run_id,
    )
    if escalation is None:
        return base
    decision = LLMPolicy(alias=alias).decide(
        perception=perception,
        knowledge=knowledge,
        social=social,
        traits=traits,
        appraisal=appraisal,
        known_exits=known_exits,
        name=name,
        memory=memory,
        rag=rag,
    )
    return replace(
        decision,
        escalation_cause=escalation.cause,
        escalation_detail=escalation.detail,
    )


@dataclass(slots=True)
class _ScheduleContext:
    """Contexte minimal pour l'escalade quand on n'a pas d'``Agent`` complet."""

    knowledge: Knowledge
    known_exits: frozenset[str]
    memory: Memory
    name: str
    policy: PolicyName = PolicyName.HYBRID
    uid: AgentId = field(default_factory=lambda: AgentId(0))
    _last_decision: Decision | None = None
    _trail: list[tuple[int, tuple[float, float]]] = field(default_factory=list)


__all__ = [
    "SMALL_SYSTEM",
    "SYSTEM_PROMPT",
    "LLMPolicy",
    "build_inputs",
    "hybrid_decide",
    "parse_choice",
    "small_messages",
]