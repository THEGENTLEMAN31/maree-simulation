#!/usr/bin/env python
"""Sonde réelle (P0) : la mémoire personnelle influence-t-elle le vrai LLM ?

Deux jumeaux identiques (visiteur, sorte A/B) reçoivent chacun UN message
différent (« B est bloquée » vs « B est libre ») puis la même fumée.
- On vérifie que le **memorandum** (les reçus) est bien dans le prompt ;
- on observe la divergence au vrai modèle (gemma4-e2b).
Usage : MAREE_LLM_URL=http://127.0.0.1:8081/v1 uv run python scripts/v3_mem_real.py
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("MAREE_LLM_URL", "http://127.0.0.1:8081/v1")

from maree.v3 import bootstrap
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.state import State
from maree.v3.core.ids import AgentId, ZoneId
from maree.v3.core.ports import PolicyName


def _smoke(t: int = 10) -> Perception:
    return Perception(tick=t, zone=ZoneId("z1"), state=State(), smoke_visible=True,
                      seen_agents=(), exits_visible=frozenset())


def _message(t: int, text: str) -> Perception:
    return Perception(tick=t, zone=ZoneId("z1"), state=State(),
                      heard=(Message(text, AgentId(77), t),),
                      seen_agents=(), exits_visible=frozenset())


def main() -> int:
    bootstrap.assemble()
    from maree.v3.agents.agent import make_agent

    know = frozenset({"A", "B"})
    a1 = make_agent(1, "visiteur", known_exits=know)
    a2 = make_agent(2, "visiteur", known_exits=know)
    a1.policy = PolicyName.LLM
    a2.policy = PolicyName.LLM

    a1.react(_message(2, "B est bloquée"))
    a2.react(_message(2, "B est libre"))
    t0 = time.time()
    d1 = a1.react(_smoke())
    d2 = a2.react(_smoke())
    dt = time.time() - t0

    def prompt_of(agent) -> str:
        tr = agent._last_decision.llm_trace
        if tr is None:
            return "(pas de trace LLM)"
        return tr.request.messages[1].content

    p1, p2 = prompt_of(a1), prompt_of(a2)
    print("A01 ->", d1.action.value, d1.target, "| repli", d1.fallback_cause)
    print("A02 ->", d2.action.value, d2.target, "| repli", d2.fallback_cause)
    print(f"DIVERGENCE: {d1.target != d2.target}  ({dt:.1f}s)")
    print("\n--- mémorandum d'A01 (reçus en tête de prompt) ---")
    print(p1[:400])
    print("\n--- mémorandum d'A02 (reçus en tête de prompt) ---")
    print(p2[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())