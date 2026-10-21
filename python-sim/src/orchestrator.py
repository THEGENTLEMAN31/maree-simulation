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
import zlib
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
    trapped: bool = False
    belief_safe_exit: str | None = None
    belief_danger: bool = False
    exit_code: str | None = None
    decisions: int = 0
    last_action: str | None = None
    last_exit: str | None = None


class Orchestrator:
    """Contrôle l'exécution d'un run complet."""

    def __init__(
        self,
        config: SimulationConfig,
        *,
        kafka_bootstrap: str = "redpanda:9092",
        llm_base_url: str | None = None,
        corpus_path: str = "/world_corpus",
        dry_run: bool = False,
        kafka_memory: bool | None = None,
    ) -> None:
        self.config = config
        self.kafka_bootstrap = kafka_bootstrap
        # La base URL peut venir de la config YAML (clé llm.base_url) — utile
        # pour les bancs d'essai locaux (Ollama) sans toucher au code.
        self.llm_base_url = llm_base_url or config.llm.get("base_url", "http://llama-cpp:8081/v1")
        self.corpus_path = corpus_path
        self.dry_run = dry_run
        # Kafka en mémoire : par défaut activé en dry_run, sinon réseau réel.
        self.kafka_memory = kafka_memory if kafka_memory is not None else dry_run

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
            config.mode,
            self.clock,
            self.rng,
            default_think_interval=20,
            sync_period=config.world.decision_period_sync,
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
        self.gateway = LLMGateway(self.llm_base_url, dry_run=dry_run)
        for a in self.llm_agents:
            a.gateway = self.gateway

        # RAG (F1) injecté dans les agents LLM. La passerelle est partagée :
        # les embeddings passent par le même point d'entrée (décision 7).
        self.rag = RagClient(gateway=self.gateway)
        for a in self.llm_agents:
            a.rag = self.rag

        # Leviers expérimentaux (X2, X5, X6, X7 ; contrôle B3). Ils modifient
        # réellement le comportement, sinon les expériences ne mesurent rien.
        self._apply_experiment_levers()
        # A1 : échanges des jours d'avant (mémoire longue). Coupés par le
        # levier `memory` (X5), ils ne doivent pas subsister autrement.
        self._seed_pre_exchanges()

        self.indicators = Indicators()
        self.oracle = TemporalOracle()

        self.kafka = KafkaClient(kafka_bootstrap, config.run_id, memory=self.kafka_memory)
        self.logger = RunLogger(config.run_id, config.log_dir)
        self.ws = WSRelay(port=8765, enabled=not dry_run)
        self.ws.on_command = self._handle_control

        self._state: dict = {"announcements": [], "false_infos": []}
        self._indicator_history: list[dict] = []
        self._offset_high_water: dict[str, int] = field(default_factory=dict)
        self._follow: list[bool] = []
        # X4 : agents à règles « miroirs » des agents LLM (même profil, même id).
        self._rules_shadow: dict[str, object] = {}

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
        n_passages = await self.rag.ingest_directory_async(self.corpus_path)

        self._emit_spawn()
        limits = max_ticks or self.config.max_ticks

        # e2e : on attend le client Godot avant de simuler, sinon un run

        # court peut finir avant sa connexion (course de démarrage).

        if self.config.wait_for_client and self.ws.enabled:

            waited = 0.0

            while not self.ws.clients and waited < self.config.wait_for_client_timeout_s:

                await asyncio.sleep(0.2)

                waited += 0.2

            print(f"[orchestrateur] client WS attendu : {len(self.ws.clients)} connecté(s) après {waited:.1f} s", flush=True)


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
        # I5 / F5 : les violations temporelles doivent exister dans le journal,
        # pas seulement dans un compteur Python — sinon la requête SQL de
        # contrôle ne peut rien vérifier.
        for v in self.oracle.violations:
            self._journal(
                "oracle",
                evmod.new_envelope(
                    self.config.run_id,
                    "oracle.violation",
                    t_prod=v.tick,
                    t_trait=v.tick,
                    agent_id=v.agent_id,
                    data={
                        "detail": v.detail,
                    },
                ),
            )
        summary = self.gateway.cost_log.summary()
        summary["run_id"] = self.config.run_id
        summary["mode"] = self.config.mode
        summary["passages_ingested"] = n_passages
        summary["temporal_violations"] = len(self.oracle.violations)
        summary["config_hash"] = self.config.config_hash()
        summary.update(self._experiment_summary())
        await self.kafka.close()
        await self.ws.close()
        self.logger.close()
        return summary

    def _experiment_summary(self) -> dict:
        """Métriques exploitables par le protocole X1–X7 (E2, B2, F2).

        On expose les indicateurs (médiane et valeur finale), la distribution
        des sorties, et de quoi tester X5/X6/X7 sans relire les journaux.
        """
        import statistics

        series = self._indicator_history
        i1 = [s["I1_consensus"] for s in series]
        i2 = [s["I2_belief_gap"] for s in series]
        i4 = [s["I4_leader_follow"] for s in series]

        def med(vals: list[float]) -> float:
            return round(statistics.median(vals), 4) if vals else 0.0

        exits: dict[str, int] = {}
        evacuated = 0
        trapped = 0
        for a in self.agents:
            rt = self.runtime[a.agent_id]
            if rt.evacuated:
                evacuated += 1
                code = rt.exit_code or rt.belief_safe_exit or "?"
                exits[code] = exits.get(code, 0) + 1
            if rt.trapped:
                trapped += 1

        llm_decisions = sum(
            self.runtime[a.agent_id].decisions for a in self.llm_agents
        )
        rag_citations = sum(getattr(a, "rag_citations", 0) for a in self.llm_agents)
        drifts = sum(len(getattr(a, "drift_events", [])) for a in self.llm_agents)

        return {
            # B2 : indicateurs (médiane sur le run + valeur finale)
            "I1_median": med(i1),
            "I1_final": i1[-1] if i1 else 0.0,
            "I2_median": med(i2),
            "I2_final": i2[-1] if i2 else 0.0,
            "I4_median": med(i4),
            "I4_final": i4[-1] if i4 else 0.0,
            "I3_evacuated": evacuated,
            "I3_evacuated_ratio": round(evacuated / max(1, len(self.agents)), 4),
            "I3_trapped": trapped,
            "I3_trapped_ratio": round(trapped / max(1, len(self.agents)), 4),
            "I5_temporal_violations": len(self.oracle.violations),
            "exit_distribution": exits,
            # F2 / X7 : part des décisions LLM ayant cité un passage retrouvé
            "rag_citation_rate": round(rag_citations / max(1, llm_decisions), 4),
            "rag_degraded": bool(getattr(self.rag, "degraded", False)),
            # A4 : dérives de parsing LLM
            "llm_drifts": drifts,
            "llm_decisions": llm_decisions,
            # X5/X6 : décisions finales par agent (pour comparer les paires)
            "agent_last_exits": {
                a.agent_id: self.runtime[a.agent_id].last_exit
                for a in self.agents
                if self.runtime[a.agent_id].decisions
            },
        }

    # ---------------------------------------------------------------- pas

    async def _run_agent_turns(self, due, tick: int) -> None:
        """Un tour d'agents : perception figée à l'instant T (décision 10).

        Les profils à protocole (sécurité, habitués) décident d'abord : leur
        croyance devient visible pour la foule, ce qui rend le suivi de meneur
        (I4, X2) réellement mesurable. L'ordre reste déterministe.
        """
        rank = {"securite": 0, "habitue": 1}
        ordered = sorted(
            due,
            key=lambda s: (rank.get(self._agent(s.agent_id).profile_name, 2), s.agent_id),
        )
        for sched in ordered:
            agent = self._agent(sched.agent_id)
            rt = self.runtime[sched.agent_id]
            if rt.evacuated or rt.trapped:
                continue
            perception = self._perception_for(agent, tick)
            t_trait = self.scheduler.process(sched, now=tick)

            flags = self.config.world.experiment_flags
            if not flags.get("llm", True):
                # X4 baseline : on force l'agent à utiliser la règle.
                intention = await self._rules_intention(agent, perception)
                explanation = {"kind": "rules_baseline_override"}
            else:
                intention = await agent.decide(perception)
                explanation = self._explanation(agent, perception, intention)

            # A2 : message en langage naturel vers les voisins. Le levier
            # `communication` (contrôle B3) coupe réellement la diffusion.
            pending = getattr(agent, "_pending_message", None)
            if pending and flags.get("communication", True):
                for neighbor in perception.visible_neighbors:
                    self._messages(neighbor, tick, pending, agent.agent_id, t_trait)

            self._apply_intention(agent, intention, tick, t_trait)
            self._record_follow(agent, perception, intention)
            self.scheduler.schedule_next(sched, now=tick)

    def _record_follow(self, agent, perception: Perception, intention) -> None:
        """I4 : l'agent a-t-il suivi la sortie majoritaire de ses voisins ?

        On mesure au moment de la décision, avec les croyances réellement
        visibles (décision 10), et non après coup. Sans voisin informé,
        aucune observation n'est enregistrée.
        """
        code = intention.exit_code
        if not code:
            return
        beliefs = [
            self.runtime[n].belief_safe_exit for n in perception.visible_neighbors
        ]
        beliefs = [b for b in beliefs if b]
        if not beliefs:
            return
        modal = max(set(beliefs), key=beliefs.count)
        self._follow.append(code == modal)

    def _perception_for(self, agent, tick: int) -> Perception:
        rt = self.runtime[agent.agent_id]
        zone = rt.zone
        smoke = self.world.smoke_level > 0 and (
            zone in self.world.smoke_zones or self.world.smoke_zones == {"sud_est"}
        )
        neighbors = self._visible_neighbors(agent, zone)
        # X2 : une fermeture n'est connue que localement (on voit la sortie
        # ou la zone qui y mène). La savoir globalement supprimerait le piège.
        z = self.world.zones.get(zone)
        adjacent = {zone, *(z.neighbors if z else [])}
        blocked = [
            code
            for zid, code in self.world.zone_of_exit.items()
            if self.world.exits[code].blocked and zid in adjacent
        ]
        # Une fermeture déjà constatée par l'agent (il s'y est engagé) reste sue.
        blocked = sorted({*blocked, *getattr(agent, "known_blocked", set())})
        return Perception(
            tick=tick,
            zone=zone,
            smoke_seen=smoke,
            visible_neighbors=neighbors,
            announcements=self._state["announcements"],
            false_infos=self._state["false_infos"],
            exits_known=self._exits_known(agent),
            neighbor_beliefs={
                n: self.runtime[n].belief_safe_exit
                for n in neighbors
                if self.runtime[n].belief_safe_exit
            },
            blocked_exits=blocked,
        )

    async def _rules_intention(self, agent, perception: Perception):
        """Bascule X4 : intention calculée par la **règle**, pas par un repli.

        Utiliser `LLMAgent.fallback_intention()` renvoyait toujours « stay » :
        le bras « règles » de X4 n'évacuait donc personne et le résultat
        (I3 = 0) était un artefact, pas une mesure. On instancie un agent à
        règles de même profil et de même identité, avec une graine dérivée de
        l'identifiant (déterministe et reproductible).
        """
        from .agents.rules_agent import RulesAgent

        shadow = self._rules_shadow.get(agent.agent_id)
        if shadow is None:
            seed = zlib.crc32(agent.agent_id.encode("utf-8"))
            shadow = RulesAgent(
                agent.agent_id, agent.profile_name, random.Random(seed)
            )
            shadow.follow_weight = 0.0
            self._rules_shadow[agent.agent_id] = shadow
        return await shadow.decide(perception)

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
        rt = self.runtime.get(agent_id)
        if agent is None or rt is None:
            # Identifiant inconnu (ou run terminé) : on répond sans planter le
            # relais WebSocket, pour que Godot puisse afficher l'erreur.
            await self.ws.broadcast(
                {"type": "inspection", "agent_id": agent_id, "error": "unknown_agent"}
            )
            return
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
            # La règle a besoin d'une perception : on la reconstruit à
            # l'instant courant (décision 10) au lieu de passer None.
            explain = getattr(agent, "explanation", None)
            perception = self._perception_for(agent, self.clock.now)
            payload["explanation"] = (
                explain(perception) if explain else {"kind": "rules"}
            )
        await self.ws.broadcast(payload)

    def _apply_intention(self, agent, intention, tick: int, t_trait: int) -> None:
        rt = self.runtime[agent.agent_id]
        rt.decisions += 1
        rt.last_action = intention.action
        rt.last_exit = intention.exit_code
        if intention.exit_code:
            rt.belief_safe_exit = intention.exit_code
        if intention.belief_danger is not None:
            rt.belief_danger = intention.belief_danger

        if intention.action == "evacuate":
            # Une sortie fermée ne laisse pas passer : l'agent est piégé.
            # C'est le cœur de X2 (H2) — sans cela, fermer A ne change rien.
            blocked = self.world.exits.get(intention.exit_code or "")
            if blocked is not None and blocked.blocked:
                rt.trapped = True
                # L'agent vient d'apprendre, à ses dépens, que la sortie est
                # fermée : il ne s'y engagera plus (boucle d'apprentissage).
                if not hasattr(agent, "known_blocked"):
                    agent.known_blocked = set()
                agent.known_blocked.add(intention.exit_code)
                self._journal(
                    "world",
                    evmod.new_envelope(
                        self.config.run_id,
                        "movement.trapped",
                        t_prod=tick,
                        t_trait=t_trait,
                        agent_id=agent.agent_id,
                        data={"exit": intention.exit_code},
                    ),
                )
            else:
                rt.evacuated = True
                rt.exit_code = intention.exit_code
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
                    # Décision 12 / F1 : traçabilité des passages réellement
                    # fournis au modèle, et du profil qui l'a décidé.
                    "profile": getattr(agent, "profile_name", None),
                    "kind": "llm" if hasattr(agent, "model") else "rules",
                    "rag_doc_ids": [
                        e.get("doc_id")
                        for e in (getattr(agent, "last_rag", None) or [])
                        if isinstance(e, dict)
                    ],
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

    def _apply_experiment_levers(self) -> None:
        """Active les leviers expérimentaux déclarés dans `world.experiment_flags`.

        Chaque levier change réellement le comportement observable — sans quoi
        l'expérience correspondante (X2, X5, X6, X7, contrôle B3) ne mesure rien.

        - `rag`           (X7) : coupe la récupération de passages.
        - `memory`        (X5) : coupe la mémoire longue (prompt + échanges).
        - `leaders`       (X2) : coupe le suivi du voisin (poids zéro).
        - `communication` (B3) : coupe la diffusion des messages aux voisins.
        - `profiles`      (X6) : échange deux profils entre deux agents LLM.
        """
        flags = self.config.world.experiment_flags
        if not flags:
            return

        use_rag = bool(flags.get("rag", True))
        use_memory = bool(flags.get("memory", True))
        for a in self.llm_agents:
            a.use_rag = use_rag
            a.use_memory = use_memory

        if not flags.get("leaders", True):
            for a in self.rules_agents:
                a.follow_weight = 0.0

        # X6 : échange de profils entre deux agents nommés (A3). Le profil est
        # ce qui pilote priorité, savoir initial et consigne — l'échanger doit
        # changer la décision.
        swap = flags.get("swap_profiles")
        if swap and len(swap) == 2:
            a1, a2 = self._agent(swap[0]), self._agent(swap[1])
            if a1 is not None and a2 is not None and a1 is not a2:
                for attr in ("profile_name", "priority", "knows"):
                    v1, v2 = getattr(a1, attr, None), getattr(a2, attr, None)
                    if hasattr(a1, attr) or hasattr(a2, attr):
                        setattr(a1, attr, v2)
                        setattr(a2, attr, v1)
    def _seed_pre_exchanges(self) -> None:
        """A1 / X5 : mémoire des jours d'avant, injectée avant le run.

        Chaque profil LLM garde un souvenir d'une édition précédente qui
        recommande une sortie différente. Avec le levier `memory` coupé
        (X5_without_mem), ce souvenir n'existe pas : la comparaison porte
        donc réellement sur l'échange préalable, pas sur un détail d'implémentation.
        """
        from .agents.llm_agent import MemoryEntry

        souvenirs = {
            "habitue": (
                "Édition précédente : la sortie C était la plus discrète et la "
                "plus rapide. Les habitués la prennent encore."
            ),
            "securite": (
                "Édition précédente : la sortie A avait dû être fermée en dernier "
                "recours. Le protocole dit de privilégier la sortie la plus proche."
            ),
            "famille": (
                "L'an dernier, avec les enfants, nous sommes sortis par la sortie "
                "B : elle est large et praticable avec une poussette."
            ),
            "visiteur": (
                "La dernière fois, un visiteur m'a dit que la sortie A était la "
                "plus évidente depuis l'entrée principale."
            ),
            "amis": (
                "L'an passé, le groupe est sorti par la sortie B en filmant ; "
                "c'était fluide et sans bousculade."
            ),
        }
        for a in self.llm_agents:
            if not getattr(a, "use_memory", True):
                continue
            text = souvenirs.get(a.profile_name)
            if not text:
                continue
            a.memory.append(
                MemoryEntry(
                    tick=-self.config.world.pre_days_ticks,
                    kind="exchange",
                    text=text,
                    source="edition_precedente",
                    importance=0.9,
                )
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
        trapped = 0
        for a in self.agents:
            rt = self.runtime[a.agent_id]
            beliefs.append((a.agent_id, rt.belief_safe_exit, rt.belief_danger))
            evacuated += 1 if rt.evacuated else 0
            trapped += 1 if rt.trapped else 0
            if rt.evacuated:
                destinations.append((a.agent_id, rt.belief_safe_exit or "A"))
        return IndicatorSet(
            tick=tick,
            beliefs=beliefs,
            evacuated=evacuated,
            trapped=trapped,
            total=len(self.agents),
            ground_truth_safe_exit=self.world.ground_truth_safe_exit(),
            destinations=destinations,
            follow_observations=list(self._follow),
            temporal_violations=len(self.oracle.violations),
        )

    def _messages(self, to_agent: str, tick: int, text: str, sender: str, t_trait: int) -> None:
        # A2 : le destinataire mémorise le message — c'est ce qui met à jour
        # sa croyance, et c'est ce que mesure le contrôle « communication
        # désactivée » (B3) : sans relais, I1 ne peut pas monter.
        dest = self._agent(to_agent)
        if dest is not None and getattr(dest, "use_memory", True) and hasattr(dest, "remember"):
            dest.remember(
                tick, "exchange", f"{sender} m'a dit : « {text[:180]} »", source=sender
            )
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
        """Voisinage local déterministe (A2, I4).

        On ne renvoie pas « les 5 premiers agents » : ce biais rendait tout le
        monde voisin des mêmes agents (des LLM sans croyance), donc l'influence
        sociale était structurellement nulle. On prend les 5 voisins de la même
        zone en tournant autour de l'agent dans l'ordre canonique.
        """
        same_zone = [
            a.agent_id
            for a in self.agents
            if a.agent_id != agent.agent_id and self.runtime[a.agent_id].zone == zone
        ]
        if not same_zone:
            return []
        ids = [a.agent_id for a in self.agents]
        try:
            start = ids.index(agent.agent_id)
        except ValueError:
            return same_zone[:5]
        order = list(reversed(ids[:start])) + list(reversed(ids[start + 1 :]))
        picked = [aid for aid in order if aid in same_zone]
        return picked[:5]

    def _exits_known(self, agent) -> list[str]:
        if agent.profile_name in {"securite", "habitue"}:
            return ["A", "B", "C"]
        # Les visiteurs lisent la signalétique : deux sorties au moins.
        return ["A", "B"]

    async def _handle_control(self, data: dict) -> None:
        """Injection d'événements depuis Godot (D3) + inspection (D2)."""
        # Trace opérationnelle : utile pour vérifier la chaîne Godot -> Python.
        print(f"[orchestrateur] contrôle reçu : {data}", flush=True)
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