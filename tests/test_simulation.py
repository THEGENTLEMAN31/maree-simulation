"""Intégration : la boucle à trois horloges, sans GPU ni JuPedSim.

On injecte une physique factice et une population **entièrement à règles**.
Ce que le test prouve :

    * le run se termine et laisse un journal complet ;
    * deux runs de même graine produisent exactement les mêmes indicateurs ;
    * aucune décision LLM n'est prise quand la population est « rules ».

C'est le test qui empêche la régression la plus coûteuse : un run qui
appelle le LLM 60 fois par tick.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from maree.adapters.bus import InMemoryBus
from maree.adapters.journal.jsonl import JsonlJournal
from maree.domain.geometry import Plan
from maree.domain.ids import AgentId, Point
from maree.engine.replay import indicators_hash
from maree.engine.simulation import PopulationEntry, RunConfig, Simulation
from maree.memory.store import EventSourcedMemory
from maree.ports import Destination, LLMResult


class FakePhysics:
    """Déplacement en ligne droite vers la destination, 2 m par tick."""

    def __init__(self, plan: Plan, speed_per_step: float = 0.01) -> None:
        self._plan = plan
        self._speed = speed_per_step
        self._pos: dict[AgentId, Point] = {}
        self._dest: dict[AgentId, Destination] = {}
        self._gone: set[AgentId] = set()
        self._closed: set[str] = set()

    def _target(self, destination: Destination) -> Point | None:
        if destination.kind == "exit" and destination.exit_id:
            return self._plan.exit(destination.exit_id).center
        if destination.kind == "point":
            return destination.point
        if destination.kind == "agent" and destination.agent_id:
            return self._pos.get(destination.agent_id)
        return None

    def add_agent(self, agent_id: AgentId, position: Point, destination: Destination) -> None:
        self._pos[agent_id] = position
        self._dest[agent_id] = destination

    def set_destination(self, agent_id: AgentId, destination: Destination) -> None:
        self._dest[agent_id] = destination

    def remove_agent(self, agent_id: AgentId) -> None:
        self._gone.add(agent_id)

    def step(self) -> None:
        for agent_id, position in list(self._pos.items()):
            if agent_id in self._gone:
                continue
            destination = self._dest.get(agent_id)
            target = self._target(destination) if destination else None
            if target is None:
                continue
            dx, dy = target[0] - position[0], target[1] - position[1]
            distance = math.hypot(dx, dy)
            if distance < 0.35:
                if destination and destination.kind == "exit":
                    self._gone.add(agent_id)
                continue
            ratio = min(1.0, self._speed / distance)
            self._pos[agent_id] = (position[0] + dx * ratio, position[1] + dy * ratio)

    def positions(self) -> dict[AgentId, Point]:
        return {a: p for a, p in self._pos.items() if a not in self._gone}

    def evacuated(self) -> set[AgentId]:
        return set(self._gone)

    def close_exit(self, exit_id: str) -> None:
        self._closed.add(exit_id)

    @property
    def agent_count(self) -> int:
        return len(self._pos) - len(self._gone)


class CountingLLM:
    """Ne doit jamais être appelé dans ce test."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, *, seed, **kwargs):
        self.calls += 1
        raise AssertionError("un agent à règles a appelé le LLM")

    async def embed(self, texts):
        raise AssertionError("aucun embedding attendu")


def _config(run_id: str, *, seed: int = 0, ticks: int = 40) -> RunConfig:
    return RunConfig(
        run_id=run_id,
        seed=seed,
        max_ticks=ticks,
        smoke_tick=3,
        smoke_position=(44.0, 15.0),
        smoke_radius=15.0,
        close_exit=None,
        announcement_tick=6,
        announcement="Évacuation.",
        population=(
            PopulationEntry("visiteur", 3, "rules"),
            PopulationEntry("habitue", 2, "rules"),
            PopulationEntry("famille", 2, "rules"),
            PopulationEntry("vendeur", 1, "rules"),
        ),
        narrative_every=5,
    )


async def _run(tmp_path: Path, run_id: str, *, seed: int = 0):
    plan = Plan.from_dict(
        __import__("yaml").safe_load(
            Path("configs/world/port_aubel.yaml").read_text("utf-8")
        )
    )
    journal = JsonlJournal(tmp_path)
    bus = InMemoryBus()
    llm = CountingLLM()
    simulation = Simulation(
        config=_config(run_id, seed=seed),
        plan=plan,
        physics=FakePhysics(plan),
        llm=llm,
        retriever=None,
        memory=EventSourcedMemory(n_exits=len(plan.exits)),
        journal=journal,
        bus=bus,
        narrator=None,
    )
    result = await simulation.run()
    return result, journal, bus, llm


async def test_run_se_termine_et_journalise(tmp_path: Path) -> None:
    result, journal, bus, llm = await _run(tmp_path, "run_a")

    assert result.ticks >= 1
    assert result.indicators
    assert result.llm_calls == 0
    assert llm.calls == 0

    events = journal.read("run_a")
    types = [str(e.type) for e in events]
    assert "run.started" in types
    assert "run.ended" in types
    assert "metrics.indicators" in types
    assert [e.seq for e in events] == sorted(e.seq for e in events)
    assert len(bus.published) == len(events)


async def test_tous_les_agents_finissent_par_sortir(tmp_path: Path) -> None:
    result, _, _, _ = await _run(tmp_path, "run_b")
    last = result.indicators[-1]
    assert last.i3_evacuated == pytest.approx(1.0)
    assert last.counts["remaining"] == 0


async def test_deux_runs_de_meme_graine_sont_identiques(tmp_path: Path) -> None:
    first, journal_a, _, _ = await _run(tmp_path, "run_c1", seed=7)
    second, journal_b, _, _ = await _run(tmp_path, "run_c2", seed=7)

    assert indicators_hash(journal_a.read("run_c1")) == indicators_hash(
        journal_b.read("run_c2")
    )
    assert [i.to_dict() for i in first.indicators] == [
        i.to_dict() for i in second.indicators
    ]


async def test_graines_differentes_changent_le_run(tmp_path: Path) -> None:
    first, _, _, _ = await _run(tmp_path, "run_d1", seed=1)
    second, _, _, _ = await _run(tmp_path, "run_d2", seed=2)
    assert [i.to_dict() for i in first.indicators] != [
        i.to_dict() for i in second.indicators
    ]


async def test_la_fumee_puis_lannonce_declenchent_des_decisions(tmp_path: Path) -> None:
    _, journal, _, _ = await _run(tmp_path, "run_e")
    decisions = [e for e in journal.read("run_e") if str(e.type) == "agent.decision"]
    assert len(decisions) >= 4  # au moins une par agent
    reasons = {e.data.get("trigger") for e in decisions}
    assert "fumee_visible" in reasons or "annonce" in reasons


class GuideLLM:
    """Un agent de sécurité qui « guide » : son métier, sans danger."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, *, seed: int, **kwargs) -> LLMResult:
        self.calls += 1
        return LLMResult(
            text='{"action": "guide", "target": "A", "confidence": 0.9}',
            prompt="…",
            seed=seed,
            model="factice",
            ok=True,
        )

    async def embed(self, texts):
        return []


async def test_un_guide_sans_danger_ne_diffuse_pas_d_alerte(tmp_path: Path) -> None:
    """Un guide qui n'a rien vu ne doit pas faire évacuer ses voisins.

    Constaté en hybride : au tick 1, deux agents de sécurité choisissaient
    `guide` (leur rôle), `_diffuse` transformait cela en « il faut sortir
    par… », et comme tout message reçu vaut signal de danger, la foule
    sortait avant la fumée de t10 (6 à 12 sorties à t9).
    """
    plan = Plan.from_dict(
        __import__("yaml").safe_load(
            Path("configs/world/port_aubel.yaml").read_text("utf-8")
        )
    )
    config = RunConfig(
        run_id="run_guide",
        seed=0,
        max_ticks=10,
        smoke_tick=10,
        smoke_position=(44.0, 15.0),
        smoke_radius=15.0,
        close_exit=None,
        announcement_tick=None,
        announcement=None,
        population=(PopulationEntry("securite", 2, "llm"),),
        narrative_every=5,
    )
    journal = JsonlJournal(tmp_path)
    simulation = Simulation(
        config=config,
        plan=plan,
        physics=FakePhysics(plan),
        llm=GuideLLM(),
        retriever=None,
        memory=EventSourcedMemory(n_exits=len(plan.exits)),
        journal=journal,
        bus=InMemoryBus(),
        narrator=None,
    )
    result = await simulation.run()
    assert result.llm_ok > 0, "les agents LLM n'ont pas décidé"

    events = journal.read("run_guide")
    avant = [
        e for e in events if str(e.type) == "agent.message.sent" and e.t_prod < 10
    ]
    assert not avant, "un guide a diffusé une alerte avant la fumée"
    sorties = [e for e in events if str(e.type) == "agent.evacuated" and e.t_prod < 10]
    assert not sorties, "des agents sont sortis avant la fumée"
