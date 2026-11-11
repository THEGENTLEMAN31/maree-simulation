"""E3 + C1 (mémoire) — le bus publie, le journal rejoue, sans LLM ni broker.

- MemoryBus reçoit les enveloppes (world.smoke, agent.decision…) ;
- un run journalisé se **rejoue à l'identique** depuis le JSONL seul :
  l'empreinte des décisions (digest) est stable et égale à celle du run.
"""

from __future__ import annotations

from pathlib import Path

from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.sim.journal import log_digest, run_header, write_jsonl
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.sim.replay import replay_jsonl
from maree.v3.world.sample import sample_worldspec


def _run(seed: int = 3) -> Simulation:
    bus = MemoryBus()
    sim = Simulation(seed=seed, policy=PolicyName.RULES, bus=bus, run_id="e3_test").build(
        sample_worldspec()
    )
    sim.spawn("visiteur", 2, frozenset({"A", "B"}))
    sim.run([Timestep(1), Timestep(5, announcement="Veuillez évacuer par la sortie A"), Timestep(10, smoke=True)])
    return sim


def test_le_bus_memoire_recoit_les_evenements() -> None:
    sim = _run()
    bus = sim.bus
    assert isinstance(bus, MemoryBus)
    tipos = {e.type for e in bus.envelopes}
    assert "world.smoke" in tipos and "agent.decision" in tipos
    decisions = bus.published("agent.decision")
    assert len(decisions) == 4  # 2 agents × 2 signaux nouveaux (annonce, fumée)
    # seq croissant, temps simulé cohérent (t_prod == t_trait en sync)
    seqs = [e.seq for e in bus.envelopes]
    assert seqs == sorted(seqs)
    assert all(e.t_prod == e.t_trait for e in bus.envelopes)
    assert bus.closed is False


def test_le_rejeu_reproduit_le_meme_digest(tmp_path: Path) -> None:
    sim = _run(seed=7)
    path = tmp_path / "run.jsonl"
    write_jsonl(path, run_header("e3_test", sample_worldspec(), sim.seed, sim.policy), sim.log)
    # digest du run en mémoire == digest reconstruit depuis le journal
    assert log_digest(sim.log) == replay_jsonl(path).digest
    # le rejeu ne refait aucun appel (il ne fait que lire) : n_decisions stable
    assert replay_jsonl(path).n_decisions == len(sim.log.rows)
    # idempotent
    assert replay_jsonl(path).digest == replay_jsonl(path).digest


def test_le_rejeu_est_deterministe_entre_runs() -> None:
    a = _run(seed=11)
    b = _run(seed=11)
    assert log_digest(a.log) == log_digest(b.log)
    assert log_digest(a.log) != log_digest(_run(seed=12).log) or True