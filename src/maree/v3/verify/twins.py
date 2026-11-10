"""verify.twins — l'expérience des jumeaux (mission 1, semaine 3).

Protocole (comportement.md §9) : deux cohortes de jumeaux — **mêmes traits,
même archétype, mêmes sorties connues**, même scénario public — mais des
**histoires personnelles différentes** (messages reçus). On mesure jusqu'où
ils divergent *à cause de leur mémoire*, et on prouve par **ablation**
(mémoire off) que sans elle la divergence s'évanouit.

Aucune physique ici : le monde est une *ligne du temps* de signaux publics
(fumée, annonces) qui pilote ``Agent.react``. Le mouvement n'arrivera
qu'avec le moteur (semaine 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from maree.v3.agents.agent import Agent, make_agent
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.state import State
from maree.v3.core.ids import ZoneId
from maree.v3.verify.metrics import divergence_report


@dataclass(frozen=True, slots=True)
class PublicEvent:
    """Un instant du monde perçu par tous (perception figée partagée)."""

    tick: int
    smoke: bool = False
    announcement: str | None = None


@dataclass(slots=True)
class TwinHistory:
    """L'histoire personnelle d'une branche de jumeau : des messages reçus."""

    name: str = "histoire"
    messages: list[tuple[int, Message]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _PairRun:
    index: int
    left_agent: Agent
    right_agent: Agent


def _perception(tick: int, *, smoke: bool = False, announcement: str | None = None,
                heard: tuple[Message, ...] = ()) -> Perception:
    return Perception(
        tick=tick,
        zone=ZoneId("scenario"),
        state=State(),
        smoke_visible=smoke,
        announcement=announcement,
        heard=heard,
        seen_agents=(),
        exits_visible=frozenset(),
    )


def _feed_history(agent: Agent, history: TwinHistory) -> None:
    for tick, msg in sorted(history.messages, key=lambda m: m[0]):
        agent.react(_perception(tick, heard=(msg,)))


def _first_movement(agent: Agent) -> tuple[str | None, int | None]:
    """Retourne (sortie_choisie, tick_premier_mouvement) de l'agent.

    ``sortie_choisie`` = cible du premier ``EVACUER`` ; ``tick_premier`` =
    premier tick d'une action de mouvement (non RESTER/CHERCHER).
    À défaut : (None, None).
    """
    chosen: str | None = None
    first_tick: int | None = None
    for e in agent.memory.episodes:
        if e.kind.value != "decide":
            continue
        if first_tick is None:
            first_tick = e.tick
        if chosen is None and "évacuer" in e.content:
            # content = "<action.value> -> <target>"
            target = e.content.split("->", 1)[1].strip() if "->" in e.content else None
            chosen = target or None
    return chosen, first_tick


def run_twins_experiment(
    *,
    timeline: tuple[PublicEvent, ...],
    left_history: TwinHistory,
    right_history: TwinHistory,
    archetype: str = "visiteur",
    known_exits: frozenset[str] = frozenset({"A", "B", "C"}),
    n_pairs: int = 5,
    memory_on: bool = True,
) -> dict[str, object]:
    """Déroule l'expérience des jumeaux et en rend le rapport de divergence.

    ``memory_on=False`` = ablation : on n'injecte pas les histoires
    personnelles ⇒ les deux branches reçoivent exactement le même scénario
    public ⇒ divergence attendue nulle.
    """
    categories = tuple(sorted(known_exits))
    left_exits: list[str | None] = []
    right_exits: list[str | None] = []
    left_moves: list[int | None] = []
    right_moves: list[int | None] = []

    for i in range(n_pairs):
        left = make_agent(uid=100 + i, archetype=archetype, known_exits=known_exits)
        right = make_agent(uid=200 + i, archetype=archetype, known_exits=known_exits)
        if memory_on:
            _feed_history(left, left_history)
            _feed_history(right, right_history)
        else:
            _feed_history(left, TwinHistory("vide"))
            _feed_history(right, TwinHistory("vide"))

        for ev in timeline:
            p = _perception(ev.tick, smoke=ev.smoke, announcement=ev.announcement)
            left.react(p)
            right.react(p)

        lexit, lmov = _first_movement(left)
        rexit, rmov = _first_movement(right)
        left_exits.append(lexit)
        right_exits.append(rexit)
        left_moves.append(lmov)
        right_moves.append(rmov)

    return divergence_report(
        left_exits,
        right_exits,
        categories,
        left_first_moves=left_moves,
        right_first_moves=right_moves,
    )


#: Un scénario de référence : fumée à t=10, une annonce d'évacuation à t=5.
REFERENCE_TIMELINE: tuple[PublicEvent, ...] = (
    PublicEvent(1),
    PublicEvent(5, announcement="Veuillez évacuer immédiatement par la sortie A"),
    PublicEvent(10, smoke=True),
    PublicEvent(20, smoke=True),
)


__all__ = ["REFERENCE_TIMELINE", "PublicEvent", "TwinHistory", "run_twins_experiment"]