"""Graphe de décision LangGraph : le repli doit être visible.

Un run où aucun appel LLM n'aboutit ne doit pas ressembler à un run
hybride. Le graphe replie sur les règles — c'est voulu — mais il le
journalise (`fallback`, `ok`, `error`), et le résumé du run sépare les
tentatives des succès.
"""

from __future__ import annotations

from maree.agents.graph import DecisionGraph
from maree.agents.profiles import get_profile
from maree.agents.triggers import Percept
from maree.domain.geometry import Plan
from maree.domain.intentions import IntentionKind
from maree.memory.store import NullMemory
from maree.ports import ChatMessage, LLMResult


class FailingLLM:
    async def chat(self, messages: list[ChatMessage], *, seed: int, **kwargs) -> LLMResult:
        return LLMResult(
            text="",
            prompt="…",
            seed=seed,
            model="factice",
            ok=False,
            error="APIConnectionError: Connection error.",
        )

    async def embed(self, texts):
        return []


class WorkingLLM:
    async def chat(self, messages: list[ChatMessage], *, seed: int, **kwargs) -> LLMResult:
        return LLMResult(
            text='{"action": "go_exit", "target": "B", "confidence": 0.8}',
            prompt="…",
            seed=seed,
            model="factice",
            ok=True,
        )

    async def embed(self, texts):
        return []


def _percept() -> Percept:
    return Percept(
        tick=10,
        position=(30.0, 20.0),
        zone="Z5",
        smoke_visible=True,
        smoke_intensity=0.6,
        exits_open=frozenset({"A", "B", "C"}),
        exit_density={"A": 0.1, "B": 0.1, "C": 0.1},
    )


def _graph(llm, plan: Plan) -> DecisionGraph:
    return DecisionGraph(
        llm=llm, retriever=None, memory=NullMemory(), plan=plan, max_tokens=64
    )


async def test_un_appel_llm_rate_replie_sur_les_regles_et_le_dit(plan: Plan) -> None:
    intention, state = await _graph(FailingLLM(), plan).decide(
        agent_id="A01",
        profile=get_profile("visiteur"),
        percept=_percept(),
        trigger="fumee_visible",
    )
    # L'intention reste valide : les règles prennent la main.
    assert intention.kind is IntentionKind.GO_EXIT
    assert state["fallback"] is True
    assert state["llm"]["ok"] is False
    assert state["llm"]["error"]


async def test_un_appel_reussi_ne_marque_pas_de_repli(plan: Plan) -> None:
    intention, state = await _graph(WorkingLLM(), plan).decide(
        agent_id="A01",
        profile=get_profile("visiteur"),
        percept=_percept(),
        trigger="fumee_visible",
    )
    assert intention.kind is IntentionKind.GO_EXIT
    assert intention.target == "B"
    assert not state.get("fallback")
    assert state["llm"]["ok"] is True


class LabelLLM:
    """Répond une étiquette de plan au lieu d'un identifiant de sortie."""

    async def chat(self, messages: list[ChatMessage], *, seed: int, **kwargs) -> LLMResult:
        return LLMResult(
            text='{"action": "guide", "target": "Signalétique — la scène principale",'
            ' "confidence": 0.9}',
            prompt="…",
            seed=seed,
            model="factice",
            ok=True,
        )

    async def embed(self, texts):
        return []


async def test_un_guide_avec_une_etiquette_replie_sur_les_regles(plan: Plan) -> None:
    """`guide` mène à une sortie : sa cible doit être un identifiant réel.

    Constaté en hybride : la cible « Signalétique — la scène principale »
    était enregistrée comme croyance de sortie ; au tick suivant, l'agent
    croyait que cette sortie avait fermé et évacuait sur un événement
    inexistant.
    """
    intention, state = await _graph(LabelLLM(), plan).decide(
        agent_id="A01",
        profile=get_profile("securite"),
        percept=_percept(),
        trigger="premiere_decision",
    )
    assert intention.target in plan.exits
    assert state["fallback"] is True


class FollowExitLLM:
    """Répond « suivre la foule vers C » : une sortie dans le champ agent."""

    async def chat(self, messages: list[ChatMessage], *, seed: int, **kwargs) -> LLMResult:
        return LLMResult(
            text='{"action": "follow", "target": "C", "confidence": 0.8}',
            prompt="…",
            seed=seed,
            model="factice",
            ok=True,
        )

    async def embed(self, texts):
        return []


async def test_suivre_une_sortie_devient_y_aller(plan: Plan) -> None:
    """`follow C` se lit « suivre la foule vers C », donc aller à C.

    Sans cette conversion, le moteur cherchait un agent nommé « C », ne le
    trouvait pas, et figeait l'agent sur place : 8 agents LLM sur 12 ne
    sortaient jamais.
    """
    intention, state = await _graph(FollowExitLLM(), plan).decide(
        agent_id="A01",
        profile=get_profile("visiteur"),
        percept=_percept(),
        trigger="annonce",
    )
    assert intention.kind is IntentionKind.GO_EXIT
    assert intention.target == "C"
    assert not state.get("fallback")
