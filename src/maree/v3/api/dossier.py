"""api.dossier — le dossier d'un agent (P4, ADR-011).

Un client clique sur un agent et reçoit sa fiche. Chaque champ est **étiqueté**
par sa nature (ADR-011) :

- ``measured`` : directement observé dans le run (position, politique, modèle) ;
- ``derived`` : calculé à partir de l'état (croyances, connaissance des sorties) ;
- ``generated`` : produit par le LLM (explication, texte), donc à lire comme
  une justification, pas comme une mesure.

Le dossier est en **superset** : il expose tout ce qui existe, y compris les
champs que le client actuel n'affiche pas — un client ne casse pas quand le
moteur en sait plus.
"""

from __future__ import annotations

from typing import Any

from maree.v3.agents.agent import Agent
from maree.v3.sim.orchestrator import Simulation


def _agent_of(sim: Simulation, name: str) -> Agent | None:
    for inst in sim.scene.instances.values():
        if inst.agent.name == name:
            return inst.agent
    return None


def agent_dossier(sim: Simulation, name: str) -> dict[str, Any]:
    """Fiche complète et étiquetée d'un agent (``None`` si absent du run)."""
    agent = _agent_of(sim, name)
    if agent is None:
        return {}
    inst = sim.scene.instances[agent.uid]
    decision = agent._last_decision
    trace = decision.llm_trace if decision else None

    measured: dict[str, Any] = {
        "agent": agent.name,
        "archetype": agent.archetype,
        "policy": agent.policy.value,
        "model_alias": agent.llm_alias,
        "position": [round(inst.point[0], 2), round(inst.point[1], 2)],
        "space": inst.space_id,
        "speed_max": agent.speed_max,
        "evacuated": agent.uid.uid in sim._evacuated,
    }
    derived: dict[str, Any] = {
        "known_exits": sorted(agent.known_exits),
        "beliefs": {
            key: {"confidence": round(b.confidence, 3), "source": b.source.value, "tick": b.tick}
            for key, b in sorted(agent.knowledge.beliefs.items())
        },
        "remembered_events": [
            {"kind": ev.kind.value, "tick": ev.tick, "text": ev.content}
            for ev in agent.memory.episodes[-5:]
        ],
        "kin": sorted(k.uid for k in agent.social.kin),
        "leader": None if agent.social.leader is None else agent.social.leader.uid,
        "last_action": None if decision is None else decision.action.value,
        "last_target": None if decision is None else decision.target,
        "fallback": None if decision is None else decision.fallback,
    }
    generated: dict[str, Any] = {
        "explanation": None if decision is None else decision.explanation,
        "llm": None
        if trace is None
        else {
            "model": trace.response.model,
            "ok": trace.response.ok,
            "prompt_tokens": trace.response.prompt_tokens,
            "completion_tokens": trace.response.completion_tokens,
        },
    }
    return {
        "type": "agent_dossier",
        "run_id": sim.run_id,
        "tick": sim.scene.tick,
        "labels": {"measured": measured, "derived": derived, "generated": generated},
    }


__all__ = ["agent_dossier"]
