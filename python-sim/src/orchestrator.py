"""Orchestrateur principal de la simulation.

Câble ensemble : configuration → monde → population → ordonnanceur →
passerelle LLM → Kafka → indicateurs → journal JSONL → WebSocket Godot.

Décisions implémentées : 1 (journal source de vérité), 2 (double horodatage),
3 (déterminisme), 5 (identité de run), 7 (passerelle LLM unique),
8 (le moteur exécute les intentions), 9 (Godot consommateur pur),
10 (ordonnanceur séparé), 12 (traçabilité RAG), 16 (offsets sources).
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import asdict, dataclass, field

from . import events as evmod
from .agents import build_agents
from .agents.base import Perception
from .agents.llm_agent import LLMAgent
from .agents.profiles import split_agents
from .config import SimulationConfig
from .kafka_client import KafkaClient
from .llm_gateway import LLMGateway
from .metrics.indicators import IndicatorSet, Indicators
from .oracle import TemporalOracle
from .rag.rag import RagClient
from .replay import RunLogger
from .temporal import Scheduler, SimClock
from .world import World
from .ws_server import WSRelay


@dataclass
class AgentRuntime:
    """État d'exécution d'un agent (zone, évacué, croyance)."""

    zone: str = "scene"
    evacuated: bool = False
    belief_safe_exit: str | None = None
    belief_danger: bool = False


class Orchestrator:
    """Contrôle l'exécution d'un run complet."""

    def __init__(
        self,
        config: SimulationConfig,
        *,
        kafka_bootstrap: str = "redpanda:9092",
        llm_base_url: str = "http://llama-cpp:8080/v1",
        corpus_path: str = "/world_corpus",
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.kafka_bootstrap = kafka_bootstrap
        self.llm_base_url = llm_base_url
        self.corpus_path = corpus_path
        self.dry_run = dry_run

        # Déterminisme (décision 3) : un RNG par run, une graine par agent.
        self.rng = random.Random(config.seed)
        self.clock = SimClock(tick_duration_ms=config.tick_duration_ms)
        self.world = World(config.world, self.rng)

        self.agents = build_agents(config.population, self.rng)
        self.llm_agents, self.rules_agents = split_agents(self.agents)
        self.runtime: dict[str, AgentRuntime] = {
            a.agent_id: AgentRuntime() for a in self.agents
        }

        self.scheduler = Scheduler(
            config.mode, self.clock, self.rng, default_think_interval=20
        )
        for spec in config.population:
            for i in range(spec.count):
                agent_id = f"{spec.name}_{i + 1:02d}"
                interval = spec.think_interval or {
                    "securite": 40,
                    "habitue": 40,
                }.get(spec.name, 20)
                self.scheduler.register(agent_id, think_interval=interval)

        # Passerelle LLM unique (décision 7).
        self.gateway = LLMGateway(llm_base_url, dry_run=dry_run)
        for a in self.llm_agents:
            a.gateway = self.gateway

        # RAG (F1) injecté dans les agents LLM.
        self.rag = RagClient()
        for a in self.llm_agents:
            a.rag = self.rag

        self.indicators = Indicators()
        self.oracle = TemporalOracle()

        self.kafka = KafkaClient(kafka_bootstrap, config.run_id, memory=dry_run)
        self.logger = RunLogger(config.run_id, config.log_dir)
        self.ws = WSRelay(port=8765, enabled=not dry_run)
        self.ws.on_command = self._handle_control

        self._state: dict = {"announcements": [], "false_infos": []}
        self._indicator_history: list[dict] = []
        self._offset_high_water: dict[str, int] = field(default_factory=dict)

    # ------------------------------------------------------- journal (déc. 1)
    def _journal(self, topic: str, envelope: evmod.EventEnvelope) -> None:
        """Écrit un événement : une fois dans le journal JSONL (E3) et une
        fois dans Kafka (C1, décision 1). En mode mémoire, la publication
        est un append synchrone ; en mode réseau, une tâche asyncio."""
        self.logger.log(envelope)
        asyncio.create_task(self.kafka.publish(topic, envelope))

    # ------------------------------------------------------------------ run
    async def run(self, *, max_ticks: int | None = None) -> dict:
        """Exécute le run complet et retourne le résumé (E4, E2)."""
        await self.kafka.start()
        await self.ws.start()
        n_passages = self.rag.ingest_directory(self.corpus_path)

        self._emit_spawn()
        limits = max_ticks or self.config.max_ticks

        for tick in range(limits):
            self.clock.now = tick
            world_changed = self.world.tick_world(tick)
            if world_changed:
                self._emit_smoke(tick)
            self._apply_experiment_events(tick)

            due = self.scheduler.due_agents(tick)
            await self._run_agent_turns(due, tick)
            await self._emit_snapshot(tick)
            if tick % 10 == 0 or tick == limits - 1:
                await self._emit_indicators(tick)
            await asyncio.sleep(0)  # laisse respirer le scheduler OS

        await self._emit_indicators(limits - 1)
        summary = self.gateway.cost_log.summary()
        summary["run_id"] = self.config.run_id
        summary["mode"] = self.config.mode
        summary["passages_ingested"] = n_passages
        summary["temporal_violations"] = len(self.oracle.violations)
        summary["config_hash"] = self.config.config_hash()
        await self.kafka.close()
        await self.ws.close()
        self.logger.close()
        return summary

    # ---------------------------------------------------------------- pas

    async def _run_agent_turns(self, due, tick: int) -> None:
        """Un tour d'agents : perception figée à l'instant T (décision 10)."""
        for sched in sorted(due, key=lambda s: s.agent_id):
            agent = self._agent(sched.agent_id)
            rt = self.runtime[sched.agent_id]
            if rt.evacuated:
                continue
            perception = self._perception_for(agent, tick)
            t_trait = self.scheduler.process(sched, now=tick)

            flags = self.config.world.experiment_flags
            if not flags.get("llm", True):
                # X4 baseline : on force l'agent à utiliser la règle.
                intention = self._rules_intention(agent, perception)
                explanation = {"kind": "rules_baseline_override"}
            else:
                intention = await agent.decide(perception)
                explanation = self._explanation(agent, perception, intention)

            # A2 : message en langage naturel vers les voisins.
            pending = getattr(agent, "_pending_message", None)
            if pending and flags.get("memory", True):
                for neighbor in perception.visible_neighbors:
                    self._messages(neighbor, tick, pending, agent.agent_id, t_trait)

            self._apply_intention(agent, intention, tick, t_trait)
            self.scheduler.schedule_next(sched, now=tick)

    def _perception_for(self, agent, tick: int) -> Perception:
        rt = self.runtime[agent.agent_id]
        zone = rt.zone
        smoke = self.world.smoke_level > 0 and (
            zone in self.world.smoke_zones or self.world.smoke_zones == {"sud_est"}
        )
        return Perception(
            tick=tick,
            zone=zone,
            smoke_seen=smoke,
            visible_neighbors=self._visible_neighbors(agent, zone),
            announcements=self._state["announcements"],
            false_infos=self._state["false_infos"],
            exits_known=self._exits_known(agent),
        )

    def _rules_intention(self, agent, perception: Perception):
        """Bascule X4 : intention calculée par la règle au lieu du LLM."""
        return agent.fallback_intention(perception)

    @staticmethod
    def _explanation(agent, perception: Perception, intention) -> dict:
        """Justification exposée dans Godot (D2) — agent LLM ou règle."""
        if isinstance(agent, LLMAgent):
            return {
                "kind": "llm",
                "reasoning": getattr(agent, "last_call", None).text[:400]
                if getattr(agent, "last_call", None)
                else None,
                "intention": asdict(intention),
            }
        explain = getattr(agent, "explanation", None)
        return explain(perception) if explain else {"kind": "rules", "intention": asdict(intention)}

    async def _inspect(self, agent_id: str) -> None:
        agent = self._agent(agent_id)
        rt = self.runtime[agent_id]
        payload = {
            "type": "inspection",
            "agent_id": agent_id,
            "zone": rt.zone,
            "belief": rt.belief_safe_exit,
            "evacuated": rt.evacuated,
        }
        if isinstance(agent, LLMAgent):
            payload["memory"] = [
                {"tick": e.tick, "kind": e.kind, "text": e.text}
                for e in agent.recent_memory(10)
            ]
            payload["last_rag"] = getattr(agent, "last_rag", None)
            payload["drifts"] = agent.drift_events
        else:
            payload["explanation"] = getattr(agent, "explanation", lambda p: {})(None)
        self.ws.broadcast(payload)

    def _apply_intention(self, agent, intention, tick: int, t_trait: int) -> None:
        rt = self.runtime[agent.agent_id]
        if intention.exit_code:
            rt.belief_safe_exit = intention.exit_code
        if intention.belief_danger is not None:
            rt.belief_danger = intention.belief_danger

        if intention.action == "evacuate":
            rt.evacuated = True
            self._journal(
                "world",
                evmod.new_envelope(
                    self.config.run_id,
                    "movement.evacuated",
                    t_prod=tick,
                    t_trait=t_trait,
                    agent_id=agent.agent_id,
                    data={"exit": intention.exit_code},
                ),
            )
        elif intention.action == "move" and intention.target_zone:
            if intention.target_zone in self.world.zones:
                rt.zone = intention.target_zone
        # publish decision event (cœur du journal, E3)
        self._journal(
            "agents",
            evmod.new_envelope(
                self.config.run_id,
                "agent.decision",
                t_prod=tick,
                t_trait=t_trait,
                agent_id=agent.agent_id,
                data={
                    "action": intention.action,
                    "target_zone": intention.target_zone,
                    "exit": intention.exit_code,
                },
            ),
        )

    # ---------------------------------------------------------- événements

    def _emit_spawn(self) -> None:
        self._journal(
            "world",
            evmod.new_envelope(
                self.config.run_id,
                "agent.spawn",
                t_prod=0,
                t_trait=0,
                data={"n_agents": len(self.agents)},
            ),
        )

    def _emit_smoke(self, tick: int) -> None:
        self._journal(
            "world",
            evmod.new_envelope(
                self.config.run_id,
                "world.smoke_update",
                t_prod=tick,
                t_trait=tick,
                data={"level": self.world.smoke_level},
            ),
        )

    def _apply_experiment_events(self, tick: int) -> None:
        """Applique les variantes expérimentales programmées (X1, X2)."""
        w = self.config.world
        if w.announcement_tick == tick:
            clarity = w.announcement_clarity or "clear"
            text = (
                "Annonce : évacuez par la sortie la plus proche, elles sont toutes ouvertes."
                if clarity == "clear"
                else "Annonce : nous vous prions de bien vouloir rester calmes."
            )
            self._state["announcements"].append(text)
            self._journal(
                "world",
                evmod.new_envelope(
                    self.config.run_id,
                    "world.announcement",
                    t_prod=tick,
                    t_trait=tick,
                    data={"text": text, "clarity": clarity},
                ),
            )
        for code, close_tick in w.exits_closed.items():
            if close_tick == tick and code in self.world.exits:
                self.world.exits[code].blocked = True
                self._journal(
                    "world",
                    evmod.new_envelope(
                        self.config.run_id,
                        "world.exit_closed",
                        t_prod=tick,
                        t_trait=tick,
                        data={"exit": code},
                    ),
                )

    async def _emit_snapshot(self, tick: int) -> None:
        """Instantané agrégé des positions (C1 : 1 message pour tous)."""
        snapshot = {
            "tick": tick,
            "smoke_level": self.world.smoke_level,
            "agents": [
                {
                    "id": a.agent_id,
                    "zone": self.runtime[a.agent_id].zone,
                    "belief": self.runtime[a.agent_id].belief_safe_exit,
                    "kind": "llm" if a in self.llm_agents else "rules",
                }
                for a in self.agents
            ],
        }
        await self.ws.broadcast({"type": "state", **snapshot})
        self._journal(
            "world",
            evmod.new_envelope(
                self.config.run_id,
                "movement.snapshot",
                t_prod=tick,
                t_trait=tick,
                data=snapshot,
            ),
        )

    async def _emit_indicators(self, tick: int) -> None:
        result = self.indicators.compute(self._indicator_state(tick))
        self._indicator_history.append(result)
        self._journal(
            "metrics",
            evmod.new_envelope(
                self.config.run_id,
                "metrics.indicators",
                t_prod=tick,
                t_trait=tick,
                data=result,
            ),
        )
        await self.ws.broadcast({"type": "indicators", **result})

    def _indicator_state(self, tick: int) -> IndicatorSet:
        beliefs = []
        destinations = []
        evacuated = 0
        for a in self.agents:
            rt = self.runtime[a.agent_id]
            beliefs.append((a.agent_id, rt.belief_safe_exit, rt.belief_danger))
            evacuated += 1 if rt.evacuated else 0
            if rt.evacuated:
                destinations.append((a.agent_id, rt.belief_safe_exit or "A"))
        return IndicatorSet(
            tick=tick,
            beliefs=beliefs,
            evacuated=evacuated,
            trapped=0,
            total=len(self.agents),
            ground_truth_safe_exit=self.world.ground_truth_safe_exit(),
            destinations=destinations,
            temporal_violations=len(self.oracle.violations),
        )

    def _messages(self, to_agent: str, tick: int, text: str, sender: str, t_trait: int) -> None:
        self._journal(
            "agents",
            evmod.new_envelope(
                self.config.run_id,
                "agent.message",
                t_prod=tick,
                t_trait=t_trait,
                agent_id=sender,
                data={"to": to_agent, "text": text},
            ),
        )

    # -------------------------------------------------------------- helpers

    def _agent(self, agent_id: str):
        return next((a for a in self.agents if a.agent_id == agent_id), None)

    def _visible_neighbors(self, agent, zone: str) -> list[str]:
        return [
            a.agent_id
            for a in self.agents
            if a.agent_id != agent.agent_id
            and self.runtime[a.agent_id].zone == zone
        ][:5]

    def _exits_known(self, agent) -> list[str]:
        if agent.profile_name in {"securite", "habitue"}:
            return ["A", "B", "C"]
        return ["A"]

    async def _handle_control(self, data: dict) -> None:
        """Injection d'événements depuis Godot (D3) + inspection (D2)."""
        if data.get("type") == "command":
            cmd = data.get("command")
            if cmd == "announcement":
                self._state["announcements"].append(data.get("text", ""))
            elif cmd == "false_info":
                self._state["false_infos"].append(data.get("text", ""))
            elif cmd == "close_exit":
                code = data.get("exit", "A")
                if code in self.world.exits:
                    self.world.exits[code].blocked = True
        elif data.get("type") == "inspect":
            await self._inspect(data.get("agent_id", ""))