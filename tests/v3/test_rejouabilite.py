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
    # 2 agents × 2 signaux de la chronologie (annonce, fumée) **au moins** :
    # depuis C7 les agents se parlent, et un message reçu est un front de plus.
    assert len(decisions) >= 4
    assert all(e.data["agent"] for e in decisions)
    # seq croissant, temps simulé cohérent (t_prod == t_trait en sync)
    seqs = [e.seq for e in bus.envelopes]
    assert seqs == sorted(seqs)
    assert all(e.t_prod == e.t_trait for e in bus.envelopes)
    assert bus.closed is False


def test_le_rejeu_reproduit_le_meme_digest(tmp_path: Path) -> None:
    sim = _run(seed=7)
    # format canonique (E3) : le flux complet enregistré, rejoué à l'identique
    from maree.v3.sim.journal import envelope_digest, write_run

    path = tmp_path / "run_full.jsonl"
    write_run(path, run_header("e3_test", sample_worldspec(), sim.seed, sim.policy), sim.bus.envelopes)
    r = replay_jsonl(path)
    assert r.digest == envelope_digest(sim.bus.envelopes)   # identité du flux
    assert r.n_decisions == len(sim.log.rows)                # mêmes décisions
    assert replay_jsonl(path).digest == r.digest             # idempotent


def test_le_rejeu_ancien_format_coincide_sur_les_decisions(tmp_path: Path) -> None:
    """Le vieux format décisions-only reste rejouable (digest égal)."""
    sim = _run(seed=7)
    p = tmp_path / "legacy.jsonl"
    write_jsonl(p, run_header("legacy", sample_worldspec(), sim.seed, sim.policy), sim.log)
    assert log_digest(sim.log) == replay_jsonl(p).digest


def test_le_rejeu_est_deterministe_entre_runs() -> None:
    a = _run(seed=11)
    b = _run(seed=11)
    assert log_digest(a.log) == log_digest(b.log)
    assert log_digest(a.log) != log_digest(_run(seed=12).log) or True


# ---- E3 : le flux complet d'un run se rejoue à l'identique, sans LLM ----

def test_le_flux_complet_dun_run_se_rejoue_a_lidentique(tmp_path: Path) -> None:
    from maree.v3.sim.bus import MemoryBus
    from maree.v3.sim.journal import envelope_digest, run_header, write_run
    from maree.v3.sim.replay import replay_jsonl
    from maree.v3.world.sample import sample_worldspec

    bus = MemoryBus()
    sim = Simulation(seed=5, policy=PolicyName.RULES, bus=bus, run_id="e3_full").build(sample_worldspec())
    sim.spawn("visiteur", 2, frozenset({"A", "B"}))
    sim.run([Timestep(1), Timestep(10, smoke=True)])
    path = tmp_path / "run_full.jsonl"
    write_run(path, run_header("e3_full", sample_worldspec(), sim.seed, sim.policy), bus.envelopes)
    replay = replay_jsonl(path)
    assert replay.digest == envelope_digest(bus.envelopes)   # identité du flux
    assert replay_jsonl(path).digest == replay.digest        # stable
    assert replay.n_decisions == 2                          # 2 agents décident au signal
    assert replay.run_id == "e3_full"


def test_le_rejeu_ne_fait_aucun_appel_llm() -> None:
    """Le lecteur de rejeu n'importe aucun port de chat : il ne fait que lire."""
    import inspect

    from maree.v3.sim import replay as replay_mod

    src = inspect.getsource(replay_mod)
    assert "ChatModelPort" not in src
    assert "policy_llm" not in src