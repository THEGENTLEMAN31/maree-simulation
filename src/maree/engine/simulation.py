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
from maree.domain.events import Event, EventType, validate
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

#: A1 — 86 400 s par jour simulé, un tick = 10 s.
TICKS_PER_DAY = 8640

#: A1 — la préhistoire : qui parle, à qui, de quoi, et quand.
#:
#: Ce n'est **pas** une génération LLM, mais ce ne sont pas non plus des
#: souvenirs posés dans le vide : chaque entrée produit un vrai
#: `agent.message.sent` / `agent.message.heard` entre deux agents réels,
#: daté d'un tick négatif (J-3 = -25 920). Le destinataire s'en souvient
#: avec le nom de celui qui lui a parlé — c'est ce que A1 appelle « un
#: échange vieux de plusieurs jours simulés ».
#:
#: Pourquoi pas de LLM ici : une préhistoire générée serait rejouable
#: (elle serait journalisée, comme toute décision, E3), mais elle
#: coûterait des appels **avant** le premier tick et rendrait l'ablation
#: A1 non appariable (deux passés générés ne sont pas le même passé). La
#: table est donc un choix de protocole, pas une contrainte de rejeu.
#:
#: (jours avant la fête, nature pour le destinataire, contenu, profil qui parle)
PREHISTORY: dict[str, tuple[tuple[int, str, str, str], ...]] = {
    "securite": (
        (3, "briefing", "la sortie B se bouche dès qu'il y a du monde, la C reste fluide", "securite"),
    ),
    "habitue": (
        (3, "entendu", "la sortie C évite la passerelle et la foule", "securite"),
    ),
    "famille": (
        (2, "entendu", "la sortie B se bouche dès qu'il y a du monde", "securite"),
    ),
    "visiteur": (
        (3, "entendu", "la sortie C existe, derrière les stands ouest", "habitue"),
    ),
    "vendeur": (
        (1, "entendu", "la sortie A avait fermé l'an dernier", "vendeur"),
    ),
}

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
    #: A2/B3 — couper la diffusion ne doit pas être un commentaire dans le
    #: code : c'est un bras d'expérience, donc un champ de configuration
    #: qui entre dans `config_hash`.
    communication: bool = True
    #: A1 — nombre de jours simulés de préhistoire (0 = aucun passé).
    prehistory_days: int = 0
    #: D3 — pause réelle entre deux ticks. 0 = aussi vite que possible
    #: (campagnes) ; > 0 = mode démonstration, où un humain peut injecter.
    tick_delay_s: float = 0.0
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
                "communication": self.communication,
                "prehistory_days": self.prehistory_days,
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
    #: E4 — coût réel, agrégé depuis les traces.
    tokens_in: int = 0
    tokens_out: int = 0
    #: C6 — décisions fondées sur une information qui n'était pas encore
    #: disponible. Attendu : zéro.
    temporal_violations: int = 0
    #: F4 — événements isolés dans `invalid.jsonl`.
    quarantined: int = 0


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
    #: Tick où le proche a disparu, pour borner la recherche.
    missing_kin_since: int | None = None
    decisions: int = 0
    spoke: bool = False
    #: D2 — la dernière décision, telle que l'interface l'affiche : raison,
    #: règle appliquée pour un agent à règles, passages et souvenirs.
    last: dict[str, Any] = field(default_factory=dict)

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
        models: dict[str, str] | None = None,
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
            llm=llm,
            retriever=retriever,
            memory=memory,
            plan=plan,
            models=models,
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
        self._tokens_in = 0
        self._tokens_out = 0
        self._violations = 0
        self._quarantined = 0
        #: F6 — premier `seq` non encore référencé par un bloc d'indicateurs.
        self._source_from = 1
        #: D3 — commandes d'injection reçues de l'extérieur, drainées en
        #: tête de `_world_events` : une commande arrivée pendant le tick
        #: est perçue au tick suivant, jamais au milieu d'une perception.
        self._inbox: list[dict[str, Any]] = []
        self._bus_failures = 0
        self._last_bus_error: str | None = None
        self._t0 = time.monotonic()
        #: Instant (s simulées) du premier signal de danger et du dernier
        #: sorti — les deux bornes de I7. `None` tant qu'ils n'ont pas eu
        #: lieu : un run sans signal n'a pas de délai, il n'en a pas un de
        #: zéro.
        self._first_signal_s: float | None = None
        self._last_exit_s: float | None = None
        #: B4 — de quoi reconstruire la chaîne causale sans relire le
        #: journal : le dernier événement de monde par nature, le dernier
        #: message émis par (émetteur, tick), la dernière décision par
        #: agent, et le dernier bloc d'indicateurs.
        self._signal_events: dict[str, Event] = {}
        self._message_events: dict[tuple[str, int], Event] = {}
        self._last_decision: dict[AgentId, Event] = {}
        self._last_indicators: Event | None = None

    # ---- contrôle (D3) -----------------------------------------
    def submit(self, command: dict[str, Any]) -> None:
        """Reçoit une commande d'injection depuis l'extérieur.

        Elle n'est **pas** appliquée ici : elle est mise en file et drainée
        en tête du tick suivant. C'est ce qui préserve la perception figée
        (décision 10) — on n'injecte jamais une fumée au milieu d'une
        perception, sous peine que deux agents voient deux mondes.
        """
        self._inbox.append(dict(command))

    async def _drain_injections(self, tick: int) -> None:
        """Applique les commandes reçues : journalisées avant d'agir."""
        while self._inbox:
            command = self._inbox.pop(0)
            kind = str(command.get("kind", ""))
            params = {k: v for k, v in command.items() if k not in ("type", "kind")}
            injection = await self._emit(
                tick,
                EventType.INJECTION,
                {"kind": kind, "params": params, "source": command.get("source", "ui")},
            )
            match kind:
                case "smoke":
                    self._smoke_active = True
                    self._signal(tick)
                    self._recent.append(f"t{tick} fumée injectée")
                    self._signal_events["smoke"] = await self._emit(
                        tick,
                        EventType.WORLD_SMOKE,
                        {
                            "position": list(
                                params.get("position") or self._cfg.smoke_position
                            ),
                            "radius": float(
                                params.get("radius") or self._cfg.smoke_radius
                            ),
                        },
                        cause=injection,
                    )
                case "announcement":
                    text = str(params.get("text") or self._cfg.announcement or "")
                    self._announcement = text
                    self._signal(tick)
                    self._recent.append(f"t{tick} annonce injectée")
                    self._signal_events["announcement"] = await self._emit(
                        tick, EventType.ANNOUNCEMENT, {"text": text}, cause=injection
                    )
                case "exit_closed":
                    exit_id = str(params.get("exit", ""))
                    if exit_id in self._exits_open:
                        self._exits_open.discard(exit_id)
                        self._physics.close_exit(exit_id)
                        self._signal(tick)
                        self._recent.append(f"t{tick} sortie {exit_id} fermée")
                        self._signal_events["exit_closed"] = await self._emit(
                            tick, EventType.EXIT_CLOSED, {"exit": exit_id}, cause=injection
                        )
                case _:
                    # Une commande inconnue n'arrête pas le monde : elle est
                    # isolée et comptée, comme tout événement non conforme.
                    self._quarantined += 1
                    self._journal.quarantine(
                        injection, [f"kind d'injection inconnu : {kind!r}"]
                    )
                    await self._emit(
                        tick,
                        EventType.INVALID,
                        {"type": "control.injection", "problems": [f"kind inconnu : {kind}"]},
                        cause=injection,
                    )

    # ---- journal ----------------------------------------------
    async def _emit(
        self,
        tick: int,
        type_: EventType,
        data: dict[str, Any],
        *,
        cause: Event | None = None,
    ) -> Event:
        """Écrit un événement et le publie.

        `cause` établit la chaîne causale (B4) : l'événement sait lequel
        l'a provoqué, et `correlation_id` remonte à la racine. Sans cause
        explicite (instantané, indicateurs agrégés), le champ reste vide —
        prétendre le contraire serait mentir sur la traçabilité.
        """
        self._seq += 1
        if cause is not None:
            event = cause.child(
                seq=self._seq,
                type=type_,
                t_prod=tick,
                t_trait=tick,
                t_real=time.monotonic() - self._t0,
                data=data,
            )
        else:
            event = Event(
                seq=self._seq,
                run_id=self._cfg.run_id,
                type=type_,
                t_prod=tick,
                t_trait=tick,
                t_real=time.monotonic() - self._t0,
                data=data,
            )
        # F4 — un événement non conforme n'entre pas dans le journal
        # principal : il part en quarantaine et laisse un `dlq.invalid` à sa
        # place. Un consommateur strict (le client, le rejeu) ne rencontre
        # donc jamais une ligne qu'il ne sait pas lire.
        problems = validate(event)
        if problems:
            self._quarantined += 1
            self._journal.quarantine(event, problems)
            event = Event(
                seq=event.seq,
                run_id=event.run_id,
                type=EventType.INVALID,
                t_prod=event.t_prod,
                t_trait=event.t_trait,
                t_real=event.t_real,
                causation_id=event.causation_id,
                correlation_id=event.correlation_id,
                data={"type": str(type_), "problems": problems},
            )
        self._journal.append(event)
        topic = {
            EventType.DECISION: TOPIC_DECISIONS,
            EventType.EVACUATED: TOPIC_DECISIONS,
            EventType.NARRATIVE: TOPIC_NARRATIVE,
            EventType.INDICATORS: TOPIC_METRICS,
        }.get(type_, TOPIC_WORLD)
        # Le bus est une diffusion, pas une persistance (décision 1) : un
        # broker mort ne doit pas tuer un run rejouable. L'échec est compté
        # et visible, jamais silencieux.
        try:
            await self._bus.publish(topic, event)
        except Exception as exc:
            self._bus_failures += 1
            self._last_bus_error = f"{type(exc).__name__}: {exc}"[:200]
        return event

    # ---- population -------------------------------------------
    def _spawn(self) -> None:
        index = 0
        #: Proche déjà placé, en attente de son pair (profil famille).
        attente: AgentRuntime | None = None
        attente_pos: Point | None = None
        attente_zone: Zone | None = None
        for entry in self._cfg.population:
            profile = get_profile(entry.profile)
            # Le profil nommé décrit un SAVOIR ; `kind` décide du MOTEUR.
            # Sans ce `replace`, les 48 agents « à règles » appelleraient
            # le LLM : c'est exactement le bug qui rendrait le run
            # impossible à terminer.
            if entry.kind == "rules":
                profile = replace(profile, kind="rules")
            for _ in range(entry.count):
                index += 1
                agent_id = f"A{index:02d}"
                # Une famille arrive ensemble : le second proche est placé à
                # moins de 2 m du premier, **dans la même zone**. Apparier
                # après coup deux tirages indépendants les séparait de plus
                # de 10 m, et 14 des 16 agents « famille » cherchaient un
                # proche dès le tick 1.
                if entry.profile == "famille" and attente is not None:
                    zone = attente_zone or self._spawn_zone(entry.profile)
                    position = self._near_point(attente_pos, zone)
                else:
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
                if entry.profile == "famille":
                    if attente is None:
                        attente, attente_pos, attente_zone = runtime, position, zone
                    else:
                        runtime.kin = attente.agent_id
                        attente.kin = runtime.agent_id
                        attente, attente_pos, attente_zone = None, None, None

    def _near_point(self, origin: Point | None, zone: Zone) -> Point:
        """Un point de la zone à moins de 2 m de `origin`."""
        if origin is None:
            return self._sample_in_zone(zone)
        for _ in range(200):
            angle = self._rng.uniform(0.0, 2.0 * math.pi)
            radius = self._rng.uniform(0.8, 1.8)
            point = (
                origin[0] + radius * math.cos(angle),
                origin[1] + radius * math.sin(angle),
            )
            if zone.contains(point):
                return point
        return self._sample_in_zone(zone)

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
        if cfg.prehistory_days:
            await self._seed_prehistory()
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
                    self._last_exit_s = cfg.clocks.tick_to_seconds(tick)
                    runtime.intention = Intention(
                        IntentionKind.GO_EXIT, None, "sorti", tick
                    )
                    await self._emit(
                        tick,
                        EventType.EVACUATED,
                        {"agent_id": agent_id, "kind": "exit"},
                        cause=self._last_decision.get(agent_id),
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

            for agent_id, reason, intention, trace, context in results:
                await self._apply(
                    agent_id,
                    intention,
                    trace,
                    percepts[agent_id],
                    positions,
                    trigger=reason,
                    context=context,
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
                signal_s=self._first_signal_s,
                last_exit_s=self._last_exit_s,
            )
            self._events.append(ind)
            # F6 — la plage de `seq` qui a produit cette valeur. Le client
            # peut donc répondre à « d'où sort ce chiffre ? » sans deviner,
            # et sans dépendre d'offsets Kafka (le journal n'en a pas).
            payload = ind.to_dict()
            payload["sources"] = {
                "from_seq": self._source_from,
                "to_seq": self._seq,
                "count": self._seq - self._source_from + 1,
            }
            self._last_indicators = await self._emit(
                tick, EventType.INDICATORS, payload
            )
            self._source_from = self._last_indicators.seq + 1
            await self._emit(tick, EventType.SNAPSHOT, self._snapshot(tick))

            # --- 8. chroniqueur ----------------------------------
            if self._narrator and self._narrator.due(tick) and not self._all_out():
                await self._narrate(ind, states, tick)

            if self._all_out():
                break
            if cfg.tick_delay_s:
                await asyncio.sleep(cfg.tick_delay_s)

        duration = time.monotonic() - self._t0
        await self._emit(
            tick,
            EventType.RUN_ENDED,
            {
                "ticks": tick,
                "llm_calls": self._llm_calls,
                "llm_ok": self._llm_ok,
                "tokens_in": self._tokens_in,
                "tokens_out": self._tokens_out,
                "duration_s": round(duration, 3),
                "temporal_violations": self._violations,
                "quarantined": self._quarantined,
                "bus_failures": self._bus_failures,
                "bus_error": self._last_bus_error,
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
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            temporal_violations=self._violations,
            quarantined=self._quarantined,
            duration_s=duration,
        )

    # ---- étapes ------------------------------------------------
    def _signal(self, tick: int) -> None:
        """Retient l'heure du **premier** signal de danger (borne basse de I7).

        Fumée, annonce et fermeture d'issue comptent toutes : ce qui
        compte pour I7, c'est le premier indice que la situation a changé,
        pas celui qui a fait bouger le plus de monde.
        """
        if self._first_signal_s is None:
            self._first_signal_s = self._cfg.clocks.tick_to_seconds(tick)

    async def _world_events(self, tick: int) -> None:
        cfg = self._cfg
        await self._drain_injections(tick)
        if tick == cfg.smoke_tick and not self._smoke_active:
            self._smoke_active = True
            self._signal(tick)
            self._recent.append(f"t{tick} fumée près de la scène")
            self._signal_events["smoke"] = await self._emit(
                tick,
                EventType.WORLD_SMOKE,
                {"position": list(cfg.smoke_position), "radius": cfg.smoke_radius},
            )
        if cfg.close_exit and tick == cfg.close_tick and cfg.close_exit in self._exits_open:
            self._exits_open.discard(cfg.close_exit)
            self._physics.close_exit(cfg.close_exit)
            self._signal(tick)
            self._recent.append(f"t{tick} sortie {cfg.close_exit} fermée")
            self._signal_events["exit_closed"] = await self._emit(
                tick, EventType.EXIT_CLOSED, {"exit": cfg.close_exit}
            )
        if cfg.announcement_tick and tick == cfg.announcement_tick:
            self._announcement = cfg.announcement
            self._signal(tick)
            self._recent.append(f"t{tick} annonce officielle")
            self._signal_events["announcement"] = await self._emit(
                tick, EventType.ANNOUNCEMENT, {"text": cfg.announcement}
            )

    async def _seed_prehistory(self) -> None:
        """A1 — le passé des agents LLM, fait d'échanges réels et datés.

        Trois propriétés, et chacune répond à une exigence :

          1. **c'est un échange** : un agent parle, un autre écoute, les
             deux événements sont journalisés (`message.sent` / `heard`) ;
          2. **c'est daté** : tick négatif (J-3 = -25 920), pas un
             souvenir antidaté à t0 — sinon C6 ne saurait plus distinguer
             un souvenir ancien d'une perception du tick ;
          3. **c'est rejouable** : les échanges sont journalisés, donc le
             rejeu les relit sans rappeler un modèle (E3). Le contenu vient
             d'une table non par nécessité de rejeu — un passé généré serait
             rejouable lui aussi — mais pour que l'ablation A1 compare deux
             passés strictement identiques et ne paie rien avant t0.

        Seuls les agents LLM reçoivent ce passé : A1 porte sur eux, et
        donner une mémoire à un agent à règles laisserait croire qu'il
        s'en sert.
        """
        days = self._cfg.prehistory_days
        # Qui peut parler : n'importe quel agent. Un agent à règles est une
        # personne aussi — c'est sa **mémoire** qui n'existe pas, pas sa
        # parole. Restreindre les émetteurs aux LLM rendait la préhistoire
        # muette dès qu'un profil n'avait qu'un agent LLM.
        speakers: dict[str, list[AgentId]] = {}
        for agent_id, runtime in sorted(self._agents.items()):
            speakers.setdefault(runtime.profile.id, []).append(agent_id)

        episodes = 0
        listeners: set[AgentId] = set()
        for listener, runtime in sorted(self._agents.items()):
            if runtime.profile.kind != "llm":
                continue
            for day, kind, content, speaker_profile in PREHISTORY.get(
                runtime.profile.id, ()
            ):
                if day > days:
                    continue
                candidates = [
                    a for a in speakers.get(speaker_profile, ()) if a != listener
                ]
                if not candidates:
                    continue
                speaker = candidates[0]
                tick = -day * TICKS_PER_DAY
                sent = await self._emit(
                    tick,
                    EventType.MESSAGE_SENT,
                    {"from": speaker, "to": [listener], "content": content},
                )
                await self._emit(
                    tick,
                    EventType.MESSAGE_HEARD,
                    {"agent_id": listener, "from": speaker, "content": content},
                    cause=sent,
                )
                self._memory.remember(
                    listener,
                    Episode(
                        tick=tick,
                        kind=kind,
                        content=f"{speaker} m'a dit : {content}",
                        source="prehistoire",
                        salience=0.6,
                    ),
                )
                if self._agents[speaker].profile.kind == "llm":
                    self._memory.remember(
                        speaker,
                        Episode(
                            tick=tick,
                            kind="dit",
                            content=f"j'ai dit à {listener} : {content}",
                            source="prehistoire",
                            salience=0.4,
                        ),
                    )
                episodes += 1
                listeners.add(listener)

        await self._emit(
            0,
            EventType.MEMORY_SEEDED,
            {
                "agents": len(listeners),
                "days": days,
                "episodes": episodes,
                "exchanges": episodes,
            },
        )

    def _check_temporal(
        self, agent_id: AgentId, percept: Percept, context: dict[str, Any] | None
    ) -> list[str]:
        """C6 — tout ce que la décision cite existait-il à l'instant T ?

        Trois sources, trois vérifications : un message ne peut pas être
        daté après la perception, un passage RAG ne peut pas être publié
        après le tick simulé, et le signal qui a déclenché la décision ne
        peut pas venir du futur. Le mode asynchrone (C4) ne crée **pas**
        de violation : un décalage `t_trait - t_prod` est mesuré à part.
        """
        problems: list[str] = []
        for message in percept.messages:
            if message.tick > percept.tick:
                problems.append(
                    f"message de {message.sender} daté t{message.tick} > t{percept.tick}"
                )
        for passage in (context or {}).get("retrieved", ()):
            available = (passage.get("metadata") or {}).get("available_tick")
            if available is not None and int(available) > percept.tick:
                problems.append(
                    f"passage {passage.get('doc_id')} publié t{available} > t{percept.tick}"
                )
        for cause in (self._signal_events.get("smoke"),):
            if cause is not None and cause.t_prod > percept.tick:
                problems.append(f"fumée produite t{cause.t_prod} > t{percept.tick}")
        return problems

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
        # `missing_kin` est un signal persistant : on le mémorise pour qu'il
        # ne redéclenche pas à chaque tick, et on le réarme si le proche
        # réapparaît. Sans cela, 142 des 202 appels LLM d'un run venaient
        # de ce seul déclencheur — le piège de la v1, sous une autre forme.
        runtime.missing_kin = missing
        if not missing:
            runtime.known_signals.discard("missing_kin")
            runtime.missing_kin_since = None
        elif runtime.missing_kin_since is None:
            runtime.missing_kin_since = tick
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
            missing_kin_ticks=(
                tick - runtime.missing_kin_since
                if missing and runtime.missing_kin_since is not None
                else 0
            ),
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
    ) -> list[
        tuple[AgentId, str, Intention, dict[str, Any] | None, dict[str, Any]]
    ]:
        """Décisions concurrentes, mais **appliquées** dans l'ordre canonique.

        Le `contexte` (passages retrouvés, souvenirs rappelés) est journalisé
        avec la décision : sans lui, F2 (« montrez ce qui a été retrouvé »)
        n'est pas recalculable après coup, et D2 ne peut pas expliquer une
        décision dans l'interface.
        """
        semaphore = asyncio.Semaphore(self._cfg.max_concurrency)
        out: list[
            tuple[AgentId, str, Intention, dict[str, Any] | None, dict[str, Any]]
        ] = []

        async def one(agent_id: AgentId, reason: str) -> None:
            runtime = self._agents[agent_id]
            percept = percepts[agent_id]
            async with semaphore:
                context: dict[str, Any] = {}
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
                    if state.get("passages"):
                        context["retrieved"] = state["passages"]
                    if state.get("memories"):
                        context["memory"] = state["memories"]
                    self._llm_calls += 1
                    if trace:
                        trace["fallback"] = bool(state.get("fallback"))
                        if trace.get("ok"):
                            self._llm_ok += 1
                        self._tokens_in += int(trace.get("tokens_in") or 0)
                        self._tokens_out += int(trace.get("tokens_out") or 0)
            out.append((agent_id, reason, intention, trace, context))

        await asyncio.gather(*(one(a, r) for a, r in todo))
        return sorted(out, key=lambda x: x[0])

    # ---- causalité (B4) ---------------------------------------
    def _cause_for(self, trigger: str, percept: Percept) -> Event | None:
        """Quel événement a provoqué cette décision ?

        Une décision périodique n'a pas de cause externe : elle vient du
        filet de sécurité, pas du monde. On ne lui invente donc pas un
        parent — c'est précisément ce que B4 doit rendre lisible.
        """
        if trigger == "fumee_visible":
            return self._signal_events.get("smoke")
        if trigger == "annonce":
            return self._signal_events.get("announcement")
        if trigger == "sortie_fermee":
            return self._signal_events.get("exit_closed")
        if trigger.startswith("message:"):
            sender = trigger.split(":", 1)[1]
            for msg in reversed(percept.messages):
                if msg.sender == sender:
                    return self._message_events.get((msg.sender, msg.tick))
        return None

    async def _apply(
        self,
        agent_id: AgentId,
        intention: Intention,
        trace: dict[str, Any] | None,
        percept: Percept,
        positions: dict[AgentId, Point],
        *,
        trigger: str,
        context: dict[str, Any] | None = None,
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
        elif trigger == "proche_disparu":
            runtime.known_signals.add("missing_kin")

        # --- destination physique (décision 8) -------------------
        match intention.kind:
            case (IntentionKind.GO_EXIT | IntentionKind.GUIDE) if (
                intention.target in self._plan.exits
            ):
                self._physics.set_destination(
                    agent_id, Destination.to_exit(intention.target)  # type: ignore[arg-type]
                )
            case IntentionKind.FOLLOW:
                if intention.target in positions:
                    self._physics.set_destination(
                        agent_id, Destination.follow(intention.target)  # type: ignore[arg-type]
                    )
                else:
                    # Le meneur n'est pas un agent (ou a déjà disparu) :
                    # rester sur place n'est pas une option. On rejoint sa
                    # propre sortie — sinon l'agent se fige jusqu'à la fin.
                    best = runtime.best_exit()
                    self._physics.set_destination(
                        agent_id,
                        Destination.to_exit(best)
                        if best
                        else Destination.to_point(percept.position),
                    )
            case IntentionKind.GO_ZONE if intention.target in self._plan.zones:
                self._physics.set_destination(
                    agent_id, Destination.to_point(self._plan.zones[intention.target].centroid)
                )
            case IntentionKind.SEARCH:
                # Chercher un proche ne veut pas dire marcher vers
                # `walkable[0]`, un sommet du domaine posé sur la limite —
                # souvent dans une issue. Les agents « cherchaient » en
                # sortant. On cherche dans la zone où l'on est.
                zone = self._plan.zones.get(percept.zone) if percept.zone else None
                self._physics.set_destination(
                    agent_id,
                    Destination.to_point(zone.centroid if zone else percept.position),
                )
            case _:
                self._physics.set_destination(
                    agent_id, Destination.to_point(percept.position)
                )

        # --- croyance -------------------------------------------
        if (
            intention.kind in {IntentionKind.GO_EXIT, IntentionKind.GUIDE}
            and intention.target in self._plan.exits
        ):
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
        if context:
            data.update(context)
        # C6 — vérifié **avant** l'écriture : une décision fondée sur une
        # information future est signalée, pas passée sous silence.
        violations = self._check_temporal(agent_id, percept, context)
        if violations:
            self._violations += len(violations)
            data["temporal_violations"] = violations
        # D2 — ce que l'interface affiche au clic sur l'agent, sans avoir à
        # reconstruire depuis trois événements.
        runtime.last = {
            "tick": percept.tick,
            "kind": data["kind"],
            "trigger": trigger,
            "reason": intention.reason,
            # Un agent à règles n'a pas de justification générée : sa
            # « règle » est la règle, et c'est cela qu'il faut montrer.
            "rule": intention.reason if runtime.profile.kind == "rules" else None,
            "intention": intention.to_dict(),
            "retrieved": [p.get("doc_id") for p in data.get("retrieved", ())],
            "memory": data.get("memory", ()),
        }
        cause = self._cause_for(trigger, percept)
        decision = await self._emit(
            percept.tick, EventType.DECISION, data, cause=cause
        )
        self._last_decision[agent_id] = decision
        for problem in violations:
            await self._emit(
                percept.tick,
                EventType.TEMPORAL_VIOLATION,
                {"agent_id": agent_id, "reason": problem},
                cause=decision,
            )
        await self._emit(
            percept.tick,
            EventType.BELIEF_UPDATED,
            {"agent_id": agent_id, "beliefs": runtime.beliefs.snapshot()},
            cause=decision,
        )

    async def _diffuse(self, tick: int, positions: dict[AgentId, Point]) -> None:
        """Un agent qui vient de comprendre prévient ses voisins. Une fois."""
        # A2/B3 — bras « sans communication ». Ce n'est pas un mode dégradé :
        # c'est le contrôle négatif qui montre que I1 mesure bien une
        # émergence sociale et pas la ressemblance de réponses d'un modèle.
        if not self._cfg.communication:
            return
        for agent_id in sorted(self._agents):
            runtime = self._agents[agent_id]
            if runtime.evacuated or runtime.spoke or runtime.intention is None:
                continue
            if runtime.intention.kind not in {
                IntentionKind.GO_EXIT,
                IntentionKind.GUIDE,
            }:
                continue
            # Un guide qui n'a rien perçu ne lance pas une évacuation. Sans
            # ce garde-fou, deux agents de sécurité qui « guident » au tick 1
            # (leur métier, sans danger) envoyaient « il faut sortir par… » ;
            # tout message reçu valant signal de danger, la foule sortait
            # avant la fumée de t10. Mesuré : 6 à 12 sorties à t9.
            if not (
                runtime.known_signals or runtime.known_messages or runtime.missing_kin
            ):
                continue
            best = runtime.best_exit()
            if not best or runtime.beliefs.confidence(best) < 0.6:
                continue
            runtime.spoke = True
            claim = f"sortie_{best}"
            content = f"il faut sortir par la sortie {best}"
            voisins = self._neighbours(agent_id, positions)
            sent = await self._emit(
                tick,
                EventType.MESSAGE_SENT,
                {"from": agent_id, "to": voisins, "content": content},
                cause=self._last_decision.get(agent_id),
            )
            self._message_events[(agent_id, tick)] = sent
            for other in voisins:
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
                    cause=sent,
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
        llm_trace = narrative.llm or {}
        self._tokens_in += int(llm_trace.get("tokens_in") or 0)
        self._tokens_out += int(llm_trace.get("tokens_out") or 0)
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
            cause=self._last_indicators,
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
        n_exits = len(self._plan.exits)
        active = [
            positions.get(aid, (0.0, 0.0))
            for aid, rt in sorted(self._agents.items())
            if not rt.evacuated
        ]
        return {
            "tick": tick,
            "sim_time": SimClock(tick, self._cfg.clocks).fmt(),
            "exits_open": sorted(self._exits_open),
            # La fumée est un événement ponctuel : un client qui se connecte
            # après t10 ne la verrait jamais sans cet état.
            "smoke_active": self._smoke_active,
            # Grille de densité prête à dessiner (cellules occupées seules).
            "density_grid": metrics.density_cells(active),
            "agents": [
                {
                    "id": aid,
                    "profile": rt.profile.id,
                    "label": rt.profile.label,
                    "kind": rt.profile.kind,
                    "pos": list(positions.get(aid, (0.0, 0.0))),
                    "belief": rt.best_exit(),
                    "confidence": round(
                        rt.beliefs.confidence(rt.best_exit()) if rt.best_exit() else 0.0, 3
                    ),
                    # Croyance complète : le client n'a pas à la reconstruire
                    # depuis les décisions, et peut colorer un dégradé.
                    "beliefs": rt.beliefs.snapshot(),
                    "entropy": round(rt.beliefs.entropy(n_exits), 3),
                    "intention": rt.intention.kind if rt.intention else None,
                    "intention_target": rt.intention.target if rt.intention else None,
                    "evacuated": rt.evacuated,
                    "kin": rt.kin,
                    "decided_at": rt.last_decision_tick,
                    # Ce que l'agent a perçu : « smoke », « announcement »,
                    # « closed:A », « missing_kin ».
                    "perceived": sorted(rt.known_signals),
                    # D2 — l'inspection d'un agent ne demande plus de
                    # recoller croyance + dernière décision + mémoire :
                    # tout est là, dans l'ordre où l'interface l'affiche.
                    "memory": [
                        e.to_dict()
                        for e in self._memory.recall(aid, k=3, tick=tick)
                    ],
                    "last_decision": rt.last or None,
                }
                for aid, rt in sorted(self._agents.items())
            ],
        }

    def _all_out(self) -> bool:
        return all(a.evacuated for a in self._agents.values())
