"""P4 — le contrat front : trames WS, dossier agent, injections.

Ce que le client Godot reçoit est testé ici sans ouvrir de socket : les
fonctions de trame, le dossier étiqueté et la boucle de commandes sont pures.
L'injection, elle, est vérifiée sur un **vrai run** : elle est drainée au tick
suivant, journalisée avant son effet (perception unique).
"""

from __future__ import annotations

import asyncio
import json

from maree.v3.api.dossier import agent_dossier
from maree.v3.api.frames import (
    PROTOCOL_VERSION,
    end_frame,
    error_frame,
    frame_for,
    hello_frame,
    world_frame,
)
from maree.v3.api.server import Broadcaster
from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import EventEnvelope, MemoryBus
from maree.v3.sim.journal import world_hash
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.world.sample import sample_worldspec


def _sim(policy: PolicyName = PolicyName.RULES, bus: MemoryBus | None = None) -> Simulation:
    sim = Simulation(seed=3, policy=policy, bus=bus, run_id="p4").build(sample_worldspec())
    sim.spawn("visiteur", 2, frozenset({"A", "B"}))
    return sim


# ---- trames ----

def test_hello_et_world_portent_lidentite_du_run() -> None:
    world = sample_worldspec()
    hello = hello_frame("p4", world, world_hash(world), nd_agents=2)
    assert hello["type"] == "hello" and hello["protocol_version"] == PROTOCOL_VERSION
    assert hello["world"]["hash"] == world_hash(world)
    assert "agent_dossier" in hello["capabilities"] and "inject" in hello["capabilities"]
    w = world_frame(world, world_hash(world))
    assert w["type"] == "world" and w["levels"][0]["exits"]


def test_chaque_type_du_journal_a_sa_trame() -> None:
    def env(t: str, data: dict[str, object]) -> EventEnvelope:
        return EventEnvelope("p4", 1, t, 2, 2, data=data)

    d = frame_for(env("agent.decision", {
        "agent": "A01", "archetype": "visiteur", "action": "évacuer vers une sortie",
        "target": "A", "fallback": False, "fallback_cause": None, "explanation": "fumée",
    }))
    assert d["type"] == "decision" and d["agent"] == "A01" and d["reason"] == "fumée"

    s = frame_for(env("world.snapshot", {"agents": {"1": [1.0, 2.0]}}))
    assert s["type"] == "snapshot" and s["agents"] == {"1": [1.0, 2.0]}

    h = frame_for(env("world.smoke", {"visible": True}))
    assert h["type"] == "hazard" and h["source"] == "smoke"

    m = frame_for(env("world.announcement", {"text": "sortez"}))
    assert m["type"] == "message" and m["content"] == "sortez"

    e = frame_for(env("agent.evacuated", {"agent": "A02"}))
    assert e["type"] == "evacuated" and e["agent"] == "A02"

    i = frame_for(env("indicator.incidents", {"total": 2, "par_cause": {"unparseable": 2}}))
    assert i["type"] == "incident" and i["total"] == 2


def test_un_evenement_sans_trame_dediee_passe_en_event() -> None:
    env = EventEnvelope("p4", 7, "experience.custom", 3, 3, data={"x": 1})
    f = frame_for(env)
    assert f["type"] == "event" and f["event_type"] == "experience.custom"
    assert f["data"] == {"x": 1} and f["seq"] == 7     # rien n'est filtré


def test_end_et_error_ont_la_forme_du_contrat() -> None:
    end = end_frame("p4", {"decisions": 3})
    assert end["type"] == "end" and end["summary"]["decisions"] == 3
    err = error_frame("p4", "agent_not_found", "A99 inconnu")
    assert err["type"] == "error" and err["error"]["code"] == "agent_not_found"
    assert err["error"]["retryable"] is False


# ---- dossier agent (ADR-011) ----

def test_le_dossier_est_etiquete_measured_derived_generated() -> None:
    sim = _sim()
    sim.run([Timestep(1), Timestep(5, smoke=True)])
    d = agent_dossier(sim, "A01")
    assert d["type"] == "agent_dossier" and d["run_id"] == "p4"
    labels = d["labels"]
    assert set(labels) == {"measured", "derived", "generated"}
    assert labels["measured"]["agent"] == "A01"
    assert labels["measured"]["policy"] == "rules"
    assert "A" in labels["derived"]["known_exits"]
    assert labels["derived"]["last_action"]
    assert labels["generated"]["explanation"]          # produit par la politique
    assert agent_dossier(sim, "A99") == {}


# ---- injections ----

def test_une_injection_est_drainee_au_tick_suivant_avant_son_effet() -> None:
    bus = MemoryBus()
    sim = _sim(bus=bus)
    it = sim.iter_ticks([Timestep(1), Timestep(2), Timestep(3)])
    assert next(it) == 1
    sim.submit({"kind": "smoke"})
    assert next(it) == 2
    types = [(e.type, e.t_trait) for e in bus.envelopes if e.t_trait == 2]
    assert ("control.injection", 2) in types
    assert ("world.smoke", 2) in types
    # journalisé AVANT l'effet qu'il provoque
    assert types.index(("control.injection", 2)) < types.index(("world.smoke", 2))
    assert any(r.tick == 2 for r in sim.log.rows)      # les agents voient la fumée


def test_une_injection_dannonce_est_percue_au_tick_suivant() -> None:
    bus = MemoryBus()
    sim = _sim(bus=bus)
    sim.submit({"kind": "announcement", "text": "Veuillez évacuer par la sortie B"})
    sim.run([Timestep(1), Timestep(2)])
    # l'annonce est un **front** : elle est perçue au tick où elle arrive,
    # mémorisée par l'agent, puis le champ retombe (ce n'est pas une alarme
    # de niveau, sinon chaque tick redéciderait).
    assert any(e.type == "world.announcement" and e.t_trait == 1 for e in bus.envelopes)
    assert any(r.tick == 1 and r.target == "B" for r in sim.log.rows)


# ---- boucle de commandes du serveur ----

class FakeWS:
    def __init__(self, messages: list[str]) -> None:
        self._msgs = list(messages)
        self.sent: list[dict[str, object]] = []

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def __aiter__(self) -> FakeWS:
        return self

    async def __anext__(self) -> str:
        if not self._msgs:
            raise StopAsyncIteration
        return self._msgs.pop(0)


def test_le_serveur_repond_hello_ack_dossier_et_erreurs() -> None:
    sim = _sim()

    async def scenario() -> FakeWS:
        b = Broadcaster(sim)
        ws = FakeWS([
            json.dumps({"type": "inject", "kind": "smoke"}),
            json.dumps({"type": "agent", "agent": "A01"}),
            json.dumps({"type": "agent", "agent": "A99"}),
            "pas du json",
            json.dumps({"type": "nope"}),
        ])
        await b.handler(ws)
        return ws

    ws = asyncio.run(scenario())
    kinds = [str(m.get("type")) for m in ws.sent]
    assert kinds[0] == "hello"                       # première trame
    assert "ack" in kinds
    assert "agent_dossier" in kinds
    assert kinds.count("error") == 3                 # A99, bad_json, commande inconnue
    # l'injection n'est pas appliquée tout de suite : elle attend le tick suivant
    assert sim.scene.smoke is False
    assert sim._injections == [{"kind": "smoke"}]
