"""Tests du cœur de la simulation (déterminisme, indicateurs, rejeu)."""
from __future__ import annotations

import asyncio
import random

import pytest

from src.config import ProfileSpec, SimulationConfig, WorldSpec
from src.events import new_envelope
from src.metrics.indicators import IndicatorSet, Indicators
from src.orchestrator import Orchestrator
from src.temporal import Scheduler, SimClock

MAX_TICKS = 30


@pytest.fixture(autouse=True)
def _clean_logs():
    """Le journal est append-only (décision 1) : un run a un run_id unique.
    Pour que les tests soient rejouables, on nettoie le répertoire journal
    avant chaque test — en production, le CLI génère des run_id uniques."""
    import shutil

    shutil.rmtree("/tmp/maree_test_logs", ignore_errors=True)
    yield
    shutil.rmtree("/tmp/maree_test_logs", ignore_errors=True)


def _cfg(mode: str = "sync", seed: int = 42) -> SimulationConfig:
    return SimulationConfig(
        run_id=f"test_{mode}_{seed}",
        seed=seed,
        mode=mode,
        max_ticks=MAX_TICKS,
        population=[
            ProfileSpec(name="securite", count=2, kind="llm", model="gemma4-e4b"),
            ProfileSpec(name="visiteur", count=3, kind="llm", model="gemma4-e2b"),
            ProfileSpec(name="foule", count=10, kind="rules"),
        ],
        world=WorldSpec(smoke_tick=5),
        log_dir="/tmp/maree_test_logs",
    )


def test_config_hash_deterministe() -> None:
    a = _cfg()
    b = _cfg()
    assert a.config_hash() == b.config_hash()
    different = _cfg(seed=99)
    assert a.config_hash() != different.config_hash()


def test_horloge_et_ordonnanceur_sync() -> None:
    clock = SimClock(tick_duration_ms=1000)
    sched = Scheduler("sync", clock, random.Random(1))
    sched.register("a_01")
    sched.register("b_02")
    assert {s.agent_id for s in sched.due_agents(0)} == {"a_01", "b_02"}
    now = 5
    sched.register("c_03", think_interval=7)
    c = sched.agents["c_03"]
    assert sched.process(c, now=now) == now  # latence 0 en sync


def test_horloge_et_ordonnanceur_async() -> None:
    clock = SimClock(tick_duration_ms=1000)
    sched = Scheduler("async", clock, random.Random(7), default_think_interval=10)
    sched.register("x_01", think_interval=10)  # interval fixe (pas de jitter)
    first = sched.agents["x_01"]
    # Le jitter est appliqué au register : vérifions l'invariant relatif.
    interval = first.think_interval_ticks
    assert interval >= 10
    sched.schedule_next(first, now=0)
    assert first.next_think_tick == interval
    # En async, process ajoute la latence de traitement.
    assert sched.process(first, now=1) == 1 + first.processing_delay_ticks


def test_indicateurs_convergent() -> None:
    ind = Indicators()
    state = IndicatorSet(
        tick=10,
        beliefs=[("a", "A", True), ("b", "A", True), ("c", "C", True)],
        evacuated=2,
        trapped=0,
        total=3,
        ground_truth_safe_exit="A",
        destinations=[("a", "A"), ("b", "A")],
    )
    res = ind.compute(state)
    assert res["I1_consensus"] > 0.0
    assert res["I2_belief_gap"] == pytest.approx(1 / 3, abs=1e-3)
    assert res["I3_evacuation"]["evacuated"] == 2
    assert res["I5_temporal_violations"] == 0


def test_event_envelope_double_horodatage() -> None:
    ev = new_envelope("run_x", "world.smoke_update", t_prod=10, t_trait=12)
    assert ev.t_prod == 10
    assert ev.t_trait == 12
    assert ev.schema_version == 1
    assert ev.event_id  # UUID généré


def test_rejeu_identique_meme_config() -> None:
    """Deux run dry-run d'une config identique (mêmes graines) produisent le
    même hash d'indicateurs (E3) — le run_id étant l'identité d'instance,
    on le fait varier comme en production (décision 5)."""
    from src.replay import ReplayEngine

    def make_cfg(run_id: str) -> SimulationConfig:
        return _cfg().model_copy(update={"run_id": run_id})

    async def once(run_id: str) -> str:
        cfg = make_cfg(run_id)
        orch = Orchestrator(cfg, dry_run=True, corpus_path="/tmp/empty_corpus")
        await orch.run()
        return ReplayEngine.replay(cfg.run_id, cfg.log_dir).indicator_hash

    h1 = asyncio.run(once("rejeu_a"))
    h2 = asyncio.run(once("rejeu_b"))
    assert h1 == h2


def test_run_sync_termine_sans_erreur() -> None:
    async def go() -> dict:
        cfg = _cfg("sync")
        orch = Orchestrator(cfg, dry_run=True, corpus_path="/tmp/empty_corpus")
        return await orch.run()

    summary = asyncio.run(go())
    # dry-run : appels logiques comptés, mais zéro token réseau réel (E4).
    assert summary["calls"] > 0
    assert summary["tokens_in"] == 0
    assert summary["tokens_out"] == 0
    assert summary["temporal_violations"] == 0


def test_run_async_termine_sans_erreur() -> None:
    async def go() -> dict:
        cfg = _cfg("async")
        orch = Orchestrator(cfg, dry_run=True, corpus_path="/tmp/empty_corpus")
        return await orch.run()

    summary = asyncio.run(go())
    assert summary["mode"] == "async"

def test_inspection_agent_regles_et_inconnu() -> None:
    """D2 : inspecter un agent à règles ne doit pas planter (perception
    reconstruite) et la réponse doit être réellement diffusée (broadcast
    awaité), y compris pour un identifiant inconnu."""
    cfg = _cfg().model_copy(
        update={
            "run_id": "test_inspect",
            "max_ticks": 3,
            "population": [ProfileSpec(name="foule", count=2, kind="rules")],
        }
    )
    orch = Orchestrator(cfg, dry_run=True, corpus_path="/tmp/empty_corpus")
    sent: list[dict] = []

    async def collect(payload: dict) -> None:
        sent.append(payload)

    orch.ws.broadcast = collect  # type: ignore[method-assign]

    async def go() -> None:
        await orch._inspect("foule_01")  # avant tout tick
        await orch._inspect("inexistant")

    asyncio.run(go())
    assert sent[0]["type"] == "inspection"
    assert sent[0]["agent_id"] == "foule_01"
    assert sent[0]["explanation"]["kind"] == "rules"
    assert sent[1]["type"] == "inspection"
    assert sent[1]["error"] == "unknown_agent"


def test_event_types_traçabilité_acceptés():
    """C6/F4 : les événements ajoutés à la chaîne doivent être versionnés."""
    v = new_envelope("run_oracle", "oracle.violation", t_prod=3, t_trait=3,
                     agent_id="a1", data={"detail": "test"})
    assert v.type == "oracle.violation"
    c = new_envelope("run_ctrl", "control.inject", t_prod=4, t_trait=4,
                     data={"command": "announcement"})
    assert c.type == "control.inject"


def test_oracle_detecte_un_message_non_arrivé():
    """C6 : une décision qui citerait un message arrivé plus tard est une
    violation. Le vérificateur n'est pas un décor : il produit bien I5 > 0
    quand la chronologie est incohérente."""
    from src.oracle import TemporalOracle

    oracle = TemporalOracle()
    oracle.check_decisions(
        tick=5,
        decisions=[{"agent_id": "a1"}],
        messages_by_agent={"a1": [(7, "message futur")]},
    )
    assert len(oracle.violations) == 1
    assert oracle.violations[0].agent_id == "a1"
    with pytest.raises(AssertionError):
        oracle.assert_clean()


def test_f6_offsets_sources_et_b4_causation() -> None:
    """F6/B4 : chaque indicateur cite des offsets Kafka réels, et les
    événements ont une chaîne causale (message -> décision -> mouvement)."""
    from src.replay import ReplayEngine

    from src.llm_gateway import LLMCallResult

    cfg = _cfg("sync").model_copy(update={"run_id": "test_f6_b4"})
    orch = Orchestrator(cfg, dry_run=True, corpus_path="/tmp/empty_corpus")

    async def fake_chat(model, messages, *, temperature=0.3, max_tokens=None):
        return LLMCallResult(
            text='{"explanation":"je préviens mon voisin","action":"stay",'
                 '"target_zone":"scene","exit_choice":null,'
                 '"message":"restons groupés"}',
            call_id=1, model=model, duration_ms=5,
        )

    orch.gateway.chat = fake_chat  # type: ignore[method-assign]
    asyncio.run(orch.run())

    events = ReplayEngine.load(cfg.run_id, cfg.log_dir)
    decisions = [e for e in events if e.type == "agent.decision"]
    messages = [e for e in events if e.type == "agent.message"]
    indicators = [e for e in events if e.type == "metrics.indicators"]

    assert decisions and messages
    decision_ids = {e.event_id for e in decisions}
    assert any(e.causation_id for e in decisions)
    assert any(m.causation_id in decision_ids for m in messages)

    assert any(i.data.get("sources") for i in indicators)
    for ind in indicators:
        for topic, rng in ind.data.get("sources", {}).items():
            assert topic in {
                "world.events", "agent.decisions", "metrics.indicators",
                "control.commands", "dlq.invalid",
            }
            assert isinstance(rng["from"], int)
            assert rng["from"] <= rng["to"]
            assert rng["events"] >= 1

    # Clic Godot -> événements bruts : on répond avec les parents causaux.
    sent: list[dict] = []

    async def collect(payload: dict) -> None:
        sent.append(payload)

    orch.ws.broadcast = collect  # type: ignore[method-assign]
    tick = indicators[0].t_prod
    asyncio.run(orch._inspect_indicator(tick, "I1"))
    assert sent and sent[0]["type"] == "indicator_events"
    assert sent[0]["events"]
    assert any(e["causation_id"] for e in sent[0]["events"])


def test_c7_latence_llm_devient_delai_de_ticks() -> None:
    """C7/C6 : une latence de 2,5 s à 1 s/tick doit produire 3 ticks de
    traitement, et le message ne doit être délivré qu'à l'arrivée."""
    from src.llm_gateway import LLMCallResult
    from src.replay import ReplayEngine

    cfg = _cfg("async").model_copy(
        update={
            "run_id": "test_c7",
            "max_ticks": 15,
            "tick_duration_ms": 1000,
            "world": WorldSpec(smoke_tick=5),
        }
    )
    orch = Orchestrator(cfg, dry_run=True, corpus_path="/tmp/empty_corpus")

    async def slow_chat(model, messages, *, temperature=0.3, max_tokens=None):
        return LLMCallResult(
            text='{"explanation":"je préviens","action":"stay",'
                 '"target_zone":"scene","exit_choice":null,'
                 '"message":"attention"}',
            call_id=1, model=model, duration_ms=2500,
        )

    orch.gateway.chat = slow_chat  # type: ignore[method-assign]
    summary = asyncio.run(orch.run())
    assert summary["processing_delay_ticks"]["median"] == 3.0
    assert summary["processing_delay_ticks"]["max"] == 3
    assert summary["llm_latency_ms"]["median"] == 2500.0
    assert summary["temporal_violations"] == 0

    events = ReplayEngine.load(cfg.run_id, cfg.log_dir)
    messages = [e for e in events if e.type == "agent.message"]
    assert messages
    assert all(m.t_trait == m.t_prod + 3 for m in messages)


def test_e3_reconstruction_depuis_journal_seul() -> None:
    """E3 : prompt, graine et sortie brute sont journalisés, et chaque
    décision LLM est reconstruite sans rappeler le modèle."""
    from src.llm_gateway import LLMCallResult
    from src.replay import reconstruct_decisions

    cfg = _cfg("sync").model_copy(update={"run_id": "test_e3"})
    orch = Orchestrator(cfg, dry_run=True, corpus_path="/tmp/empty_corpus")

    async def fake_chat(model, messages, *, temperature=0.3, max_tokens=None):
        return LLMCallResult(
            text='{"explanation":"sortir par B","action":"move",'
                 '"target_zone":"nord","exit_choice":"B",'
                 '"message":"suivez-moi vers B"}',
            call_id=1, model=model, duration_ms=12,
            tokens_in=120, tokens_out=30,
        )

    orch.gateway.chat = fake_chat  # type: ignore[method-assign]
    asyncio.run(orch.run())
    check = reconstruct_decisions(cfg.run_id, cfg.log_dir)
    assert check["n_decisions"] > 0
    assert check["trace_complete"] == check["n_decisions"]
    assert check["matching"] == check["n_decisions"], check["mismatches"][:2]


def test_b3_diversite_justifications_embeddings() -> None:
    """B3 : la diversité compare les justifications par embeddings, avec
    une séparation même modèle / modèles différents."""
    cfg = _cfg().model_copy(update={"run_id": "test_b3_div"})
    orch = Orchestrator(cfg, dry_run=True, corpus_path="/tmp/empty_corpus")
    for i, agent in enumerate(orch.llm_agents):
        orch.runtime[agent.agent_id].last_explanation = {
            "kind": "llm",
            "reasoning": f"justification {i}",
        }

    async def fake_embed(texts):
        return [[1.0, 0.0] if i % 2 == 0 else [0.0, 1.0] for i, _ in enumerate(texts)]

    orch.gateway.embed = fake_embed  # type: ignore[method-assign]
    result = asyncio.run(orch._compute_justification_diversity())
    assert result["n"] == len(orch.llm_agents)
    assert result["mean_pairwise_cosine_distance"] > 0.5
    assert result["same_model"] > 0.5
    assert result["cross_model"] >= 0.5
    assert result["degraded"] is False
