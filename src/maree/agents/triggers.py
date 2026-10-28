"""Déclencheurs de décision — la réponse au problème des 60 agents.

En v1, chaque agent décidait à chaque tick : 60 agents × 36 ticks = 2160
appels LLM par run, pour un débit de 0,36 appel/s. Impossible.

Or une foule ne réfléchit pas en permanence. On décide quand quelque
chose **change** :

    la fumée devient visible      -> réévaluer
    un message arrive             -> réévaluer
    la sortie crue est fermée     -> réévaluer (le piège se referme)
    la densité devient critique   -> réévaluer
    sinon                         -> garder son intention

Mesuré sur le scénario de référence : ~40 à 60 décisions par run au lieu
de 2160, soit une charge moyenne de 0,15 décision/s — largement dans la
capacité du routeur (1,43 décision/s avec 4 slots).

Le déclencheur périodique reste présent comme filet : une intention ne
peut pas être conservée indéfiniment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from maree.domain.ids import AgentId, ExitId, Point, Tick, ZoneId


@dataclass(frozen=True, slots=True)
class Message:
    sender: AgentId
    content: str
    tick: Tick
    claim: str | None = None  # "sortie A bloquee" | "fumee" | None


@dataclass(frozen=True, slots=True)
class Percept:
    """Perception figée à l'instant T (décision 10)."""

    tick: Tick
    position: Point
    zone: ZoneId | None
    smoke_visible: bool = False
    smoke_intensity: float = 0.0
    density: float = 0.0
    exits_open: frozenset[ExitId] = frozenset()
    #: Densité locale DEVANT chaque sortie (pers/m²). Sans cela, la
    #: pénalité de densité serait la même pour toutes les sorties et ne
    #: changerait jamais le choix — un terme décoratif.
    exit_density: dict[ExitId, float] = field(default_factory=dict)
    messages: tuple[Message, ...] = ()
    nearby: tuple[AgentId, ...] = ()
    announcement: str | None = None
    missing_kin: bool = False


@dataclass(frozen=True, slots=True)
class DecisionTrigger:
    needed: bool
    reason: str
    urgency: float = 0.0

    def __bool__(self) -> bool:
        return self.needed


#: Au-delà, on force une réévaluation même sans nouveauté.
DEFAULT_MAX_IDLE = 6

_DENSITY_ALERT = 3.0  # pers/m²


def should_decide(
    percept: Percept,
    *,
    last_decision_tick: Tick | None,
    current_exit: ExitId | None,
    known_messages: frozenset[str] = frozenset(),
    max_idle: int = DEFAULT_MAX_IDLE,
    cadence_ticks: int = 3,
) -> DecisionTrigger:
    """Décide s'il faut (re)consulter le LLM, et pourquoi.

    L'ordre des tests est l'ordre des priorités : le danger d'abord.
    """
    # 1. La sortie qu'il croyait sûre n'existe plus.
    if current_exit is not None and current_exit not in percept.exits_open:
        return DecisionTrigger(True, "sortie_fermee", 1.0)

    # 2. Danger perçu directement.
    if percept.smoke_visible and percept.smoke_intensity > 0.05:
        return DecisionTrigger(True, "fumee_visible", 0.9)

    # 3. Annonce officielle.
    if percept.announcement:
        return DecisionTrigger(True, "annonce", 0.85)

    # 4. Information nouvelle d'un voisin.
    for msg in percept.messages:
        key = f"{msg.sender}:{msg.tick}"
        if key not in known_messages:
            return DecisionTrigger(True, f"message:{msg.sender}", 0.7)

    # 5. Proche disparu (profil famille).
    if percept.missing_kin:
        return DecisionTrigger(True, "proche_disparu", 0.75)

    # 6. Embouteillage.
    if percept.density >= _DENSITY_ALERT:
        return DecisionTrigger(True, "densite_critique", 0.6)

    # 7. Filet périodique.
    if last_decision_tick is None:
        return DecisionTrigger(True, "premiere_decision", 0.5)
    idle = percept.tick - last_decision_tick
    if idle >= max(max_idle, cadence_ticks):
        return DecisionTrigger(True, "periodique", 0.2)

    return DecisionTrigger(False, "rien_de_nouveau", 0.0)
