"""verify.bench — banc d'évaluation de politiques (style OpenJev, S4).

Un petit jeu de *situations* standardisées : chacune attend une action
donnée. Un run de banc soumet chaque situation à une politique et mesure
la résolution, la justesse et le taux de repli. On compare les politiques
(``rules``, ``llm`` avec un fournisseur donné, ``hybrid``) sur le *même*
jeu — le support de la décision « adopter ou non ».
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from maree.v3.agents.agent import Agent, make_agent
from maree.v3.agents.appraisal import Action, appraise
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.policy import Decision, rules_decide
from maree.v3.agents.policy_llm import LLMPolicy, hybrid_decide
from maree.v3.agents.state import State
from maree.v3.core.ids import AgentId, ZoneId

#: une décision = (action, cible_attendu|None)
Decider = Callable[
    [Agent, Perception],
    Decision,
]


@dataclass(frozen=True, slots=True)
class Situation:
    name: str
    expected: Action
    #: rien (rester) | fumée | annonce | message | menace | proche
    archetype: str = "visiteur"
    known_exits: frozenset[str] = frozenset({"A", "B", "C"})
    smoke: bool = False
    announcement: str | None = None
    message: str | None = None
    threat: float = 0.0
    kin: bool = False
    description: str = ""


def _agent_for(s: Situation) -> Agent:
    a = make_agent(uid=1, archetype=s.archetype, known_exits=s.known_exits)
    if s.kin:
        a.social.kin.add(AgentId(99))
    return a


def _perception(s: Situation, drink: tuple[Message, ...]) -> Perception:
    return Perception(
        tick=10,
        zone=ZoneId("z1"),
        state=State(),
        smoke_visible=s.smoke,
        announcement=s.announcement,
        heard=drink,
        threat=s.threat,
        seen_agents=(AgentId(2), AgentId(3)) if s.archetype == "agent_de_securite" else (),
        exits_visible=frozenset(s.known_exits),
    )


#: Un jeu de situations d'entraînement (petit noyau, extensible).
SITUATIONS: tuple[Situation, ...] = (
    Situation("calme", Action.RESTER, description="rien ne se passe, on reste"),
    Situation(
        "fumee", Action.EVACUER, smoke=True,
        description="fumée visible -> on évacue vers la sortie connue",
    ),
    Situation(
        "annonce_evac", Action.EVACUER,
        announcement="Veuillez évacuer par la sortie A",
        description="annonce claire -> évacuation",
    ),
    Situation(
        "annonce_calme", Action.RESTER,
        announcement="Veuillez rester calmes",
        description="annonce sans ordre -> on ne bouge pas",
    ),
    Situation(
        "proche_a_chercher", Action.CHERCHER_PROCHE, kin=True,
        description="un proche manque -> chercher avant la menace",
    ),
    Situation(
        "fumee_proche", Action.EVACUER, kin=True, smoke=True,
        description="fumée forte -> évacuer même avec un proche",
    ),
    Situation(
        "aide_altruiste", Action.AIDER, archetype="agent_de_securite",
        kin=True,
        description="agent de sécurité -> aider",
    ),
)


def rules_decider(a: Agent, p: Perception) -> Decision:
    ap = appraise(perception=p, traits=a.traits, knowledge=a.knowledge,
                  social=a.social, name=a.name)
    return rules_decide(perception=p, knowledge=a.knowledge, social=a.social,
                        traits=a.traits, appraisal=ap, known_exits=a.known_exits,
                        name=a.name)


def hybrid_decider(a: Agent, p: Perception) -> Decision:
    ap = appraise(perception=p, traits=a.traits, knowledge=a.knowledge,
                  social=a.social, name=a.name)
    return hybrid_decide(perception=p, knowledge=a.knowledge, social=a.social,
                         traits=a.traits, appraisal=ap, known_exits=a.known_exits,
                         name=a.name)


def llm_decider(a: Agent, p: Perception) -> Decision:
    ap = appraise(perception=p, traits=a.traits, knowledge=a.knowledge,
                  social=a.social, name=a.name)
    return LLMPolicy().decide(perception=p, knowledge=a.knowledge, social=a.social,
                              traits=a.traits, appraisal=ap, known_exits=a.known_exits,
                              name=a.name)


def run_bench(decider: Decider, situations: tuple[Situation, ...] = SITUATIONS) -> dict[str, object]:
    """Évalue une politique sur le jeu : résolution, justesse, replis."""
    by_name: dict[str, dict[str, object]] = {}
    for s in situations:
        agent = _agent_for(s)
        drink = (Message(s.message, AgentId(3), 10),) if s.message else ()
        decision = decider(agent, _perception(s, drink))
        not getattr(decision, "fallback", False)
        is_correct = decision.action == s.expected
        by_name[s.name] = {
            "attendu": s.expected.value,
            "obtenu": decision.action.value,
            "repli": getattr(decision, "fallback", False),
            "correct": is_correct,
            "description": s.description,
        }
    n = len(by_name)
    resolved_count = sum(1 for r in by_name.values() if not bool(r["repli"]))
    correct_count = sum(1 for r in by_name.values() if bool(r["correct"]))
    return {
        "n": n,
        "taux_resolution": resolved_count / n,
        "taux_justesse": correct_count / n,
        "par_situation": by_name,
    }


def compare_policies() -> dict[str, object]:
    """Tableau comparatif rules / llm / hybrid sur le même jeu."""
    from maree.v3.adapters.chat_stub import StubChat
    from maree.v3.agents.catalog import register_provider

    # le LLM du banc est un stub qui répond « évacuer vers A »
    register_provider(
        "llamacpp",
        StubChat(lambda _r: '{"action": "evacuer", "cible": "A", "confiance": 0.8}'),
    )
    return {
        "rules": run_bench(rules_decider),
        "llm": run_bench(llm_decider),
        "hybrid": run_bench(hybrid_decider),
    }


__all__ = [
    "SITUATIONS",
    "Situation",
    "compare_policies",
    "hybrid_decider",
    "llm_decider",
    "rules_decider",
    "run_bench",
]