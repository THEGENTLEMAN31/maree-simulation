"""sim.orchestrator — le petit moteur qui relie le monde, les agents et le LLM.

C'est le chaînon qui manquait : construire un monde validé, y spawner une
population, faire tourner des ticks de *perceptions* (fumée, annonce,
messages) vers ``Agent.react``, et journaliser chaque décision pour qu'on
puisse lire *comment* les agents reçoivent, évaluent, décident et mémorisent.

Décisions-only pour l'instant (pas de physique JuPedSim) : on observe la
cognition. C'est le support de l'évaluation de la pipeline avec un vrai LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from maree.v3.agents.agent import Agent, make_agent
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.policy import Decision
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import ExecutionMode, PolicyName
from maree.v3.sim.bus import EventBus, EventEnvelope, MemoryBus
from maree.v3.sim.scene import Scene
from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.simartifact import SimArtifact, build_sim_artifact
from maree.v3.world.validate import validate_or_raise
from maree.v3.world.worldspec import WorldSpec


@dataclass(frozen=True, slots=True)
class Timestep:
    tick: int
    smoke: bool = False
    announcement: str | None = None
    messages: tuple[tuple[int, Message], ...] = ()


@dataclass(frozen=True, slots=True)
class LogRow:
    tick: int              # t_trait : tick où la décision est appliquée
    t_prod: int            # tick où elle a été *perçue/vue*
    agent: str
    archetype: str
    action: str
    target: str | None
    fallback: bool
    fallback_cause: str | None
    explanation: str
    dims: dict[str, float]
    llm_ok: bool | None
    llm_model: str | None

    @property
    def lag(self) -> int:
        """Décalage traité − perçu (C7) : 0 en sync, > 0 en async."""
        return self.tick - self.t_prod


@dataclass(slots=True)
class RunLog:
    rows: list[LogRow] = field(default_factory=list)

    def as_text(self) -> str:
        lines = []
        for r in self.rows:
            llm = ""
            if r.llm_model:
                llm = f" [LLM {r.llm_model} ok={r.llm_ok}]"
            repli = f" ⚠repli({r.fallback_cause})" if r.fallback else ""
            menace = f"{r.dims.get('menace', 0):.2f}"
            lines.append(
                f"t{r.tick:>3} {r.agent:<6} {r.archetype:<8} "
                f"{r.action:<22} -> {r.target or '-'!s:<4} "
                f"menace={menace}{repli}{llm}"
            )
        return "\n".join(lines)


class Simulation:
    """Construit et anime un monde.

    ``seed`` pilote tout l'aléa (spawns, etc.) : même graine ⇒ même run.
    ``mode`` (sync/async) choisit comment le temps passe (C4).
    """

    def __init__(
        self,
        seed: int = 42,
        policy: PolicyName = PolicyName.RULES,
        bus: EventBus | None = None,
        run_id: str = "v3",
        mode: ExecutionMode = ExecutionMode.SYNC,
        latency_ticks: dict[PolicyName, int] | None = None,
    ) -> None:
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        self.policy = policy
        self.bus = bus or MemoryBus()
        self.run_id = run_id
        self.mode = mode
        #: latence de décision par politique (ticks) — le LLM réfléchit lentement.
        self.latency_ticks = latency_ticks or {
            PolicyName.RULES: 0,
            PolicyName.HYBRID: 2,
            PolicyName.LLM: 4,
        }
        self._seq = 0
        self.violations = 0          # compteur de cohérence temporelle (C6)
        self._scheduled: dict[AgentId, tuple[int, Perception]] = {}
        self.navgraph: NavigationGraph | None = None
        self.artifact: SimArtifact | None = None
        self.scene = Scene()
        self.log = RunLog()

    def build(self, world: WorldSpec) -> Simulation:
        validate_or_raise(world)
        g = NavigationGraph(world)
        art = build_sim_artifact(world, g, self._rng, spawn_per_space=6)
        self.navgraph = g
        self.artifact = art
        self.scene.navgraph = g
        return self

    def spawn(self, archetype: str, count: int, known_exits: frozenset[str]) -> None:
        """Spawn ``count`` agents de l'archétype en points valides (éventail)."""
        assert self.artifact is not None
        spaces = next(iter(self.artifact.levels.values())).spawn_points
        space_ids = sorted(spaces)
        for i in range(count):
            space_id = space_ids[i % len(space_ids)]
            pts = spaces[space_id]
            pt = pts[i % len(pts)]
            agent = make_agent(
                uid=len(self.scene.instances) + 1,
                archetype=archetype,
                known_exits=known_exits,
            )
            agent.policy = self.policy
            self.scene.add(agent, space_id, pt)

    def run(self, timesteps: list[Timestep]) -> RunLog:
        """Anime le monde tick par tick (barrière en sync, cadence en async)."""
        by_tick = {ts.tick: ts for ts in timesteps}
        if not by_tick:
            return self.log
        start, last = min(by_tick), max(by_tick)
        horizon = last + max(self.latency_ticks.values(), default=0)  # les appels en vol
        for tick in range(start, horizon + 1):
            ts = by_tick.get(tick)
            if ts is not None:
                self.scene.tick = tick
                self.scene.smoke = ts.smoke
                self.scene.announcement = ts.announcement
                if ts.smoke:
                    self._emit("world.smoke", tick, tick, {"visible": True})
                if ts.announcement:
                    self._emit("world.announcement", tick, tick, {"text": ts.announcement})
                for agent_uid, msg in ts.messages:
                    self.scene.mails.setdefault(AgentId(agent_uid), []).append(msg)
            self._process_tick(tick)
        return self.log

    def _process_tick(self, tick: int) -> None:
        # 1) en async : appliquer les décisions arrivées à échéance (perception figée)
        if self.mode is ExecutionMode.ASYNC:
            due = [a for a, (apply_t, _) in self._scheduled.items() if apply_t <= tick]
            for agent_id in sorted(due, key=lambda a: a.uid):
                apply_t, snap = self._scheduled.pop(agent_id)
                agent = self.scene.instances[agent_id].agent
                decision = agent.react(snap)
                self._record(agent, decision, t_prod=snap.tick, t_trait=apply_t)

        # 2) détecter les nouveaux signaux (fronts) ; en sync décider immédiatement
        for agent_id in sorted(self.scene.instances, key=lambda a: a.uid):
            agent = self.scene.instances[agent_id].agent
            perception = self.scene.perception_for(agent_id)
            if not agent._novel_events(perception):
                continue
            self.scene.drain(agent_id)
            if self.mode is ExecutionMode.ASYNC:
                if agent_id not in self._scheduled:  # déjà « en train de réfléchir »
                    latency = self.latency_ticks.get(agent.policy, 1)
                    self._scheduled[agent_id] = (tick + latency, perception)
            else:
                decision = agent.react(perception)
                self._record(agent, decision, t_prod=tick, t_trait=tick)

    def _record(self, agent: Agent, decision: Decision, t_prod: int, t_trait: int) -> None:
        """Journalise décision + cohérence (C6) + publie l'enveloppe (C1)."""
        # C6 : jamais agir sur une info produite après sa décision (par construction)
        if t_prod > t_trait:
            self.violations += 1
        self.log.rows.append(self._row(agent, decision, t_prod, t_trait))
        self._emit("agent.decision", t_prod, t_trait, {
            "agent": agent.name,
            "archetype": agent.archetype,
            "action": decision.action.value,
            "target": decision.target,
            "fallback": decision.fallback,
            "fallback_cause": decision.fallback_cause,
            "explanation": decision.explanation,
        })

    def _emit(self, event_type: str, t_prod: int, t_trait: int, data: dict[str, object]) -> None:
        """Publie une enveloppe (C1) avec sa chronologie simulée (C3)."""
        self._seq += 1
        self.bus.publish(
            EventEnvelope(
                run_id=self.run_id,
                seq=self._seq,
                type=event_type,
                t_prod=t_prod,
                t_trait=t_trait,
                data=data,
            )
        )

    @staticmethod
    def _row(agent: Agent, decision: Decision, t_prod: int, t_trait: int) -> LogRow:
        ap = decision.appraisal
        trace = decision.llm_trace
        return LogRow(
            tick=t_trait,
            t_prod=t_prod,
            agent=agent.name,
            archetype=agent.archetype,
            action=decision.action.value,
            target=decision.target,
            fallback=decision.fallback,
            fallback_cause=decision.fallback_cause,
            explanation=decision.explanation,
            dims=ap.dimensions if ap else {},
            llm_ok=None if trace is None else trace.response.ok,
            llm_model=None if trace is None else trace.response.model,
        )


__all__ = ["LogRow", "RunLog", "Simulation", "Timestep"]