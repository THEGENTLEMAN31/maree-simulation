"""Boucle de simulation — trois horloges, un seul état du monde.

    physique   0,05 s   JuPedSim avance (positions, contacts, files)
    cognition 10,00 s   les agents qui ont une raison de décider décident
    rendu      0,10 s   un instantané part vers Godot

Points de conception qui ne sont pas négociables :

  * **perception figée** (décision 10) : tous les agents perçoivent le même
    instant T, même si leurs décisions arrivent à des moments différents ;
  * **ordre canonique** (décision 3) : les décisions sont appliquées par
    `agent_id` croissant, jamais dans l'ordre d'arrivée des réponses LLM ;
  * **tout est journalisé** (décision 1) : un appel LLM non écrit est un
    événement perdu, donc un rejeu impossible ;
  * **les intentions sont la seule sortie des agents** (décision 8) : la
    physique ne connaît ni croyance ni message, elle reçoit une destination.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import time
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from maree.agents.graph import DecisionGraph
from maree.agents.profiles import Profile, get_profile
from maree.agents.rules import rules_decide
from maree.agents.triggers import Message, Percept, should_decide
from maree.domain.beliefs import BeliefTable
from maree.domain.clock import Clocks, SimClock
from maree.domain.events import Event, EventType
from maree.domain.geometry import Plan, Zone
from maree.domain.ids import AgentId, ExitId, Point, RunId
from maree.domain.intentions import Intention, IntentionKind
from maree.memory.store import EventSourcedMemory
from maree.metrics import indicators as metrics
from maree.narrative.chroniqueur import Chroniqueur, Narrative
from maree.narrative.digest import build_digest
from maree.ports import (
    CrowdPhysics,
    Destination,
    Episode,
    EventBus,
    JournalPort,
    LLMPort,
    RetrieverPort,
)

TOPIC_WORLD = "world.events"
TOPIC_DECISIONS = "agent.decisions"
TOPIC_NARRATIVE = "narrative.generated"
TOPIC_METRICS = "metrics.indicators"


# ============================================================
# Configuration d'un run
# ============================================================
@dataclass(frozen=True, slots=True)
class PopulationEntry:
    profile: str
    count: int
    kind: Literal["llm", "rules"] = "llm"


@dataclass(frozen=True, slots=True)
class RunConfig:
    run_id: RunId
    seed: int = 0
    max_ticks: int = 72
    smoke_tick: int = 10
    smoke_position: Point = (44.0, 15.0)
    smoke_radius: float = 15.0
    close_exit: ExitId | None = None
    close_tick: int = 40
    announcement_tick: int | None = 18
    announcement: str | None = "Évacuation. Rejoignez la sortie nord."
    population: tuple[PopulationEntry, ...] = ()
    max_concurrency: int = 4
    narrative_every: int = 5
    message_radius: float = 8.0
    density_radius: float = 3.0
    clocks: Clocks = field(default_factory=Clocks)

    def config_hash(self) -> str:
        """Identité du run (décision 5) : run_id + configuration."""
        payload = json.dumps(
            {
                "run_id": self.run_id,
                "seed": self.seed,
                "max_ticks": self.max_ticks,
                "smoke": [self.smoke_tick, self.smoke_position, self.smoke_radius],
                "close": [self.close_exit, self.close_tick],
                "announcement": [self.announcement_tick, self.announcement],
                "population": [(p.profile, p.count, p.kind) for p in self.population],
                "clocks": [self.clocks.physics_dt, self.clocks.cognition_s],
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class RunResult:
    run_id: RunId
    config_hash: str
    ticks: int
    events: int
    indicators: tuple[metrics.Indicators, ...]
    narratives: tuple[Narrative, ...]
    llm_calls: int
    duration_s: float
    #: Appels LLM réellement aboutis. `llm_calls` compte les tentatives :
    #: sans serveur, un run « hybride » n'est qu'un run à règles déguisé.
    llm_ok: int = 0


# ============================================================
# État runtime
# ============================================================
@dataclass(slots=True)
class AgentRuntime:
    agent_id: AgentId
    profile: Profile
    beliefs: BeliefTable = field(default_factory=BeliefTable)
    intention: Intention | None = None
    last_decision_tick: int | None = None
    known_messages: set[str] = field(default_factory=set)
    #: Signaux d'environnement déjà traités (« smoke », « announcement »).
    #: Sans cela, la fumée visible redéclencherait une décision à CHAQUE
    #: tick — un déclencheur de niveau, pas de front, et 60 appels par tick.
    known_signals: set[str] = field(default_factory=set)
    pending: list[Message] = field(default_factory=list)
    evacuated: bool = False
    missing_kin: bool = False
    kin: AgentId | None = None
    decisions: int = 0
    spoke: bool = False

    def best_exit(self) -> ExitId | None:
        return self.beliefs.best()


class Simulation:
    """Assemble les ports. Aucune implémentation concrète n'est connue ici."""

    def __init__(
        self,
        *,
        config: RunConfig,
        plan: Plan,
        physics: CrowdPhysics,
        llm: LLMPort,
        retriever: RetrieverPort | None,
        memory: EventSourcedMemory,
        journal: JournalPort,
        bus: EventBus,
        narrator: Chroniqueur | None = None,
    ) -> None:
        self._cfg = config
        self._plan = plan
        self._physics = physics
        self._llm = llm
        self._retriever = retriever
        self._memory = memory
        self._journal = journal
        self._bus = bus
        self._narrator = narrator
        self._graph = DecisionGraph(
            llm=llm, retriever=retriever, memory=memory, plan=plan
        )
        self._rng = random.Random(config.seed)
        self._seq = journal.last_seq(config.run_id)
        self._agents: dict[AgentId, AgentRuntime] = {}
        self._exits_open: set[ExitId] = set(plan.exits)
        self._smoke_active = False
        self._announcement: str | None = None
        self._events: list[metrics.Indicators] = []
        self._narratives: list[Narrative] = []
        self._recent: list[str] = []
        self._llm_calls = 0
        self._llm_ok = 0
        self._t0 = time.monotonic()

    # ---- journal ----------------------------------------------
    async def _emit(self, tick: int, type_: EventType, data: dict[str, Any]) -> Event:
        self._seq += 1
        event = Event(
            seq=self._seq,
            run_id=self._cfg.run_id,
            type=type_,
            t_prod=tick,
            t_trait=tick,
            t_real=time.monotonic() - self._t0,
            data=data,
        )
        self._journal.append(event)
        topic = {
            EventType.DECISION: TOPIC_DECISIONS,
            EventType.EVACUATED: TOPIC_DECISIONS,
            EventType.NARRATIVE: TOPIC_NARRATIVE,
            EventType.INDICATORS: TOPIC_METRICS,
        }.get(type_, TOPIC_WORLD)
        await self._bus.publish(topic, event)
        return event

    # ---- population -------------------------------------------
    def _spawn(self) -> None:
        index = 0
        for entry in self._cfg.population:
            profile = get_profile(entry.profile)
            # Le profil nommé décrit un SAVOIR ; `kind` décide du MOTEUR.
            # Sans ce `replace`, les 48 agents « à règles » appelleraient
            # le LLM : c'est exactement le bug qui rendrait le run
            # impossible à terminer.
            if entry.kind == "rules":
                profile = replace(profile, kind="rules", model="")
            for _ in range(entry.count):
                index += 1
                agent_id = f"A{index:02d}"
                zone = self._spawn_zone(entry.profile)
                position = self._sample_in_zone(zone)
                runtime = AgentRuntime(agent_id=agent_id, profile=profile)
                # Croyances initiales : ce que le profil sait en arrivant.
                for exit_id in self._plan.exits:
                    if profile.knows(exit_id):
                        runtime.beliefs.set(exit_id, 0.35, "connu", 0)
                self._agents[agent_id] = runtime
                self._physics.add_agent(
                    agent_id, position, Destination.to_point(position)
                )
        # Appariement des proches (profil famille).
        family = [a for a in self._agents.values() if a.profile.id == "famille"]
        for i in range(0, len(family) - 1, 2):
            family[i].kin = family[i + 1].agent_id
            family[i + 1].kin = family[i].agent_id

    def _spawn_zone(self, profile_id: str) -> Zone:
        preference = {
            "securite": ("Z1", "Z5"),
            "habitue": ("Z2", "Z5"),
            "famille": ("Z7", "Z3"),
            "visiteur": ("Z6", "Z1"),
            "vendeur": ("Z6", "Z3"),
        }.get(profile_id, tuple(self._plan.zones))
        zones = [self._plan.zones[z] for z in preference if z in self._plan.zones]
        return self._rng.choice(zones or list(self._plan.zones.values()))

    def _sample_in_zone(self, zone: Zone) -> Point:
        xs = [p[0] for p in zone.polygon]
        ys = [p[1] for p in zone.polygon]
        for _ in range(200):
            p = (self._rng.uniform(min(xs), max(xs)), self._rng.uniform(min(ys), max(ys)))
            if zone.contains(p):
                return p
        return zone.centroid

    # ---- boucle -----------------------------------------------
    async def run(self) -> RunResult:
        cfg = self._cfg
        await self._emit(
            0,
            EventType.RUN_STARTED,
            {
                "config_hash": cfg.config_hash(),
                "seed": cfg.seed,
                "plan": self._plan.name,
                "population": [
                    {"profile": p.profile, "count": p.count, "kind": p.kind}
                    for p in cfg.population
                ],
            },
        )
        self._spawn()
        await self._emit(0, EventType.SNAPSHOT, self._snapshot(0))

        tick = 0
        for tick in range(1, cfg.max_ticks + 1):
            # --- 1. physique -------------------------------------
            for _ in range(cfg.clocks.steps_per_tick):
                self._physics.step()
            positions = self._physics.positions()
            evacuated = self._physics.evacuated()

            for agent_id, runtime in self._agents.items():
                if agent_id in evacuated and not runtime.evacuated:
                    runtime.evacuated = True
                    runtime.intention = Intention(
                        IntentionKind.GO_EXIT, None, "sorti", tick
                    )
                    await self._emit(
                        tick, EventType.EVACUATED, {"agent_id": agent_id, "kind": "exit"}
                    )

            # --- 2. événements du monde --------------------------
            await self._world_events(tick)

            # --- 3. perception -----------------------------------
            percepts = {
                aid: self._percept(aid, rt, positions, tick)
                for aid, rt in self._agents.items()
                if not rt.evacuated
            }

            # --- 4. qui décide ? ---------------------------------
            todo: list[tuple[AgentId, str]] = []
            for agent_id in sorted(percepts):
                runtime = self._agents[agent_id]
                percept = percepts[agent_id]
                trigger = should_decide(
                    percept,
                    last_decision_tick=runtime.last_decision_tick,
                    current_exit=runtime.best_exit(),
                    known_messages=frozenset(runtime.known_messages),
                    known_signals=frozenset(runtime.known_signals),
                    cadence_ticks=runtime.profile.cadence_ticks,
                )
                if trigger:
                    todo.append((agent_id, trigger.reason))

            # --- 5. décisions (concurrentes, appliquées dans l'ordre) ---
            results = await self._decide_all(todo, percepts)

            for agent_id, reason, intention, trace in results:
                await self._apply(
                    agent_id, intention, trace, percepts[agent_id], positions, trigger=reason
                )

            # --- 6. messages et mémoire --------------------------
            await self._diffuse(tick, positions)

            # --- 7. indicateurs ----------------------------------
            states = self._agent_states(positions)
            ind = metrics.compute(
                states,
                self._plan,
                self._exits_open,
                tick,
                cfg.clocks.tick_to_seconds(tick),
            )
            self._events.append(ind)
            await self._emit(tick, EventType.INDICATORS, ind.to_dict())
            await self._emit(tick, EventType.SNAPSHOT, self._snapshot(tick))

            # --- 8. chroniqueur ----------------------------------
            if self._narrator and self._narrator.due(tick) and not self._all_out():
                await self._narrate(ind, states, tick)

            if self._all_out():
                break

        await self._emit(
            tick,
            EventType.RUN_ENDED,
            {
                "ticks": tick,
                "llm_calls": self._llm_calls,
                "llm_ok": self._llm_ok,
                "evacuated": sum(1 for a in self._agents.values() if a.evacuated),
                "total": len(self._agents),
            },
        )
        return RunResult(
            run_id=cfg.run_id,
            config_hash=cfg.config_hash(),
            ticks=tick,
            events=self._seq,
            indicators=tuple(self._events),
            narratives=tuple(self._narratives),
            llm_calls=self._llm_calls,
            llm_ok=self._llm_ok,
            duration_s=time.monotonic() - self._t0,
        )

    # ---- étapes ------------------------------------------------
    async def _world_events(self, tick: int) -> None:
        cfg = self._cfg
        if tick == cfg.smoke_tick and not self._smoke_active:
            self._smoke_active = True
            self._recent.append(f"t{tick} fumée près de la scène")
            await self._emit(
                tick,
                EventType.WORLD_SMOKE,
                {"position": list(cfg.smoke_position), "radius": cfg.smoke_radius},
            )
        if cfg.close_exit and tick == cfg.close_tick and cfg.close_exit in self._exits_open:
            self._exits_open.discard(cfg.close_exit)
            self._physics.close_exit(cfg.close_exit)
            self._recent.append(f"t{tick} sortie {cfg.close_exit} fermée")
            await self._emit(tick, EventType.EXIT_CLOSED, {"exit": cfg.close_exit})
        if cfg.announcement_tick and tick == cfg.announcement_tick:
            self._announcement = cfg.announcement
            self._recent.append(f"t{tick} annonce officielle")
            await self._emit(
                tick, EventType.ANNOUNCEMENT, {"text": cfg.announcement}
            )

    def _percept(
        self,
        agent_id: AgentId,
        runtime: AgentRuntime,
        positions: dict[AgentId, Point],
        tick: int,
    ) -> Percept:
        cfg = self._cfg
        position = positions.get(agent_id, (0.0, 0.0))
        near = self._neighbours(agent_id, positions)
        density = len(near) / (math.pi * cfg.density_radius**2)
        smoke_visible = False
        intensity = 0.0
        if self._smoke_active:
            dist = math.dist(position, cfg.smoke_position)
            if dist < cfg.smoke_radius:
                smoke_visible = True
                intensity = 1.0 - dist / cfg.smoke_radius
        missing = False
        if runtime.kin:
            kin = self._agents.get(runtime.kin)
            if kin and not kin.evacuated:
                kin_pos = positions.get(runtime.kin)
                if kin_pos is None or math.dist(position, kin_pos) > 10.0:
                    missing = True
            elif kin and kin.evacuated:
                missing = False
        return Percept(
            tick=tick,
            position=position,
            zone=self._plan.zone_of(position),
            smoke_visible=smoke_visible,
            smoke_intensity=intensity,
            density=density,
            exits_open=frozenset(self._exits_open),
            exit_density={
                exit_id: self._density_near(
                    self._plan.exit(exit_id).center, positions, cfg.density_radius
                )
                for exit_id in self._exits_open
            },
            messages=tuple(runtime.pending),
            nearby=tuple(near),
            announcement=self._announcement if tick >= (cfg.announcement_tick or 10**9) else None,
            missing_kin=missing,
        )

    def _density_near(
        self, point: Point, positions: dict[AgentId, Point], radius: float
    ) -> float:
        area = math.pi * radius**2
        count = sum(1 for pos in positions.values() if math.dist(point, pos) <= radius)
        return count / area

    def _neighbours(
        self, agent_id: AgentId, positions: dict[AgentId, Point]
    ) -> list[AgentId]:
        me = positions.get(agent_id)
        if me is None:
            return []
        radius = self._cfg.message_radius
        return [
            other
            for other, pos in positions.items()
            if other != agent_id and math.dist(me, pos) <= radius
        ]

    async def _decide_all(
        self, todo: list[tuple[AgentId, str]], percepts: dict[AgentId, Percept]
    ) -> list[tuple[AgentId, str, Intention, dict[str, Any] | None]]:
        """Décisions concurrentes, mais **appliquées** dans l'ordre canonique."""
        semaphore = asyncio.Semaphore(self._cfg.max_concurrency)
        out: list[tuple[AgentId, str, Intention, dict[str, Any] | None]] = []

        async def one(agent_id: AgentId, reason: str) -> None:
            runtime = self._agents[agent_id]
            percept = percepts[agent_id]
            async with semaphore:
                if runtime.profile.kind == "rules":
                    intention = rules_decide(
                        percept, self._plan, profile=runtime.profile.id
                    )
                    trace = None
                else:
                    intention, state = await self._graph.decide(
                        agent_id=agent_id,
                        profile=runtime.profile,
                        percept=percept,
                        trigger=reason,
                    )
                    trace = state.get("llm")
                    self._llm_calls += 1
                    if trace:
                        trace["fallback"] = bool(state.get("fallback"))
                        if trace.get("ok"):
                            self._llm_ok += 1
            out.append((agent_id, reason, intention, trace))

        await asyncio.gather(*(one(a, r) for a, r in todo))
        return sorted(out, key=lambda x: x[0])

    async def _apply(
        self,
        agent_id: AgentId,
        intention: Intention,
        trace: dict[str, Any] | None,
        percept: Percept,
        positions: dict[AgentId, Point],
        *,
        trigger: str,
    ) -> None:
        runtime = self._agents[agent_id]
        runtime.intention = intention
        runtime.last_decision_tick = percept.tick
        runtime.decisions += 1
        runtime.pending.clear()
        # Un signal persistant n'est traité qu'une fois (front, pas niveau).
        if trigger == "fumee_visible":
            runtime.known_signals.add("smoke")
        elif trigger == "annonce":
            runtime.known_signals.add("announcement")
        elif trigger == "sortie_fermee":
            # `best_exit()` est encore la croyance d'avant la décision :
            # c'est bien cette sortie-là qu'il faut marquer comme traitée.
            previous = runtime.best_exit()
            if previous is not None:
                runtime.known_signals.add(f"closed:{previous}")

        # --- destination physique (décision 8) -------------------
        match intention.kind:
            case (IntentionKind.GO_EXIT | IntentionKind.GUIDE) if (
                intention.target in self._plan.exits
            ):
                self._physics.set_destination(
                    agent_id, Destination.to_exit(intention.target)  # type: ignore[arg-type]
                )
            case IntentionKind.FOLLOW if intention.target in positions:
                self._physics.set_destination(
                    agent_id, Destination.follow(intention.target)  # type: ignore[arg-type]
                )
            case IntentionKind.GO_ZONE if intention.target in self._plan.zones:
                self._physics.set_destination(
                    agent_id, Destination.to_point(self._plan.zones[intention.target].centroid)
                )
            case IntentionKind.SEARCH:
                self._physics.set_destination(
                    agent_id, Destination.to_point(self._plan.walkable[0])
                )
            case _:
                self._physics.set_destination(
                    agent_id, Destination.to_point(percept.position)
                )

        # --- croyance -------------------------------------------
        if intention.kind in {IntentionKind.GO_EXIT, IntentionKind.GUIDE} and intention.target:
            runtime.beliefs.decay(0.92)
            runtime.beliefs.set(
                intention.target,
                max(intention.confidence, runtime.beliefs.confidence(intention.target)),
                f"decision:t{percept.tick}",
                percept.tick,
            )
        elif intention.kind is IntentionKind.FOLLOW and intention.target:
            source = self._agents.get(intention.target)
            if source:
                best = source.best_exit()
                if best:
                    runtime.beliefs.set(
                        best, 0.6, f"suivi:{intention.target}", percept.tick
                    )

        # --- mémoire --------------------------------------------
        self._memory.remember(
            agent_id,
            Episode(
                tick=percept.tick,
                kind="decide",
                content=f"{intention.describe()} — {intention.reason}",
                source="soi",
                salience=0.6,
            ),
        )
        if percept.smoke_visible:
            self._memory.remember(
                agent_id,
                Episode(
                    tick=percept.tick,
                    kind="vu",
                    content="fumée visible près de la scène",
                    source="perception",
                    salience=0.9,
                ),
            )
        self._memory.consolidate(agent_id, percept.tick)

        # --- journal --------------------------------------------
        data: dict[str, Any] = {
            "agent_id": agent_id,
            "kind": "rules" if runtime.profile.kind == "rules" else "llm",
            # `trigger` = pourquoi on a décidé ; `reason` = pourquoi cette
            # intention. Les confondre rendait le journal inexploitable.
            "trigger": trigger,
            "reason": intention.reason,
            "intention": intention.to_dict(),
            "beliefs": runtime.beliefs.snapshot(),
            "position": list(percept.position),
            "density": round(percept.density, 3),
        }
        if trace:
            data["llm"] = trace
        await self._emit(percept.tick, EventType.DECISION, data)
        await self._emit(
            percept.tick,
            EventType.BELIEF_UPDATED,
            {"agent_id": agent_id, "beliefs": runtime.beliefs.snapshot()},
        )

    async def _diffuse(self, tick: int, positions: dict[AgentId, Point]) -> None:
        """Un agent qui vient de comprendre prévient ses voisins. Une fois."""
        for agent_id in sorted(self._agents):
            runtime = self._agents[agent_id]
            if runtime.evacuated or runtime.spoke or runtime.intention is None:
                continue
            if runtime.intention.kind not in {
                IntentionKind.GO_EXIT,
                IntentionKind.GUIDE,
            }:
                continue
            best = runtime.best_exit()
            if not best or runtime.beliefs.confidence(best) < 0.6:
                continue
            runtime.spoke = True
            claim = f"sortie_{best}"
            content = f"il faut sortir par la sortie {best}"
            await self._emit(
                tick,
                EventType.MESSAGE_SENT,
                {"from": agent_id, "to": self._neighbours(agent_id, positions), "content": content},
            )
            for other in self._neighbours(agent_id, positions):
                target = self._agents[other]
                if target.evacuated:
                    continue
                target.pending.append(
                    Message(sender=agent_id, content=content, tick=tick, claim=claim)
                )
                target.known_messages.add(f"{agent_id}:{tick}")
                self._memory.remember(
                    other,
                    Episode(
                        tick=tick,
                        kind="entendu",
                        content=f"{agent_id} dit : {content}",
                        source=agent_id,
                        salience=0.7,
                    ),
                )
                await self._emit(
                    tick,
                    EventType.MESSAGE_HEARD,
                    {"agent_id": other, "from": agent_id, "content": content},
                )

    async def _narrate(
        self, ind: metrics.Indicators, states: list[metrics.AgentState], tick: int
    ) -> None:
        digest = build_digest(
            indicators=ind,
            agents=states,
            open_exits=self._exits_open,
            all_exits=tuple(self._plan.exits),
            sim_time=SimClock(tick, self._cfg.clocks).fmt(),
            recent_events=tuple(self._recent[-3:]),
        )
        narrative = await self._narrator.narrate(digest)  # type: ignore[union-attr]
        self._narratives.append(narrative)
        await self._emit(
            tick,
            EventType.NARRATIVE,
            {
                "text": narrative.text,
                "digest_hash": narrative.digest_hash,
                "valid": narrative.valid,
                "problems": list(narrative.problems),
                "llm": narrative.llm,
            },
        )

    # ---- vues --------------------------------------------------
    def _agent_states(self, positions: dict[AgentId, Point]) -> list[metrics.AgentState]:
        return [
            metrics.AgentState(
                agent_id=aid,
                profile=rt.profile.id,
                position=positions.get(aid, (0.0, 0.0)),
                belief_best=rt.best_exit(),
                belief_confidence=(
                    rt.beliefs.confidence(rt.best_exit()) if rt.best_exit() else 0.0
                ),
                belief_entropy=rt.beliefs.entropy(len(self._plan.exits)),
                evacuated=rt.evacuated,
            )
            for aid, rt in sorted(self._agents.items())
        ]

    def _snapshot(self, tick: int) -> dict[str, Any]:
        positions = self._physics.positions()
        return {
            "tick": tick,
            "sim_time": SimClock(tick, self._cfg.clocks).fmt(),
            "exits_open": sorted(self._exits_open),
            "agents": [
                {
                    "id": aid,
                    "profile": rt.profile.id,
                    "pos": list(positions.get(aid, (0.0, 0.0))),
                    "belief": rt.best_exit(),
                    "confidence": round(
                        rt.beliefs.confidence(rt.best_exit()) if rt.best_exit() else 0.0, 3
                    ),
                    "intention": rt.intention.kind if rt.intention else None,
                    "evacuated": rt.evacuated,
                }
                for aid, rt in sorted(self._agents.items())
            ],
        }

    def _all_out(self) -> bool:
        return all(a.evacuated for a in self._agents.values())
