#!/usr/bin/env python
"""Pipeline v3 réelle : monde → agents → vrai LLM → mémoire.

Déroule sur le serveur llama projet (MAREE_LLM_URL, défaut 8081) un run
hybride sur une foule mixte, puis une paire de jumeaux en politique ``llm``
pour montrer que la divergence vient de la mémoire personnelle. Écrit un
journal JSONL rejouable dans ``runs/v3/``.

Usage : MAREE_LLM_URL=<url> uv run python scripts/v3_pipeline.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("MAREE_LLM_URL", "http://127.0.0.1:8081/v1")

from maree.v3 import bootstrap
from maree.v3.agents.perception import Message
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import PolicyName
from maree.v3.sim.journal import run_header, write_jsonl
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.world.sample import sample_worldspec

RUNS = Path(__file__).resolve().parents[1] / "runs" / "v3"


def _journal(sim: Simulation, run_id: str) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    world = sample_worldspec()
    header = run_header(run_id, world, sim.seed, sim.policy)
    write_jsonl(RUNS / f"{run_id}.jsonl", header, sim.log)
    print(f"journal : {RUNS / run_id}.jsonl")


def _foule_hybride(seed: int) -> None:
    print("=" * 78)
    print("RUN 1 — foule mixte, politique hybride (règles + LLM réel)")
    print("=" * 78)
    sim = Simulation(seed=seed, policy=PolicyName.HYBRID).build(sample_worldspec())
    sim.spawn("habitue", 2, frozenset({"A", "B", "C"}))
    sim.spawn("visiteur", 3, frozenset({"A"}))
    ts = [
        Timestep(1),
        Timestep(5, announcement="Veuillez évacuer immédiatement par la sortie A"),
        Timestep(10, smoke=True, messages=(
            (3, Message("la sortie B est praticable", AgentId(99), 10)),
            (4, Message("la sortie B est praticable", AgentId(99), 10)),
        )),
    ]
    t0 = time.time()
    log = sim.run(ts)
    dt = time.time() - t0
    print(log.as_text())
    calls = sum(1 for r in log.rows if r.llm_model)
    replis = sum(1 for r in log.rows if r.fallback)
    print(f"\n{len(log.rows)} décisions, {calls} appels LLM, {replis} replis, {dt:.1f}s murale.")
    _journal(sim, "v3_foule_hybride")


def _jumeaux_llm(seed: int) -> None:
    print("=" * 78)
    print("RUN 2 — jumeaux identiques, politique LLM, messages personnels différents")
    print("=" * 78)
    sim = Simulation(seed=seed, policy=PolicyName.LLM).build(sample_worldspec())
    sim.spawn("visiteur", 2, frozenset({"A", "B"}))
    ts = [
        Timestep(2, messages=(
            (1, Message("B est bloquée", AgentId(77), 2)),
            (2, Message("B est libre", AgentId(77), 2)),
        )),
        Timestep(10, smoke=True),
    ]
    log = sim.run(ts)
    print(log.as_text())
    for inst in sorted(sim.scene.instances.values(), key=lambda i: i.agent.uid.uid):
        agent = inst.agent
        reçus = {k: f"{v.source.value}@{v.tick} c={v.confidence:.2f}" for k, v in agent.memory.receipts.items()}
        print(f"\n[{agent.name}] reçus en mémoire : {reçus}")
        d = agent._last_decision
        if d:
            print(f"    dernière décision : {d.action.value} -> {d.target}")
            if d.llm_trace:
                tr = d.llm_trace.response
                print(f"    LLM {tr.model} ok={tr.ok} tokens={tr.prompt_tokens}+{tr.completion_tokens}")
    _journal(sim, "v3_jumeaux_llm")


def main() -> int:
    bootstrap.assemble()  # branche les fournisseurs (llamacpp -> MAREE_LLM_URL)
    seed = int(os.environ.get("V3_SEED", "42"))
    _foule_hybride(seed)
    _jumeaux_llm(seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())