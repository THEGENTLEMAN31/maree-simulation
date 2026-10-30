"""Intégration : la boucle à trois horloges, sans GPU ni JuPedSim.

On injecte une physique factice et une population **entièrement à règles**.
Ce que le test prouve :

    * le run se termine et laisse un journal complet ;
    * deux runs de même graine produisent exactement les mêmes indicateurs ;
    * aucune décision LLM n'est prise quand la population est « rules ».

C'est le test qui empêche la régression la plus coûteuse : un run qui
appelle le LLM 60 fois par tick.
"""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import pytest

from maree.adapters.bus import InMemoryBus
from maree.adapters.journal.jsonl import JsonlJournal
from maree.domain.geometry import Plan
from maree.domain.ids import AgentId, Point
from maree.engine.replay import indicators_hash
from maree.engine.simulation import PopulationEntry, RunConfig, Simulation
from maree.memory.store import EventSourcedMemory
from maree.ports import Destination, LLMResult


class FakePhysics:
    """Déplacement en ligne droite vers la destination, 2 m par tick."""

    def __init__(self, plan: Plan, speed_per_step: float = 0.01) -> None:
        self._plan = plan
        self._speed = speed_per_step
        self._pos: dict[AgentId, Point] = {}
        self._dest: dict[AgentId, Destination] = {}
        self._gone: set[AgentId] = set()
        self._closed: set[str] = set()

    def _target(self, destination: Destination) -> Point | None:
        if destination.kind == "exit" and destination.exit_id:
            return self._plan.exit(destination.exit_id).center
        if destination.kind == "point":
            return destination.point
        if destination.kind == "agent" and destination.agent_id:
            return self._pos.get(destination.agent_id)
        return None

    def add_agent(self, agent_id: AgentId, position: Point, destination: Destination) -> None:
        self._pos[agent_id] = position
        self._dest[agent_id] = destination

    def set_destination(self, agent_id: AgentId, destination: Destination) -> None:
        self._dest[agent_id] = destination

    def remove_agent(self, agent_id: AgentId) -> None:
        self._gone.add(agent_id)

    def step(self) -> None:
        for agent_id, position in list(self._pos.items()):
            if agent_id in self._gone:
                continue
            destination = self._dest.get(agent_id)
            target = self._target(destination) if destination else None
            if target is None:
                continue
            dx, dy = target[0] - position[0], target[1] - position[1]
            distance = math.hypot(dx, dy)
            if distance < 0.35:
                if destination and destination.kind == "exit":
                    self._gone.add(agent_id)
                continue
            ratio = min(1.0, self._speed / distance)
            self._pos[agent_id] = (position[0] + dx * ratio, position[1] + dy * ratio)

    def positions(self) -> dict[AgentId, Point]:
        return {a: p for a, p in self._pos.items() if a not in self._gone}

    def evacuated(self) -> set[AgentId]:
        return set(self._gone)

    def close_exit(self, exit_id: str) -> None:
        self._closed.add(exit_id)

    @property
    def agent_count(self) -> int:
        return len(self._pos) - len(self._gone)


class CountingLLM:
    """Ne doit jamais être appelé dans ce test."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, *, seed, **kwargs):
        self.calls += 1
        raise AssertionError("un agent à règles a appelé le LLM")

    async def embed(self, texts):
        raise AssertionError("aucun embedding attendu")


def _config(
    run_id: str, *, seed: int = 0, ticks: int = 40, population=None, **extra
) -> RunConfig:
    return RunConfig(
        run_id=run_id,
        seed=seed,
        max_ticks=ticks,
        smoke_tick=3,
        smoke_position=(44.0, 15.0),
        smoke_radius=15.0,
        close_exit=None,
        announcement_tick=6,
        announcement="Évacuation.",
        population=population
        or (
            PopulationEntry("visiteur", 3, "rules"),
            PopulationEntry("habitue", 2, "rules"),
            PopulationEntry("famille", 2, "rules"),
            PopulationEntry("vendeur", 1, "rules"),
        ),
        narrative_every=5,
        **extra,
    )


async def _run(tmp_path: Path, run_id: str, *, seed: int = 0, llm=None, **extra):
    plan = Plan.from_dict(
        __import__("yaml").safe_load(
            Path("configs/world/port_aubel.yaml").read_text("utf-8")
        )
    )
    journal = JsonlJournal(tmp_path)
    bus = InMemoryBus()
    llm = llm or CountingLLM()
    simulation = Simulation(
        config=_config(run_id, seed=seed, **extra),
        plan=plan,
        physics=FakePhysics(plan),
        llm=llm,
        retriever=None,
        memory=EventSourcedMemory(n_exits=len(plan.exits)),
        journal=journal,
        bus=bus,
        narrator=None,
    )
    result = await simulation.run()
    return result, journal, bus, llm


async def test_run_se_termine_et_journalise(tmp_path: Path) -> None:
    result, journal, bus, llm = await _run(tmp_path, "run_a")

    assert result.ticks >= 1
    assert result.indicators
    assert result.llm_calls == 0
    assert llm.calls == 0

    events = journal.read("run_a")
    types = [str(e.type) for e in events]
    assert "run.started" in types
    assert "run.ended" in types
    assert "metrics.indicators" in types
    assert [e.seq for e in events] == sorted(e.seq for e in events)
    # C1 — le bus porte les faits, pas l'état : tout est publié **sauf**
    # les instantanés (`world.snapshot`), qui se reconstruisent.
    published = {e.seq for _, e in bus.published}
    assert published == {e.seq for e in events if str(e.type) != "world.snapshot"}
    assert all(topic for topic, _ in bus.published)


async def test_tous_les_agents_finissent_par_sortir(tmp_path: Path) -> None:
    result, _, _, _ = await _run(tmp_path, "run_b")
    last = result.indicators[-1]
    assert last.i3_evacuated == pytest.approx(1.0)
    assert last.counts["remaining"] == 0


async def test_i7_relie_le_premier_signal_au_dernier_sorti(tmp_path: Path) -> None:
    """I7 est câblé dans la boucle, pas seulement dans `compute`.

    Le signal est la fumée de t3 ; le dernier sorti est le dernier
    `agent.evacuated`. Sans ce test, un câblage oublié laisserait I7 à 0
    dans tous les runs — ce qui ressemble à « personne n'est sorti ».
    """
    result, journal, _, _ = await _run(tmp_path, "run_i7")
    events = journal.read("run_i7")
    signal = min(e.t_prod for e in events if str(e.type) == "world.smoke")
    last = max(e.t_prod for e in events if str(e.type) == "agent.evacuated")
    final = result.indicators[-1].to_dict()
    assert final["I7_delay_seconds"] == pytest.approx((last - signal) * 10.0)
    assert final["I7_delay_seconds"] > 0


async def test_l_instantane_porte_la_cognition_pour_l_interface(tmp_path: Path) -> None:
    """Le client 2D doit dessiner la croyance, pas seulement des positions."""
    _, journal, _, _ = await _run(tmp_path, "run_snap")
    snaps = [e for e in journal.read("run_snap") if str(e.type) == "world.snapshot"]
    assert snaps
    first = snaps[0].data
    assert set(first) >= {
        "tick",
        "sim_time",
        "exits_open",
        "smoke_active",
        "density_grid",
        "agents",
    }
    assert first["smoke_active"] is False

    agent = first["agents"][0]
    assert set(agent) >= {
        "id",
        "profile",
        "label",
        "kind",
        "pos",
        "belief",
        "confidence",
        "beliefs",
        "entropy",
        "intention",
        "intention_target",
        "evacuated",
        "kin",
        "decided_at",
        "perceived",
    }
    assert agent["kind"] == "rules"
    assert agent["beliefs"], "la table complète, pas seulement l'argmax"
    assert isinstance(agent["perceived"], list)

    # Grille de densité prête à dessiner : origine en mètres + effectif.
    cells = first["density_grid"]
    assert cells and all({"x", "y", "n"} <= set(c) for c in cells)
    assert sum(c["n"] for c in cells) == len(first["agents"])


async def test_la_fumee_reste_visible_dans_les_instantanes(tmp_path: Path) -> None:
    """Un client qui se connecte après la fumée doit encore la voir."""
    _, journal, _, _ = await _run(tmp_path, "run_smoke")
    snaps = [
        e.data for e in journal.read("run_smoke") if str(e.type) == "world.snapshot"
    ]
    assert snaps[0]["smoke_active"] is False
    assert any(s["smoke_active"] for s in snaps[1:])


async def test_deux_runs_de_meme_graine_sont_identiques(tmp_path: Path) -> None:
    first, journal_a, _, _ = await _run(tmp_path, "run_c1", seed=7)
    second, journal_b, _, _ = await _run(tmp_path, "run_c2", seed=7)

    assert indicators_hash(journal_a.read("run_c1")) == indicators_hash(
        journal_b.read("run_c2")
    )
    assert [i.to_dict() for i in first.indicators] == [
        i.to_dict() for i in second.indicators
    ]


async def test_graines_differentes_changent_le_run(tmp_path: Path) -> None:
    first, _, _, _ = await _run(tmp_path, "run_d1", seed=1)
    second, _, _, _ = await _run(tmp_path, "run_d2", seed=2)
    assert [i.to_dict() for i in first.indicators] != [
        i.to_dict() for i in second.indicators
    ]


async def test_la_fumee_puis_lannonce_declenchent_des_decisions(tmp_path: Path) -> None:
    _, journal, _, _ = await _run(tmp_path, "run_e")
    decisions = [e for e in journal.read("run_e") if str(e.type) == "agent.decision"]
    assert len(decisions) >= 4  # au moins une par agent
    reasons = {e.data.get("trigger") for e in decisions}
    assert "fumee_visible" in reasons or "annonce" in reasons


class GuideLLM:
    """Un agent de sécurité qui « guide » : son métier, sans danger."""

    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, messages, *, seed: int, **kwargs) -> LLMResult:
        self.calls += 1
        return LLMResult(
            text='{"action": "guide", "target": "A", "confidence": 0.9}',
            prompt="…",
            seed=seed,
            model="factice",
            ok=True,
        )

    async def embed(self, texts):
        return []


async def test_un_guide_sans_danger_ne_diffuse_pas_d_alerte(tmp_path: Path) -> None:
    """Un guide qui n'a rien vu ne doit pas faire évacuer ses voisins.

    Constaté en hybride : au tick 1, deux agents de sécurité choisissaient
    `guide` (leur rôle), `_diffuse` transformait cela en « il faut sortir
    par… », et comme tout message reçu vaut signal de danger, la foule
    sortait avant la fumée de t10 (6 à 12 sorties à t9).
    """
    plan = Plan.from_dict(
        __import__("yaml").safe_load(
            Path("configs/world/port_aubel.yaml").read_text("utf-8")
        )
    )
    config = RunConfig(
        run_id="run_guide",
        seed=0,
        max_ticks=10,
        smoke_tick=10,
        smoke_position=(44.0, 15.0),
        smoke_radius=15.0,
        close_exit=None,
        announcement_tick=None,
        announcement=None,
        population=(PopulationEntry("securite", 2, "llm"),),
        narrative_every=5,
    )
    journal = JsonlJournal(tmp_path)
    simulation = Simulation(
        config=config,
        plan=plan,
        physics=FakePhysics(plan),
        llm=GuideLLM(),
        retriever=None,
        memory=EventSourcedMemory(n_exits=len(plan.exits)),
        journal=journal,
        bus=InMemoryBus(),
        narrator=None,
    )
    result = await simulation.run()
    assert result.llm_ok > 0, "les agents LLM n'ont pas décidé"

    events = journal.read("run_guide")
    avant = [
        e for e in events if str(e.type) == "agent.message.sent" and e.t_prod < 10
    ]
    assert not avant, "un guide a diffusé une alerte avant la fumée"
    sorties = [e for e in events if str(e.type) == "agent.evacuated" and e.t_prod < 10]
    assert not sorties, "des agents sont sortis avant la fumée"


async def test_b4_une_decision_declenchee_par_la_fumee_a_une_cause(tmp_path: Path) -> None:
    """B4 — `causation_id` pointe l'événement qui a réellement déclenché.

    Le journal portait 0 / 1 181 `causation_id` : `Event.child()` existait
    mais n'était jamais appelé. Sans ce lien, « montrez les échanges qui
    ont précédé le basculement » n'a pas de réponse calculable.
    """
    _, journal, _, _ = await _run(tmp_path, "run_b4")
    events = journal.read("run_b4")
    by_id = {e.id: e for e in events}
    smoke = next(e for e in events if str(e.type) == "world.smoke")
    caused = [
        e
        for e in events
        if str(e.type) == "agent.decision" and e.data.get("trigger") == "fumee_visible"
    ]
    assert caused, "aucune décision déclenchée par la fumée"
    for decision in caused:
        assert decision.causation_id == smoke.id
        assert decision.correlation_id == smoke.id
        assert by_id[decision.causation_id].type is smoke.type
    # Une décision périodique n'a pas de parent inventé.
    periodic = [
        e for e in events if str(e.type) == "agent.decision" and e.data.get("trigger") == "periodique"
    ]
    assert periodic
    assert all(e.causation_id is None for e in periodic)


# ------------------------------------------------------------
# Vague 2 : ce que le monde fait, et ce qu'il refuse de faire
# ------------------------------------------------------------
async def test_sans_communication_aucun_message(tmp_path: Path) -> None:
    """A2/B3 — le bras « sans communication » ne diffuse rien du tout.

    Ce n'est pas un détail d'implémentation : c'est le contrôle négatif
    qui dit si I1 mesure une émergence sociale ou la ressemblance des
    réponses d'un même modèle. S'il restait un seul message, le bras
    serait un faux témoin.
    """
    _, journal_on, _, _ = await _run(tmp_path, "avec", communication=True)
    _, journal_off, _, _ = await _run(tmp_path, "sans", communication=False)
    sent_on = [e for e in journal_on.read("avec") if str(e.type) == "agent.message.sent"]
    sent_off = [e for e in journal_off.read("sans") if str(e.type) == "agent.message.sent"]
    heard_off = [e for e in journal_off.read("sans") if str(e.type) == "agent.message.heard"]
    assert sent_on, "le bras avec communication doit produire des messages"
    assert sent_off == []
    assert heard_off == []


async def test_prehistoire_est_un_echange_date_et_journalise(tmp_path: Path) -> None:
    """A1 — « un échange vieux de plusieurs jours simulés ».

    Trois choses à prouver, et pas une de moins :

      1. c'est un **échange** : un émetteur, un destinataire, un contenu ;
      2. c'est **vieux** : le tick est négatif (J-3 = -25 920), pas antidaté ;
      3. c'est **journalisé** : le rejeu peut donc dire ce que l'agent
         savait avant t0, sans rappeler un modèle.
    """
    result, journal, _, _ = await _run(
        tmp_path,
        "pre",
        llm=GuideLLM(),
        prehistory_days=3,
        population=(
            PopulationEntry("securite", 1, "llm"),
            PopulationEntry("visiteur", 1, "llm"),
            PopulationEntry("habitue", 1, "rules"),
        ),
    )
    events = journal.read("pre")
    seeded = [e for e in events if str(e.type) == "memory.seeded"]
    assert len(seeded) == 1
    assert seeded[0].data["days"] == 3
    assert seeded[0].data["episodes"] > 0

    # 1 et 2 — un vrai message, daté d'avant t0, avec sa cause.
    ancient_messages = [
        e
        for e in events
        if str(e.type) == "agent.message.sent" and e.t_prod < 0
    ]
    assert ancient_messages
    heard = [e for e in events if str(e.type) == "agent.message.heard" and e.t_prod < 0]
    assert heard
    assert all(h.causation_id == ancient_messages[0].id for h in heard)

    # 3 — le destinataire s'en souvient, et il sait qui lui a parlé.
    first_snapshot = next(e for e in events if str(e.type) == "world.snapshot")
    memories = [
        episode
        for agent in first_snapshot.data["agents"]
        for episode in agent.get("memory", [])
    ]
    ancient = [m for m in memories if m["tick"] < 0]
    assert ancient, "la préhistoire doit apparaître dans la mémoire des agents"
    assert all(m["source"] == "prehistoire" for m in ancient)
    assert any("m'a dit" in m["content"] for m in ancient)
    assert result.ticks >= 1


async def test_indicateurs_portent_leur_plage_de_seq(tmp_path: Path) -> None:
    """F6 — chaque bloc d'indicateurs sait d'où il vient."""
    _, journal, _, _ = await _run(tmp_path, "src")
    blocks = [e for e in journal.read("src") if str(e.type) == "metrics.indicators"]
    assert blocks
    for block in blocks:
        sources = block.data["sources"]
        assert 1 <= sources["from_seq"] <= sources["to_seq"]
        assert sources["count"] == sources["to_seq"] - sources["from_seq"] + 1


async def test_snapshot_explique_la_derniere_decision(tmp_path: Path) -> None:
    """D2 — l'interface n'a pas à recoller trois événements pour expliquer."""
    _, journal, _, _ = await _run(tmp_path, "d2")
    snapshots = [e for e in journal.read("d2") if str(e.type) == "world.snapshot"]
    explained = [
        agent["last_decision"]
        for snapshot in snapshots
        for agent in snapshot.data["agents"]
        if agent.get("last_decision")
    ]
    assert explained
    decision = explained[0]
    for key in ("tick", "kind", "trigger", "reason", "intention"):
        assert key in decision
    # Un agent à règles expose la règle, pas un raisonnement inventé.
    assert decision["rule"]


async def test_injection_est_appliquee_au_tick_suivant(tmp_path: Path) -> None:
    """D3 — une commande déposée avant le run est perçue au tick 1, pas à 0.

    L'injection est journalisée **avant** l'événement qu'elle provoque :
    c'est ce qui rend la chaîne causale lisible dans le rejeu.
    """
    plan = Plan.from_dict(
        __import__("yaml").safe_load(
            Path("configs/world/port_aubel.yaml").read_text("utf-8")
        )
    )
    journal = JsonlJournal(tmp_path)
    simulation = Simulation(
        config=_config("d3"),
        plan=plan,
        physics=FakePhysics(plan),
        llm=CountingLLM(),
        retriever=None,
        memory=EventSourcedMemory(n_exits=len(plan.exits)),
        journal=journal,
        bus=InMemoryBus(),
        narrator=None,
    )
    simulation.submit({"kind": "announcement", "text": "Sortez par C"})
    await simulation.run()

    events = journal.read("d3")
    injections = [e for e in events if str(e.type) == "control.injection"]
    assert len(injections) == 1
    assert injections[0].t_prod == 1
    announcements = [e for e in events if str(e.type) == "world.announcement"]
    assert any(a.causation_id == injections[0].id for a in announcements)
    assert announcements[0].data["text"] == "Sortez par C"


async def test_une_injection_inconnue_est_isolee(tmp_path: Path) -> None:
    """D3 + F4 — une commande inconnue ne tue pas le monde, elle est isolée."""
    plan = Plan.from_dict(
        __import__("yaml").safe_load(
            Path("configs/world/port_aubel.yaml").read_text("utf-8")
        )
    )
    journal = JsonlJournal(tmp_path)
    simulation = Simulation(
        config=_config("d3bad"),
        plan=plan,
        physics=FakePhysics(plan),
        llm=CountingLLM(),
        retriever=None,
        memory=EventSourcedMemory(n_exits=len(plan.exits)),
        journal=journal,
        bus=InMemoryBus(),
        narrator=None,
    )
    simulation.submit({"kind": "nuke"})
    result = await simulation.run()

    assert result.quarantined >= 1
    assert journal.quarantine_path("d3bad").exists()
    events = journal.read("d3bad")
    assert any(str(e.type) == "dlq.invalid" for e in events)
    # Le run va jusqu'au bout : une commande folle n'arrête pas l'évacuation.
    assert result.indicators


async def test_aucune_violation_temporelle(tmp_path: Path) -> None:
    """C6 — le monde est causal : rien ne cite une information future."""
    result, journal, _, _ = await _run(tmp_path, "c6")
    assert result.temporal_violations == 0
    assert not [e for e in journal.read("c6") if str(e.type) == "temporal.violation"]


class ScriptedLLM:
    """Un modèle qui répond ce qu'on lui dit de répondre — A4."""

    def __init__(self, text: str = "", *, ok: bool = True, error: str | None = None):
        self.text = text
        self.ok = ok
        self.error = error
        self.calls = 0

    async def chat(self, messages, *, seed: int, **kwargs) -> LLMResult:
        self.calls += 1
        return LLMResult(
            text=self.text if self.ok else "",
            prompt="…",
            seed=seed,
            model="factice",
            ok=self.ok,
            error=self.error,
        )

    async def embed(self, texts):
        return []


async def _incidents(journal, run_id: str):
    return [e for e in journal.read(run_id) if str(e.type) == "agent.incident"]


async def test_un_modele_qui_divague_est_trace_et_le_run_continue(
    tmp_path: Path,
) -> None:
    """A4 — une réponse inexploitable n'arrête rien, et laisse une trace."""
    result, journal, _, llm = await _run(
        tmp_path,
        "a4g",
        llm=ScriptedLLM("je ne sais pas, je regarde le ciel"),
        population=(
            PopulationEntry("visiteur", 2, "llm"),
            PopulationEntry("habitue", 3, "rules"),
        ),
    )
    assert llm.calls > 0
    incidents = await _incidents(journal, "a4g")
    assert incidents, "un repli silencieux n'est pas un incident tracé"
    assert {i.data["kind"] for i in incidents} == {"unparseable"}
    assert all(i.data["agent_id"].startswith("A") for i in incidents)
    assert result.incidents == len(incidents)
    assert result.incident_kinds == {"unparseable": len(incidents)}
    # Le monde continue : l'évacuation a bien lieu, par les règles.
    assert result.indicators
    assert result.indicators[-1].counts["evacuated"] > 0


async def test_un_modele_qui_invente_une_sortie_est_un_incident(
    tmp_path: Path,
) -> None:
    """A4 — « Z » n'existe pas : c'est une dérive, pas un silence."""
    result, journal, _, _ = await _run(
        tmp_path,
        "a4z",
        llm=ScriptedLLM('{"action": "go_exit", "target": "Z", "confidence": 0.8}'),
        population=(
            PopulationEntry("visiteur", 2, "llm"),
            PopulationEntry("habitue", 2, "rules"),
        ),
    )
    incidents = await _incidents(journal, "a4z")
    assert {i.data["kind"] for i in incidents} == {"unknown_exit"}
    assert result.incident_kinds == {"unknown_exit": len(incidents)}


async def test_un_modele_hors_de_son_role_est_un_incident_distinct(
    tmp_path: Path,
) -> None:
    """A4 — un visiteur qui nomme B sort de son rôle, il ne se trompe pas de mot.

    La distinction compte : `unknown_exit` accuse le modèle, `out_of_role`
    accuse le prompt (le profil ne connaît que A). Les deux se corrigent
    différemment, donc ils ne partagent pas le même compteur.
    """
    result, journal, _, _ = await _run(
        tmp_path,
        "a4r",
        llm=ScriptedLLM('{"action": "go_exit", "target": "B", "confidence": 0.8}'),
        population=(
            PopulationEntry("visiteur", 2, "llm"),
            PopulationEntry("habitue", 2, "rules"),
        ),
    )
    incidents = await _incidents(journal, "a4r")
    assert {i.data["kind"] for i in incidents} == {"out_of_role"}
    assert result.incident_kinds == {"out_of_role": len(incidents)}


async def test_un_modele_muet_n_est_pas_un_modele_qui_divague(
    tmp_path: Path,
) -> None:
    """A4 — pas de réponse et réponse inexploitable sont deux incidents."""
    result, journal, _, _ = await _run(
        tmp_path,
        "a4m",
        llm=ScriptedLLM("", ok=False, error="TimeoutError: 120s"),
        population=(
            PopulationEntry("visiteur", 2, "llm"),
            PopulationEntry("habitue", 2, "rules"),
        ),
    )
    incidents = await _incidents(journal, "a4m")
    assert {i.data["kind"] for i in incidents} == {"no_response"}
    assert result.llm_ok == 0
    assert result.incident_kinds == {"no_response": len(incidents)}
    assert all("TimeoutError" in i.data["detail"] for i in incidents)
    assert result.indicators, "un serveur muet ne tue pas le run"


class SlowLLM:
    """Un modèle qui met du temps — C4 : la latence est réelle, pas inventée."""

    def __init__(self, delay: float = 0.2, text: str | None = None) -> None:
        self.delay = delay
        self.text = text or '{"action": "go_exit", "target": "A", "confidence": 0.8}'
        self.calls = 0

    async def chat(self, messages, *, seed: int, **kwargs) -> LLMResult:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return LLMResult(
            text=self.text, prompt="…", seed=seed, model="lent", ok=True
        )

    async def embed(self, texts):
        return []


async def test_c3_un_message_publie_a_t_est_lu_a_t_plus_n(tmp_path: Path) -> None:
    """C3 — le moment de production et celui du traitement sont distincts.

    Sans cette distinction, `t_prod` et `t_trait` seraient le même champ
    recopié deux fois : le journal ne pourrait pas dire qu'un message a
    dormi deux ticks avant d'être lu.
    """
    _, journal, _, _ = await _run(
        tmp_path,
        "c3",
        llm=SlowLLM(delay=0.0),
        message_delay_ticks=2,
        population=(
            PopulationEntry("securite", 1, "llm"),
            PopulationEntry("visiteur", 2, "llm"),
            PopulationEntry("habitue", 4, "rules"),
        ),
    )
    events = journal.read("c3")
    heard = [e for e in events if str(e.type) == "agent.message.heard"]
    assert heard, "aucun message livré : le test ne prouve rien"
    assert all(e.t_trait - e.t_prod == 2 for e in heard), [
        (e.t_prod, e.t_trait) for e in heard
    ]
    sent = {e.id: e for e in events if str(e.type) == "agent.message.sent"}
    for event in heard:
        assert event.causation_id in sent
        assert sent[event.causation_id].t_prod == event.t_prod
    # En mode synchrone, les décisions n'ont aucun décalage.
    decisions = [e for e in events if str(e.type) == "agent.decision"]
    assert all(e.t_prod == e.t_trait for e in decisions)


async def test_c4_asynchrone_applique_la_decision_quand_elle_arrive(
    tmp_path: Path,
) -> None:
    """C4 — en asynchrone, la décision porte la latence réelle du modèle."""
    result, journal, _, _llm = await _run(
        tmp_path,
        "c4a",
        llm=SlowLLM(delay=0.25),
        mode="async",
        tick_delay_s=0.05,
        population=(
            PopulationEntry("visiteur", 3, "llm"),
            PopulationEntry("habitue", 3, "rules"),
        ),
    )
    assert result.mode == "async"
    events = journal.read("c4a")
    decisions = [e for e in events if str(e.type) == "agent.decision"]
    assert decisions
    lagged = [e for e in decisions if e.t_trait > e.t_prod]
    assert lagged, "aucune décision décalée : le mode asynchrone n'en est pas un"
    assert all(e.data["lag_ticks"] == e.t_trait - e.t_prod for e in lagged)
    # La latence observée colle à la latence réelle du faux modèle.
    assert max(e.data["lag_ticks"] for e in lagged) >= 2


async def test_c4_asynchrone_ne_bloque_pas_le_monde(tmp_path: Path) -> None:
    """C4 — un modèle lent ne fige pas la physique ni les indicateurs."""
    result, journal, _, _ = await _run(
        tmp_path,
        "c4b",
        llm=SlowLLM(delay=0.3),
        mode="async",
        tick_delay_s=0.02,
        ticks=30,
        population=(
            PopulationEntry("visiteur", 2, "llm"),
            PopulationEntry("habitue", 4, "rules"),
        ),
    )
    blocks = [e for e in journal.read("c4b") if str(e.type) == "metrics.indicators"]
    # Le monde avance à chaque tick, indépendamment des réponses en vol.
    assert len(blocks) >= 10
    assert result.indicators[-1].counts["evacuated"] > 0


async def test_c6_asynchrone_ne_cree_pas_de_violation_fantome(
    tmp_path: Path,
) -> None:
    """C6 × C4 — une décision appliquée en retard ne cite pas un futur.

    Régression réelle : `_check_temporal` comparait l'état **courant** du
    monde au lieu de l'état **perçu**. En synchrone, les deux coïncident
    donc le bug restait invisible ; en asynchrone, une décision de t1
    appliquée à t12 voyait la fumée de t10 et se déclarait en violation.
    Mesuré sur `c4_async_01` : 12 violations fantômes.
    """
    result, journal, _, _ = await _run(
        tmp_path,
        "c6a",
        llm=SlowLLM(delay=0.15),
        mode="async",
        tick_delay_s=0.02,
        ticks=30,
        population=(
            PopulationEntry("visiteur", 3, "llm"),
            PopulationEntry("habitue", 3, "rules"),
        ),
    )
    assert result.temporal_violations == 0
    assert not [
        e for e in journal.read("c6a") if str(e.type) == "temporal.violation"
    ]
