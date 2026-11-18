"""sim.orchestrator — le petit moteur qui relie le monde, les agents et le LLM.

C'est le chaînon qui manquait : construire un monde validé, y spawner une
population, faire tourner des ticks de *perceptions* (fumée, annonce,
messages) vers ``Agent.react``, et journaliser chaque décision pour qu'on
puisse lire *comment* les agents reçoivent, évaluent, décident et mémorisent.

Décisions-only pour l'instant (pas de physique JuPedSim) : on observe la
cognition. C'est le support de l'évaluation de la pipeline avec un vrai LLM.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import Point as ShapelyPoint
from shapely.geometry import Polygon

from maree.v3.agents.agent import Agent, make_agent
from maree.v3.agents.appraisal import Action
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.policy import Decision
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import ExecutionMode, PolicyName
from maree.v3.sim.bus import EventBus, EventEnvelope, MemoryBus
from maree.v3.sim.physics import CrowdPhysics, Target
from maree.v3.sim.scene import Scene
from maree.v3.verify.emergence import emergence_report
from maree.v3.verify.indicators import TICK_SECONDS, compute, from_agents
from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.simartifact import SimArtifact, build_sim_artifact
from maree.v3.world.validate import validate_or_raise
from maree.v3.world.worldspec import Point, WorldSpec

#: attribution du modèle LLM par **profil** (A5) — jamais par catégorie sociale.
_TIER_BY_ARCHETYPE = {
    "habitue": "decision",
    "agent_de_securite": "decision",
    "visiteur": "petit",
    "famille": "petit",
}

#: placement initial (m) : marge aux parois et espacement minimal (JuPedSim
#: exige > 0,4 m entre deux agents ; on prend de la marge).
_SPAWN_MARGIN = 0.35
_MIN_SPACING = 0.45
_SPAWN_TRIES = 400


@dataclass(frozen=True, slots=True)
class Timestep:
    tick: int
    smoke: bool = False
    announcement: str | None = None
    messages: tuple[tuple[int, Message], ...] = ()
    #: origine du foyer (m, étage courant) : la distance au danger devient
    #: perceptible (C2). Sans elle, la fumée est un signal global.
    hazard_origin: Point | None = None
    #: sorties qui ferment à ce tick (front perçu par les agents).
    closed_exits: tuple[str, ...] = ()


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
    #: bras expérimental (règles / llm / hybride).
    arm: str = "regles"
    #: cause d'escalade vers le modèle (hybride), None en routine.
    escalation_cause: str | None = None
    #: coût de l'appel LLM, **par décision** (jamais relu sur l'agent) :
    #: ``llm_attempted`` distingue « pas d'appel » de « appel raté ».
    llm_attempted: bool = False
    #: cible choisie par le moteur (le modèle n'a nommé aucune sortie).
    target_resolved: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0

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
        physics: CrowdPhysics | None = None,
        physics_steps_per_tick: int = 200,
        epsilon: float = 0.0,
        tick_seconds: float = TICK_SECONDS,
    ) -> None:
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        self.policy = policy
        self.bus = bus or MemoryBus()
        self.run_id = run_id
        self.mode = mode
        self.physics = physics
        self.physics_steps_per_tick = physics_steps_per_tick
        #: quota ε (instrument de sensibilité) — 0 par défaut.
        self.epsilon = epsilon
        #: durée d'un tick (s). Réglée par scénario : une salle de 16 × 12 m se
        #: vide en 20 s, donc un tick de 10 s n'y produirait que deux points de
        #: mesure. I4 et I7 suivent cette horloge, elle est journalisée.
        self.tick_seconds = tick_seconds
        self._evacuated: set[int] = set()
        #: latence de décision par politique (ticks) — le LLM réfléchit lentement.
        self.latency_ticks = latency_ticks or {
            PolicyName.RULES: 0,
            PolicyName.HYBRID: 2,
            PolicyName.LLM: 4,
        }
        self._seq = 0
        self.violations = 0          # compteur de cohérence temporelle (C6)
        #: incidents **tracés et dénombrés** par cause (A4) : repli règles compris.
        self.incidents: Counter[str] = Counter()
        #: injections client en attente (P4), drainées au tick suivant.
        self._injections: list[dict[str, object]] = []
        self._scheduled: dict[AgentId, tuple[int, Perception]] = {}
        self.navgraph: NavigationGraph | None = None
        self.artifact: SimArtifact | None = None
        self.world: WorldSpec | None = None
        #: premier signal de danger du **monde** (fumée, annonce, fermeture) :
        #: l'origine de I7, jamais le premier agent qui bouge.
        self._first_danger_tick: int | None = None
        #: dernier tick où un agent a franchi une issue (I7, I3).
        self._last_exit_tick: int | None = None
        #: temps mural passé dans la physique (C4, mesuré, pas estimé).
        self.wall_physics_s: float = 0.0
        self.scene = Scene()
        self.scene.physics_active = physics is not None
        self.log = RunLog()

    def build(self, world: WorldSpec) -> Simulation:
        validate_or_raise(world)
        self.world = world
        g = NavigationGraph(world)
        art = build_sim_artifact(world, g, self._rng, spawn_per_space=6)
        self.navgraph = g
        self.artifact = art
        self.scene.navgraph = g
        return self

    def spawn(self, archetype: str, count: int, known_exits: frozenset[str],
              llm_alias: str | None = None) -> None:
        """Spawn ``count`` agents de l'archétype en points valides (éventail).

        ``llm_alias`` force le modèle LLM de l'agent (A5) ; par défaut on
        l'attribue par **profil** (habitué/securite → grand, visiteur/famille →
        petit), jamais par catégorie sociale.
        """
        assert self.artifact is not None
        level = next(iter(self.artifact.levels.values()))
        space_ids = sorted(level.spawn_points)
        #: positions déjà occupées, pour l'espacement minimal au placement.
        placed = [(i.point[0], i.point[1]) for i in self.scene.instances.values()]
        for i in range(count):
            space_id = space_ids[i % len(space_ids)]
            pt = self._free_point(level.walkable, placed)
            placed.append(pt)
            agent = make_agent(
                uid=len(self.scene.instances) + 1,
                archetype=archetype,
                known_exits=known_exits,
            )
            agent.policy = self.policy
            agent.llm_alias = llm_alias or _TIER_BY_ARCHETYPE.get(archetype)
            agent.run_id = self.run_id
            agent.epsilon = self.epsilon
            self.scene.add(agent, space_id, pt)
            if self.physics is not None:
                self.physics.spawn(agent.uid.uid, pt, desired_speed=agent.speed_max)

    def _free_point(
        self, walkable: Polygon, placed: list[Point]
    ) -> Point:
        """Un point libre, déterministe, à ``_MIN_SPACING`` des agents déjà posés.

        Leçon 2026-11-17 : réutiliser six points d'artefact en boucle pour
        soixante agents créait six grappes et une densité de pointe au spawn,
        qui se lisait ensuite comme un goulot. Le placement est un tirage
        rejeté dans le polygone marchable (marge ``_SPAWN_MARGIN``), donc
        reproductible : même graine ⇒ mêmes positions.
        """
        inner = walkable.buffer(-_SPAWN_MARGIN)
        minx, miny, maxx, maxy = inner.bounds
        for _ in range(_SPAWN_TRIES):
            x = float(self._rng.uniform(minx, maxx))
            y = float(self._rng.uniform(miny, maxy))
            if not inner.contains(ShapelyPoint(x, y)):
                continue
            if all(
                (x - px) ** 2 + (y - py) ** 2 >= _MIN_SPACING**2
                for px, py in placed
            ):
                return (x, y)
        # repli : le centroïde de la zone sûre (jamais l'origine du repère).
        return (float(inner.centroid.x), float(inner.centroid.y))

    def run(self, timesteps: list[Timestep]) -> RunLog:
        """Anime le monde tick par tick (barrière en sync, cadence en async)."""
        for _ in self.iter_ticks(timesteps):
            pass
        return self.log

    def iter_ticks(self, timesteps: list[Timestep]) -> Iterator[int]:
        """Comme ``run``, mais rend la main **après chaque tick** (diffusion live).

        Le serveur P4 diffuse les enveloppes publiées entre deux rendus ; une
        injection soumise entre deux ticks est drainée au début du suivant.
        """
        by_tick = {ts.tick: ts for ts in timesteps}
        if not by_tick:
            return
        start, last = min(by_tick), max(by_tick)
        # l'horizon n'a de sens qu'en async : il laisse aboutir les appels en
        # vol. En sync, tous les appels sont immédiats ; prolonger le run
        # ajouterait des ticks que le scénario n'a pas demandés.
        horizon = last
        if self.mode is ExecutionMode.ASYNC:
            horizon = last + max(self.latency_ticks.values(), default=0)
        for tick in range(start, horizon + 1):
            ts = by_tick.get(tick)
            if ts is not None:
                self.scene.tick = tick
                # la fumée et l'annonce sont des **niveaux** : un tick qui ne
                # les répète pas ne les éteint pas (sinon t20 « éteignait » la
                # fumée de t10 et le monde mentait).
                if ts.smoke:
                    self.scene.smoke = True
                    self._note_danger(tick)
                if ts.announcement is not None:
                    self.scene.announcement = ts.announcement
                    self._note_danger(tick)
                if ts.hazard_origin is not None:
                    self.scene.hazard_origin = ts.hazard_origin
                if ts.smoke:
                    self._emit("world.smoke", tick, tick, {"visible": True})
                if ts.announcement:
                    self._emit("world.announcement", tick, tick, {"text": ts.announcement})
                for label in ts.closed_exits:
                    if label not in self.scene.closed_exits:
                        self.scene.closed_exits.add(label)
                        self._note_danger(tick)
                        self._emit("world.exit_closed", tick, tick, {"exit": label})
                for agent_uid, msg in ts.messages:
                    self.scene.mails.setdefault(AgentId(agent_uid), []).append(msg)
            self._process_tick(tick)
            yield tick

    def submit(self, payload: dict[str, object]) -> None:
        """Met en file une injection du client (P4) — drainée **au tick suivant**."""
        self._injections.append(dict(payload))

    def _drain_injections(self, tick: int) -> None:
        """Applique les injections en **tête de tick** (perception unique).

        ``control.injection`` est journalisé **avant** l'événement qu'il
        provoque : l'injection n'est jamais une perception à deux vitesses.
        """
        while self._injections:
            payload = self._injections.pop(0)
            self._emit("control.injection", tick, tick, dict(payload))
            kind = payload.get("kind")
            if kind == "smoke":
                self.scene.smoke = True
                self._note_danger(tick)
                origin = payload.get("origin")
                if isinstance(origin, (list, tuple)) and len(origin) == 2:
                    self.scene.hazard_origin = (float(origin[0]), float(origin[1]))
                self._emit("world.smoke", tick, tick, {"visible": True})
            elif kind == "announcement":
                text = str(payload.get("text", ""))
                self.scene.announcement = text
                self._note_danger(tick)
                self._emit("world.announcement", tick, tick, {"text": text})
            elif kind == "close_exit":
                label = str(payload.get("exit", ""))
                if label and label not in self.scene.closed_exits:
                    self.scene.closed_exits.add(label)
                    self._note_danger(tick)
                    self._emit("world.exit_closed", tick, tick, {"exit": label})
            elif kind == "message":
                raw_uid = payload.get("agent", 0)
                uid = raw_uid if isinstance(raw_uid, int) else int(str(raw_uid))
                text = str(payload.get("text", ""))
                self.scene.mails.setdefault(AgentId(uid), []).append(
                    Message(text, AgentId(99), tick)
                )

    def _process_tick(self, tick: int) -> None:
        # l'horloge du monde avance à chaque tick de la boucle, y compris les
        # ticks d'horizon (async) sans nouvel événement : sinon l'état du corps
        # se figerait pendant que la physique, elle, continue.
        self.scene.tick = tick
        # 0) injections client (P4) : drainées en tête de tick, journalisées avant l'effet
        self._drain_injections(tick)
        # 0bis) le corps d'abord : positions et intentions figées, perçues par
        #      tous au même instant (C2 — perception figée). Sans physique, on
        #      fige quand même les intentions (les points de spawn ne bougent pas).
        self.scene.update_positions(
            self.physics.positions() if self.physics is not None else {}
        )

        # 1) en async : appliquer les décisions arrivées à échéance (perception figée)
        if self.mode is ExecutionMode.ASYNC:
            due = [a for a, (apply_t, _) in self._scheduled.items() if apply_t <= tick]
            for agent_id in sorted(due, key=lambda a: a.uid):
                if agent_id.uid in self._evacuated:
                    self._scheduled.pop(agent_id, None)
                    continue
                apply_t, snap = self._scheduled.pop(agent_id)
                agent = self.scene.instances[agent_id].agent
                decision = agent.react(snap, force=True)
                self._record(agent, decision, t_prod=snap.tick, t_trait=apply_t)
                self._apply_intention(agent, decision)

        # 2) chaque bras applique son calendrier (ADR-014) ; en sync décider ici
        for agent_id in sorted(self.scene.instances, key=lambda a: a.uid):
            if agent_id.uid in self._evacuated:      # sorti physiquement : plus de décision
                continue
            agent = self.scene.instances[agent_id].agent
            perception = self.scene.perception_for(agent_id)
            gate = agent.should_decide(perception)
            if not gate.decide:
                continue
            if self.mode is ExecutionMode.ASYNC:
                if agent_id not in self._scheduled:  # déjà « en train de réfléchir »
                    self.scene.drain(agent_id)
                    self._emit("agent.reconsider", tick, tick, {
                        "agent": agent.name,
                        "reason": gate.reason,
                    })
                    latency = self.latency_ticks.get(agent.policy, 1)
                    self._scheduled[agent_id] = (tick + latency, perception)
            else:
                self.scene.drain(agent_id)
                self._emit("agent.reconsider", tick, tick, {
                    "agent": agent.name,
                    "reason": gate.reason,
                })
                decision = agent.react(perception, force=True)
                self._record(agent, decision, t_prod=tick, t_trait=tick)
                self._apply_intention(agent, decision)

        # 3) le corps bouge : la physique avance et l'on diffuse l'état
        if self.physics is not None:
            t_phys = time.perf_counter()
            self.physics.advance(self.physics_steps_per_tick)
            self.wall_physics_s += time.perf_counter() - t_phys
            new_evac = self.physics.evacuated() - self._evacuated
            self._evacuated |= new_evac
            for tag in sorted(new_evac):
                self._last_exit_tick = tick
                self._emit("agent.evacuated", tick, tick, {"agent": f"A{tag:02d}"})
            positions = self.physics.positions()
            self._emit("world.snapshot", tick, tick, {
                "agents": {str(tag): [round(x, 2), round(y, 2)] for tag, (x, y) in positions.items()},
            })

        # 4) indicateurs calculés PENDANT le run, pas après (B2/A4)
        active = [
            inst.agent
            for agent_id, inst in self.scene.instances.items()
            if agent_id.uid not in self._evacuated
        ]
        rep = emergence_report(active, seed=self.seed + tick)
        self._emit("indicator.emergence", tick, tick, {
            "consensus": rep["consensus"],
            "couplage": rep["couplage"],
            "emergence": rep["emergence"],
            "null_consensus": rep["null_consensus"],
            "social_excess": rep["social_excess"],
        })
        self._emit("indicator.crowd", tick, tick, self._crowd_indicators(tick))
        self._emit("indicator.incidents", tick, tick, {
            "total": sum(self.incidents.values()),
            "par_cause": dict(sorted(self.incidents.items())),
        })

    def _crowd_indicators(self, tick: int) -> dict[str, object]:
        """I1–I7 de l'instant (C4) : la même définition que la v2, portée ici.

        Trois pièges v2 sont tenus par construction : I5 est un noyau de 2 m
        (pas une grille), le consensus ne compte que les agents **actifs**, et
        I7 part du premier signal de danger du monde. I6 est **0 par
        construction** s'il n'y a pas de fermeture : le champ ``closed`` le dit
        pour qu'on ne publie pas un zéro qui ne mesure rien.
        """
        pairs: list[tuple[Agent, tuple[float, float], bool]] = []
        for agent_id, inst in self.scene.instances.items():
            pairs.append(
                (
                    inst.agent,
                    self.scene.position_of(agent_id),
                    agent_id.uid in self._evacuated,
                )
            )
        exits = set(self._known_exit_ids()) | set(self.scene.closed_exits)
        open_exits = {
            label for label in self._known_exit_ids()
            if label not in self.scene.closed_exits
        }
        states = from_agents(pairs, n_exits=max(1, len(exits)))
        ind = compute(
            states,
            n_exits=max(1, len(exits)),
            open_exits=open_exits,
            tick=tick,
            signal_tick=self._first_danger_tick,
            last_exit_tick=self._last_exit_tick,
            tick_seconds=self.tick_seconds,
        )
        data = ind.to_dict()
        data["closed_exits"] = sorted(self.scene.closed_exits)
        return data

    def _known_exit_ids(self) -> list[str]:
        """Les sorties du plan (source de vérité pour I6)."""
        if self.world is None:
            return []
        return [exit_spec.id for level in self.world.levels for exit_spec in level.exits]

    def _apply_intention(self, agent: Agent, decision: Decision) -> None:
        """Traduit une décision en intention physique.

        Règle (2026-11-17) : **aucune** action ne déplace l'agent ailleurs que
        là où il est, sauf ``EVACUER`` (vers une sortie) et ``CHERCHER`` /
        ``CHERCHER_PROCHE`` (vers un point). Les autres tiennent la position :
        elles n'avaient aucun sens physique (``SUIVRE``, ``AIDER``,
        ``REVIRER``) et seront câblées avec la perception (C2).
        """
        if self.physics is None:
            return
        self.physics.set_intention(agent.uid.uid, self._target_for(agent, decision))

    def _target_for(self, agent: Agent, decision: Decision) -> Target:
        """L'intention physique d'une décision (pur, testable sans JuPedSim)."""
        if decision.action is Action.EVACUER and decision.target:
            return Target.exit(decision.target)
        if decision.action is Action.CHERCHER:
            point = self._search_point(agent)
            return Target.at(point) if point is not None else Target.stay()
        if decision.action is Action.CHERCHER_PROCHE and decision.target:
            point = self._position_of(decision.target)
            return Target.at(point) if point is not None else Target.stay()
        # RESTER, SUIVRE, AIDER, REVIRER : on tient la position (C2/C3).
        return Target.stay()

    def _search_point(self, agent: Agent) -> Point | None:
        """Un point à 3 m, dans une direction déterministe tirée de l'agent.

        « Chercher de l'information » ne veut pas dire sortir : on se déplace
        dans la zone où l'on est, et l'adaptateur ramène le point dans le
        domaine marchable (``_safe_position``).
        """
        if self.physics is None:
            return None
        position = self.physics.positions().get(agent.uid.uid)
        if position is None:
            return None
        angle = (agent.uid.uid * 2.399963) % (2.0 * math.pi)
        return (
            position[0] + 3.0 * math.cos(angle),
            position[1] + 3.0 * math.sin(angle),
        )

    def _position_of(self, name: str) -> Point | None:
        """Position courante de l'agent ``name`` (s'il est encore dans le monde)."""
        if self.physics is None:
            return None
        for agent_id, instance in self.scene.instances.items():
            if instance.agent.name == name:
                return self.physics.positions().get(agent_id.uid)
        return None

    def _record(self, agent: Agent, decision: Decision, t_prod: int, t_trait: int) -> None:
        """Journalise décision + cohérence (C6) + publie l'enveloppe (C1)."""
        # C6 : jamais agir sur une info produite après sa décision (par construction)
        if t_prod > t_trait:
            self.violations += 1
        self.log.rows.append(self._row(agent, decision, t_prod, t_trait))
        # l'escalade précède la décision qu'elle a provoquée.
        if decision.escalation_cause:
            self._emit("agent.escalation", t_prod, t_trait, {
                "agent": agent.name,
                "cause": decision.escalation_cause,
                "detail": decision.escalation_detail,
            })
        self._emit("agent.decision", t_prod, t_trait, {
            "agent": agent.name,
            "archetype": agent.archetype,
            "action": decision.action.value,
            "target": decision.target,
            "fallback": decision.fallback,
            "fallback_cause": decision.fallback_cause,
            "explanation": decision.explanation,
            "arm": agent.policy.value,
            "escalation_cause": decision.escalation_cause,
            "target_resolved": decision.target_resolved,
        })
        # A4 : un repli n'est pas un silence — il est tracé et dénombré par cause.
        if decision.fallback:
            cause = decision.fallback_cause or "inconnue"
            self.incidents[cause] += 1
            self._emit("agent.incident", t_prod, t_trait, {
                "agent": agent.name,
                "cause": cause,
                "action": decision.action.value,
            })

    def _note_danger(self, tick: int) -> None:
        """Retient le **premier** signal de danger du monde (origine de I7).

        L'ordre des déclencheurs n'importe pas : fumée, annonce et fermeture
        sont tous des signaux de danger ; I7 part du premier, jamais du
        premier agent qui bouge (un guide ou un proche cherché part avant).
        """
        if self._first_danger_tick is None:
            self._first_danger_tick = tick

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
            arm=agent.policy.value,
            escalation_cause=decision.escalation_cause,
            llm_attempted=trace is not None,
            target_resolved=decision.target_resolved,
            prompt_tokens=0 if trace is None else trace.response.prompt_tokens,
            completion_tokens=(
                0 if trace is None else trace.response.completion_tokens
            ),
            latency_s=0.0 if trace is None else trace.response.latency_s,
        )


__all__ = ["LogRow", "RunLog", "Simulation", "Timestep"]