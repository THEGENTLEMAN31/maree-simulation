# Graph Report - maree-simulation  (2026-10-14)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 339 nodes · 730 edges · 11 communities (9 shown, 2 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 81 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4d48270c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Perception
- cli.py
- Orchestrator
- EventEnvelope
- test_core.py
- test_rag_rules.py
- orchestrator.py
- llm_gateway.py
- World
- download_models.sh
- maree-simulation

## God Nodes (most connected - your core abstractions)
1. `Orchestrator` - 48 edges
2. `Perception` - 23 edges
3. `LLMAgent` - 22 edges
4. `EventEnvelope` - 18 edges
5. `RulesAgent` - 15 edges
6. `SimulationConfig` - 15 edges
7. `KafkaClient` - 15 edges
8. `RagClient` - 15 edges
9. `Agent` - 14 edges
10. `Intention` - 13 edges

## Surprising Connections (you probably didn't know these)
- `Orchestrator` --uses--> `Perception`  [INFERRED]
  python-sim/src/orchestrator.py → python-sim/src/agents/base.py
- `test_rag_controle_acces_profil()` --uses--> `Perception`  [INFERRED]
  python-sim/tests/test_rag_rules.py → python-sim/src/agents/base.py
- `test_rag_date_disponibilite_c6()` --uses--> `Perception`  [INFERRED]
  python-sim/tests/test_rag_rules.py → python-sim/src/agents/base.py
- `LLMAgent` --uses--> `LLMGateway`  [INFERRED]
  python-sim/src/agents/llm_agent.py → python-sim/src/llm_gateway.py
- `Orchestrator` --uses--> `LLMAgent`  [INFERRED]
  python-sim/src/orchestrator.py → python-sim/src/agents/llm_agent.py

## Import Cycles
- None detected.

## Communities (11 total, 2 thin omitted)

### Community 0 - "Perception"
Cohesion: 0.07
Nodes (12): Agent, Intention, Perception, LLMAgent, MemoryEntry, build_agents(), split_agents(), _exit_rank() (+4 more)

### Community 1 - "cli.py"
Cohesion: 0.06
Nodes (13): cli(), experiments(), _fmt_summary(), replay(), report(), run(), CollectorSpec, load_config() (+5 more)

### Community 2 - "Orchestrator"
Cohesion: 0.07
Nodes (13): new_envelope(), Orchestrator, WSRelay, _cfg(), test_config_hash_deterministe(), test_event_envelope_double_horodatage(), test_rejeu_identique_meme_config(), make_cfg() (+5 more)

### Community 3 - "EventEnvelope"
Cohesion: 0.06
Nodes (7): EventEnvelope, now_iso(), KafkaClient, _MemoryLog, ReplayEngine, ReplayResult, RunLogger

### Community 4 - "test_core.py"
Cohesion: 0.09
Nodes (8): Indicators, IndicatorSet, AgentSchedule, Scheduler, SimClock, test_horloge_et_ordonnanceur_async(), test_horloge_et_ordonnanceur_sync(), test_indicateurs_convergent()

### Community 5 - "test_rag_rules.py"
Cohesion: 0.13
Nodes (6): Passage, RagClient, _agent(), test_rag_controle_acces_profil(), test_rag_date_disponibilite_c6(), _write_passage()

### Community 6 - "orchestrator.py"
Cohesion: 0.12
Nodes (3): TemporalOracle, TemporalViolation, AgentRuntime

### Community 7 - "llm_gateway.py"
Cohesion: 0.12
Nodes (3): ProfileSpec, CostLog, LLMGateway

### Community 8 - "World"
Cohesion: 0.17
Nodes (4): WorldSpec, ExitState, World, Zone

## Knowledge Gaps
- **1 isolated node(s):** `maree-simulation`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 142 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Orchestrator` connect `Orchestrator` to `Perception`, `cli.py`, `EventEnvelope`, `test_core.py`, `test_rag_rules.py`, `orchestrator.py`, `llm_gateway.py`, `World`?**
  _High betweenness centrality (0.306) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `Orchestrator` (e.g. with `run()` and `ExperimentRunner`) actually correct?**
  _`Orchestrator` has 16 INFERRED edges - model-reasoned connections that need verification._
- **What connects `maree-simulation` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Perception` be split into smaller, more focused modules?**
  _Cohesion score 0.07364114552893045 - nodes in this community are weakly interconnected._
- **Why does `Perception` connect `Perception` to `Orchestrator`, `test_rag_rules.py`, `orchestrator.py`?**
  _High betweenness centrality (0.092) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Perception` (e.g. with `LLMAgent` and `RulesAgent`) actually correct?**
  _`Perception` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Should `cli.py` be split into smaller, more focused modules?**
  _Cohesion score 0.061952861952861954 - nodes in this community are weakly interconnected._