"""verify.scenario_crowd — la mesure macro : la même croyance, avec une foule.

Le banc ``scenario_blocked`` mesure quatre agents sur un monde fixe, sans
physique : il isole la *lecture* d'une croyance. Ce module-ci mesure ce que la
croyance devient quand un corps la suit : soixante agents dans une salle
calibrée (``crowd_hall``, 22 × 16 m, deux issues de 1,2 m), JuPedSim aux
commandes, et les indicateurs I1–I7 calculés pendant le run.

Calibration (C5, 2026-11-18) — mesurée, pas choisie (3 graines) :

========================  ===================
surface                   22 × 16 m (352 m²)
agents                    60 (0,17 pers/m²)
issues                    2 × 1,2 m
I5 pic (noyau 2 m)        1,27–1,43 pers/m²
vidage (règles)           24–26 s
pic de densité            t6–t7 (en marche)
========================  ===================

Deux conséquences assumées :

- ``hall_3`` (120 × 80 m, 9 600 m²) ne fait **aucun** goulot à 60 agents
  (densité mesurée 0,000 pers/m²) : un monde qui ne contraint pas ne mesure
  pas l'évacuation, il mesure la marche ;
- le tick de ce scénario vaut **2 s** (et non 10 s) : la salle se vide en
  ~25 s, donc un tick de 10 s ne donnerait que deux points de mesure. La durée
  du tick est un paramètre du run, et I4/I7 la suivent ;
- la porte laisse passer plus que le débit empirique (≈3,2 pers/(m·s) contre
  1,3 dans la littérature, mesuré sur ce modèle sans compression de corps).
  Ce n'est pas corrigé par un réglage caché : c'est consigné, et l'écart est
  du même ordre sur les trois bras, donc les comparaisons tiennent.
"""

from __future__ import annotations

from typing import cast

import numpy as np

from maree.v3.adapters.physics import JuPedSimCrowd
from maree.v3.agents.perception import Message
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import EventBus, MemoryBus
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.verify.indicators import summarise
from maree.v3.world.generate import build
from maree.v3.world.navgraph import NavigationGraph
from maree.v3.world.simartifact import build_sim_artifact
from maree.v3.world.worldspec import WorldSpec

#: durée d'un tick de ce scénario (s) : la salle se vide en ~20 s.
TICK_SECONDS = 2.0
#: pas de physique par tick (dt = 0,05 s ⇒ 2 s de temps simulé).
STEPS_PER_TICK = 40
#: taille de la population et sorties connues par les agents.
N_AGENTS = 60
EXITS = ("A", "B")
#: instant de la fumée (premier danger) et plafond du run.
#: 30 ticks = 60 s : mesuré nécessaire pour que le scénario `contradiction`
#: ne soit pas **censuré** (à 20 ticks, certains bras finissaient à 55/60 et
#: I4 se figeait au plafond — un zéro qui ne mesurait que la durée du run).
T_SMOKE = 1
MAX_TICKS = 30


def world() -> WorldSpec:
    """Le monde calibré (22 × 16 m, deux issues de 1,2 m)."""
    return build("crowd_hall")


def _physics(w: WorldSpec, seed: int) -> JuPedSimCrowd:
    graph = NavigationGraph(w)
    art = build_sim_artifact(w, graph, np.random.default_rng(seed), spawn_per_space=6)
    level = art.levels["L0"]
    exits = {e.id: e.segment for e in w.level("L0").exits}
    return JuPedSimCrowd(walkable=level.walkable, exits=exits, seed=seed)


def timeline(max_ticks: int = MAX_TICKS) -> list[Timestep]:
    """Fumée à t1, puis des ticks vides : le monde continue, l'horloge tourne."""
    return [
        Timestep(T_SMOKE, smoke=True, hazard_origin=(11.0, 8.0)),
        *[Timestep(t) for t in range(T_SMOKE + 1, max_ticks + 1)],
    ]


def split_timeline(seed: int = 0) -> list[Timestep]:
    """La version macro du scénario bloqué (C6).

    À t1, la moitié de la foule apprend « A est bloquée », l'autre moitié
    « B est bloquée » — les deux portes restent **physiquement ouvertes**. La
    bonne réponse est de contourner ce que l'on croit fermé ; une décision qui
    vise la porte crue bloquée est le coût mesuré.
    """
    rng = np.random.default_rng(seed)
    order = rng.permutation(N_AGENTS)
    messages: list[tuple[int, Message]] = []
    for k, agent_index in enumerate(order):
        label = "A" if k < N_AGENTS // 2 else "B"
        messages.append(
            (
                int(agent_index) + 1,
                Message(f"La sortie {label} est bloquée", AgentId(999), 1, 0.8),
            )
        )
    return [
        Timestep(1, smoke=True, hazard_origin=(11.0, 8.0), messages=tuple(messages)),
        *[Timestep(t) for t in range(2, MAX_TICKS + 1)],
    ]


def contradiction_timeline(seed: int = 0) -> list[Timestep]:
    """L'annonce officielle contredit une croyance personnelle.

    À t1 : la moitié croit « A bloquée », l'autre « B bloquée », et l'annonce
    nomme **A**. La moitié qui croit A bloquée reçoit donc une consigne qui
    contredit ce qu'elle tient pour vrai : c'est le cas
    ``information_contradictoire`` de ``schedule.escalation_cause``, et le
    seul où un modèle peut faire autre chose qu'appliquer une consigne.
    """
    rng = np.random.default_rng(seed)
    order = rng.permutation(N_AGENTS)
    messages: list[tuple[int, Message]] = []
    for k, agent_index in enumerate(order):
        label = "A" if k < N_AGENTS // 2 else "B"
        messages.append(
            (
                int(agent_index) + 1,
                Message(f"La sortie {label} est bloquée", AgentId(999), 1, 0.8),
            )
        )
    return [
        Timestep(1, smoke=True, hazard_origin=(11.0, 8.0), messages=tuple(messages)),
        Timestep(2, announcement="Veuillez évacuer par la sortie A"),
        *[Timestep(t) for t in range(3, MAX_TICKS + 1)],
    ]


def build_sim(
    policy: PolicyName = PolicyName.RULES,
    *,
    seed: int = 1,
    bus: EventBus | None = None,
    alias: str | None = None,
    agents: int = N_AGENTS,
    physics: bool = True,
) -> Simulation:
    """Monte la salle calibrée, la foule et (éventuellement) JuPedSim."""
    w = world()
    crowd = _physics(w, seed) if physics else None
    sim = Simulation(
        seed=seed,
        policy=policy,
        bus=bus or MemoryBus(),
        run_id=f"crowd_{policy.value}_s{seed}",
        physics=crowd,
        physics_steps_per_tick=STEPS_PER_TICK,
        tick_seconds=TICK_SECONDS,
    ).build(w)
    sim.spawn("visiteur", agents, frozenset(EXITS), llm_alias=alias)
    return sim


def measure(
    policy: PolicyName = PolicyName.RULES,
    *,
    seed: int = 1,
    alias: str | None = None,
    split: bool = False,
    scenario: str = "plain",
    agents: int = N_AGENTS,
    physics: bool = True,
) -> dict[str, object]:
    """Joue le scénario et résume ce qu'il faut pour la porte G2.

    Rendus : les I1–I7 résumés (``summarise`` : pic pour I5/I6, partie active
    pour I1/I2, dernier tick pour I3/I4/I7), le pic par tick, l'instant du
    pic, et le nombre de sortis.
    """
    bus = MemoryBus()
    sim = build_sim(policy, seed=seed, bus=bus, alias=alias, agents=agents,
                    physics=physics)
    if scenario == "split" or (split and scenario == "plain"):
        steps = split_timeline(seed)
    elif scenario == "contradiction":
        steps = contradiction_timeline(seed)
    else:
        steps = timeline()
    sim.run(steps)
    series: list[dict[str, object]] = [
        dict(env.data) for env in bus.published("indicator.crowd")
    ]
    summary = summarise(series)
    peaks = [
        float(cast("float", d.get("I5_max_density") or 0.0)) for d in series
    ]
    peak_tick = int(np.argmax(peaks)) if peaks else 0
    evacuated = sum(1 for _ in sim._evacuated)
    return {
        "policy": policy.value,
        "seed": seed,
        "split": split,
        "scenario": scenario,
        "n_agents": agents,
        "summary": summary,
        "peak_tick": peak_tick,
        "peak_at_spawn": peak_tick == 0,
        "evacuated": evacuated,
        "decisions": len(sim.log.rows),
        "series": [
            {
                "tick": d.get("tick"),
                "I3": d.get("I3_evacuated"),
                "I5": d.get("I5_max_density"),
                "I7": d.get("I7_delay_seconds"),
            }
            for d in series
        ],
    }


def summarise_series(series: list[dict[str, object]]) -> dict[str, float]:
    """I1–I7 résumés d'une série de trames ``indicator.crowd``."""
    return summarise(series)


__all__ = [
    "EXITS",
    "MAX_TICKS",
    "N_AGENTS",
    "STEPS_PER_TICK",
    "TICK_SECONDS",
    "T_SMOKE",
    "build_sim",
    "contradiction_timeline",
    "measure",
    "split_timeline",
    "summarise_series",
    "timeline",
    "world",
]
