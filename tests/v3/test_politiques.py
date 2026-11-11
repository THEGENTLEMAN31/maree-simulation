"""Semaine 4 — politiques ``llm`` / ``hybrid``, passerelle, traces, repli.

Critère (roadmap S4) : deux providers interchangeables (prouvé ici avec un
stub et un adapter-openai via client factice) ; un repli sur règles avec
cause nommée quand le LLM échoue ou vise une sortie inconnue ; des traces
complètes (provider, modèle, tokens) ; hybride qui ne monte au LLM qu'en
ambiguïté.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from maree.v3.adapters.chat_openai import OpenAICompatibleChat
from maree.v3.adapters.chat_stub import StubChat
from maree.v3.agents.agent import make_agent
from maree.v3.agents.appraisal import Action, appraise
from maree.v3.agents.catalog import chat_for, register_provider
from maree.v3.agents.knowledge import Source
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.policy_llm import LLMPolicy, hybrid_decide
from maree.v3.agents.state import State
from maree.v3.core.ids import AgentId, ZoneId
from maree.v3.core.ports import LLMMessage, LLMRequest


def _perception(tick: int = 10, *, smoke: bool = False, threat: float = 0.0) -> Perception:
    return Perception(
        tick=tick,
        zone=ZoneId("z1"),
        state=State(),
        smoke_visible=smoke,
        threat=threat,
        heard=(),
        seen_agents=(),
        exits_visible=frozenset(),
    )


def _visitor(known: frozenset[str] = frozenset({"A", "B"})):
    return make_agent(uid=1, archetype="visiteur", known_exits=known)


def _appr(agent, perc):
    return appraise(
        perception=perc,
        traits=agent.traits,
        knowledge=agent.knowledge,
        social=agent.social,
        name=agent.name,
    )


def _llm_evacuer():
    return StubChat(lambda _req: '{"action": "evacuer", "cible": "B", "confiance": 0.9}')


def _llm_bavard():
    return StubChat(lambda _req: 'Réfléchissons… {"action": "evacuer", "cible": "A", "confiance": 0.8}"')


def test_le_stub_est_un_provider_interchangeable() -> None:
    agent = _visitor()
    perc = _perception(smoke=True)
    d = LLMPolicy(port=_llm_evacuer()).decide(
        perception=perc,
        knowledge=agent.knowledge,
        social=agent.social,
        traits=agent.traits,
        appraisal=_appr(agent, perc),
        known_exits=agent.known_exits,
        name=agent.name,
    )
    assert d.action == Action.EVACUER
    assert d.target == "B"
    assert d.fallback is False
    trace = d.llm_trace
    assert trace is not None
    assert trace.response.provider  # non vide (stub injecté)
    assert trace.response.completion_tokens > 0
    assert len(trace.request.messages) == 2


def test_une_reponse_bavarde_est_parsee() -> None:
    agent = _visitor()
    perc = _perception(smoke=True)
    d = LLMPolicy(port=_llm_bavard()).decide(
        perception=perc,
        knowledge=agent.knowledge,
        social=agent.social,
        traits=agent.traits,
        appraisal=_appr(agent, perc),
        known_exits=agent.known_exits,
        name=agent.name,
    )
    assert d.action == Action.EVACUER
    assert d.target == "A"


def test_cible_inconnue_replie_sur_les_regles() -> None:
    agent = _visitor()
    perc = _perception(smoke=True)
    stub = StubChat(lambda _req: '{"action": "evacuer", "cible": "Z", "confiance": 0.9}')
    d = LLMPolicy(port=stub).decide(
        perception=perc,
        knowledge=agent.knowledge,
        social=agent.social,
        traits=agent.traits,
        appraisal=_appr(agent, perc),
        known_exits=agent.known_exits,
        name=agent.name,
    )
    assert d.fallback is True
    assert d.llm_trace is not None


def test_reponse_invalide_replie_sur_les_regles() -> None:
    agent = _visitor()
    perc = _perception(smoke=True)
    stub = StubChat(lambda _req: "pas du json")
    d = LLMPolicy(port=stub).decide(
        perception=perc,
        knowledge=agent.knowledge,
        social=agent.social,
        traits=agent.traits,
        appraisal=_appr(agent, perc),
        known_exits=agent.known_exits,
        name=agent.name,
    )
    assert d.fallback is True
    assert d.fallback_cause == "unparseable"


def test_hybride_ne_monte_au_llm_quen_ambiguite() -> None:
    # menace modérée (0.5) sans fumée : les règles restent, l'ambiguïté monte au LLM
    register_provider("llamacpp", StubChat(lambda _r: '{"action": "evacuer", "cible": "A", "confiance": 0.8}'))
    agent = _visitor()
    perc = _perception(tick=5, threat=0.5)
    d = hybrid_decide(
        perception=perc,
        knowledge=agent.knowledge,
        social=agent.social,
        traits=agent.traits,
        appraisal=_appr(agent, perc),
        known_exits=agent.known_exits,
        name=agent.name,
    )
    assert d.fallback is False
    assert d.llm_trace is not None  # il y a bien eu un appel LLM


def test_hybride_reste_aux_regles_sans_ambiguite() -> None:
    register_provider("llamacpp", StubChat(lambda _r: _r.messages[0].content[:40]))
    agent = _visitor()
    perc = _perception(tick=5)  # aucune menace, aucun signal
    d = hybrid_decide(
        perception=perc,
        knowledge=agent.knowledge,
        social=agent.social,
        traits=agent.traits,
        appraisal=_appr(agent, perc),
        known_exits=agent.known_exits,
        name=agent.name,
    )
    assert d.llm_trace is None  # pas d'appel LLM : les règles suffisent


def test_adaptateur_openai_parle_le_dialecte() -> None:
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kw: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{"action":"rester"}'))],
                    usage=SimpleNamespace(prompt_tokens=42, completion_tokens=7),
                )
            )
        )
    )
    adapter = OpenAICompatibleChat(base_url="http://x", client=fake_client)
    resp = adapter.complete(
        LLMRequest(
            messages=(LLMMessage("system", "s"),),
            model="m",
            temperature=0.0,
            max_tokens=8,
            seed=1,
            provider="p",
        )
    )
    assert resp.ok is True
    assert resp.prompt_tokens == 42


def test_catalogue_resout_et_rejette_les_inconnus() -> None:
    register_provider("stub", StubChat())
    spec = chat_for("stub")
    assert spec[1].resolved.startswith("stub")
    with pytest.raises(KeyError):
        from maree.v3.agents.catalog import resolve_model

        resolve_model("n-existe-pas")


def test_le_prompt_transporte_les_messages_recus() -> None:
    """Le LLM doit pouvoir raisonner sur ce qu'il vient d'entendre."""
    from maree.v3.agents.policy_llm import build_inputs

    a = _visitor()
    perc = Perception(
        tick=10,
        zone=ZoneId("z1"),
        state=State(),
        heard=(Message("B est bloquée", AgentId(3), 10),),
        seen_agents=(),
        exits_visible=frozenset(),
    )
    inputs = build_inputs(
        perception=perc,
        traits=a.traits,
        appraisal=_appr(a, perc),
        knowledge=a.knowledge,
    )
    assert "messages_recus" in inputs
    assert "B est bloquée" in str(inputs["messages_recus"])


def test_le_prompt_transporte_le_contexte_rag() -> None:
    """F1 : les décisions LLM s'appuient sur des passages retrouvés."""
    from maree.v3.agents.policy_llm import build_inputs

    a = _visitor()
    perc = Perception(tick=100, zone=ZoneId("z1"), state=State(), seen_agents=(), exits_visible=frozenset())
    inputs = build_inputs(
        perception=perc,
        traits=a.traits,
        appraisal=_appr(a, perc),
        knowledge=a.knowledge,
        rag=[{"id": "plan_A", "titre": "Sortie A", "collection": "plan", "contenu": "la sortie A est au nord"}],
    )
    assert inputs["contexte_rag"]
    assert "plan_A" in str(inputs["contexte_rag"])


def test_le_prompt_transporte_la_memoire_personnelle() -> None:
    """Le « memorandum » : les reçus de l'agent sont visibles par le LLM."""
    from maree.v3.agents.memory import Memory
    from maree.v3.agents.policy_llm import build_inputs

    a = _visitor()
    a.memory = Memory()
    a.memory.learn("B est bloquée", Source.ENTENDU, tick=10, confidence=0.8)
    perc = Perception(tick=11, zone=ZoneId("z1"), state=State(), seen_agents=(), exits_visible=frozenset())
    inputs = build_inputs(
        perception=perc,
        traits=a.traits,
        appraisal=_appr(a, perc),
        knowledge=a.knowledge,
        memory=a.memory,
    )
    memo = str(inputs["memoire"])
    assert "B est bloquée" in memo
    assert "entendu" in memo and "0.8" in memo