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
from maree.v3.agents.perception import Message
from maree.v3.agents.policy import Decision
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import PolicyName
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
    tick: int
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
    """

    def __init__(self, seed: int = 42, policy: PolicyName = PolicyName.RULES) -> None:
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        self.policy = policy
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
        time_steps = sorted(timesteps, key=lambda t: t.tick)
        for ts in time_steps:
            self.scene.tick = ts.tick
            self.scene.smoke = ts.smoke
            self.scene.announcement = ts.announcement
            # dépôt des messages adressés
            for agent_uid, msg in ts.messages:
                self.scene.mails.setdefault(AgentId(agent_uid), []).append(msg)
            # chaque agent perçoit l'instant T puis décide (ordre canonique)
            for agent_id in sorted(self.scene.instances, key=lambda a: a.uid):
                agent = self.scene.instances[agent_id].agent
                perception = self.scene.perception_for(agent_id)
                decision = agent.react(perception)
                self.scene.drain(agent_id)
                self.log.rows.append(self._row(agent, decision, ts.tick))
        return self.log

    @staticmethod
    def _row(agent: Agent, decision: Decision, tick: int) -> LogRow:
        ap = decision.appraisal
        trace = decision.llm_trace
        return LogRow(
            tick=tick,
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