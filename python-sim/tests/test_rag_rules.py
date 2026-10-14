"""Tests du RAG (F1, F2, C6) et de l'agent à règles (E1)."""
from __future__ import annotations

import asyncio
import random
from pathlib import Path

import pytest

from src.agents.base import Perception
from src.agents.llm_agent import LLMAgent
from src.agents.rules_agent import RulesAgent
from src.rag.rag import RagClient


def _write_passage(root: Path, collection: str, name: str, body: str, meta: str = "") -> None:
    d = root / collection
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\ntitle: {name}\n{meta}---\n{body}", encoding="utf-8"
    )


def _agent(profile_id: str, profile_name: str, model: str) -> LLMAgent:
    return LLMAgent(
        agent_id=profile_id,
        profile_name=profile_name,
        model=model,
        priority="",
        knows="",
        temperature=0.3,
    )


@pytest.mark.asyncio
async def test_rag_controle_acces_profil(tmp_path: Path) -> None:
    """Décision 15 : un passage autorisé pour 'securite' n'est pas retrouvé
    par un visiteur."""
    _write_passage(
        tmp_path, "consignes_securite", "protocole",
        "Le protocole impose d'aller vers la sortie C en cas de fumée.",
        "allowed_profiles: [securite]\navailable_tick: 0\nimportance: 0.9\n",
    )
    rag = RagClient()
    assert rag.ingest_directory(tmp_path) == 1

    securite = _agent("securite_01", "securite", "gemma4-e4b")
    visiteur = _agent("visiteur_01", "visiteur", "gemma4-e2b")

    p = Perception(tick=5, zone="scene", smoke_seen=True)
    out_sec = await rag.retrieve_for(securite, p)
    out_vis = await rag.retrieve_for(visiteur, p)
    assert "protocole" in out_sec
    assert "protocole" not in out_vis
    assert securite.last_rag  # traçabilité F2


@pytest.mark.asyncio
async def test_rag_date_disponibilite_c6(tmp_path: Path) -> None:
    """Décision 15 / C6 : un passage daté du futur n'est pas retrouvé."""
    _write_passage(
        tmp_path, "annonces", "communique",
        "Le communiqué officiel sera diffusé à 20h00.",
        "allowed_profiles: [*]\navailable_tick: 200\nimportance: 0.9\n",
    )
    rag = RagClient()
    rag.ingest_directory(tmp_path)
    agent = _agent("visiteur_01", "visiteur", "gemma4-e2b")
    out = await rag.retrieve_for(
        agent, Perception(tick=10, zone="scene", smoke_seen=False)
    )
    assert out == ""


def test_rules_agent_decide_respecte_perception() -> None:
    """Baseline E1 : l'agent à règles répond à la perception sans LLM."""
    rng = random.Random(0)
    agent = RulesAgent(agent_id="foule_01", profile_name="foule", rng=rng)

    intent = asyncio.run(
        agent.decide(
            Perception(
                tick=1, zone="scene", smoke_seen=False,
                visible_neighbors=["foule_02"], exits_known=["A"],
            )
        )
    )
    assert intent.action in {"move", "stay", "evacuate"}
    assert agent.explanation(
        Perception(tick=1, zone="scene", smoke_seen=False)
    )["kind"] == "rules"