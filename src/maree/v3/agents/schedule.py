"""agents.schedule — quand un agent reconsidère, et quand le modèle parle.

ADR-014 : le calendrier est un **fait du monde**, pas une horloge. Ce module
sort la décision de ``Agent.react`` et la répartit par bras :

- ``regles`` : uniquement les **fronts** (fumée, annonce, message, fermeture,
  proche) ;
- ``llm`` : tout **changement pertinent** de la perception (information
  nouvelle, plan invalidé, palier de contexte) plus une revue de sécurité ;
- ``hybride`` : les mêmes déclencheurs, puis une **escalade** vers le modèle
  seulement si le monde est ambigu (critères d'`agents-et-llm.md` §3).

Règle de mesure : une politique qui se corrige à t10 n'a pas bien choisi à
t2. Le journal garde donc la cause de chaque reconsidération et de chaque
escalade, jamais un simple compteur.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from maree.v3.agents.appraisal import Action, Appraisal
from maree.v3.agents.perception import Perception
from maree.v3.agents.policy import Decision, _believed_blocked
from maree.v3.core.ports import PolicyName

if TYPE_CHECKING:
    from maree.v3.agents.agent import Agent

#: revue de sécurité sous menace (ticks). Un filet, pas une cadence : les
#: déclencheurs réels sont les fronts, les plans invalidés et les paliers.
REVIEW_INTERVAL = 60
#: palier de densité (pers/m²) qui fait changer le contexte perçu.
DENSITY_STEP = 0.5
#: seuil de densité « jamais vu » — au-delà, la situation est inédite.
DENSITY_UNSEEN = 1.5
#: pas de progression : moins de 2 m en 5 ticks.
NO_PROGRESS_TICKS = 5
NO_PROGRESS_METRES = 2.0
#: au-delà de cette distance, une fumée n'est pas « proche ».
CLOSE_DANGER_M = 15.0


@dataclass(frozen=True, slots=True)
class Reconsideration:
    """Faut-il reconsidérer maintenant ? Et pour quelle raison (journalisée)."""

    decide: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Escalation:
    """Une escalade vers le modèle, avec sa cause et ses valeurs."""

    cause: str
    detail: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# fronts (communs aux trois bras)
# ---------------------------------------------------------------------------
def novel_front(agent: Agent, perception: Perception) -> str | None:
    """Un signal **nouveau** que l'agent n'a jamais mémorisé.

    C'est la définition v2 des fronts, étendue à la fermeture d'issue. Un
    niveau (la fumée reste visible) n'est pas un front : sans cette
    distinction, chaque tick redéciderait (le coût de la v1).
    """
    if perception.smoke_visible and not agent.memory.has_seen_signal("fumée", True):
        return "information_nouvelle:fumee"
    if perception.announcement and not agent.memory.has_seen_signal(
        "annonce", perception.announcement
    ):
        return "information_nouvelle:annonce"
    for label in sorted(perception.closed_exits):
        if not agent.memory.has_seen_signal("fermeture", label):
            return f"information_nouvelle:fermeture:{label}"
    for message in perception.heard:
        if not agent.memory.has_seen_signal("message", message.fact):
            return "information_nouvelle:message"
    for kin in sorted(str(k) for k in agent.social.kin):
        if not agent.memory.has_seen_signal("proche", kin):
            return f"information_nouvelle:proche:{kin}"
    return None


# ---------------------------------------------------------------------------
# plan invalidé
# ---------------------------------------------------------------------------
def plan_invalidated(agent: Agent, perception: Perception) -> str | None:
    """L'engagement courant ne tient plus (cible bloquée, saturée, figée)."""
    last = agent._last_decision
    if last is None or last.action is not Action.EVACUER or not last.target:
        if last is not None and last.action in (
            Action.CHERCHER,
            Action.CHERCHER_PROCHE,
        ) and _no_progress(agent, perception):
            return "plan_invalide:pas_de_progression"
        return None
    target = last.target
    if _believed_blocked(agent.knowledge, target) and not agent.memory.has_seen_signal(
        "cible_bloquee", target
    ):
        return f"plan_invalide:cible_bloquee:{target}"
    if (
        perception.exits_visible
        and target not in perception.exits_visible
        and not agent.memory.has_seen_signal("cible_invisible", target)
    ):
        return f"plan_invalide:cible_invisible:{target}"
    if perception.crowding >= 1.0 and not agent.memory.has_seen_signal(
        "cible_saturee", target
    ):
        return f"plan_invalide:cible_saturee:{target}"
    if _no_progress(agent, perception):
        return "plan_invalide:pas_de_progression"
    return None


def _no_progress(agent: Agent, perception: Perception) -> bool:
    """Moins de 2 m parcourus en 5 ticks alors qu'on voulait avancer.

    Sans physique (banc de décision pur), ``perception.position`` est None :
    on ne peut pas mesurer une progression, donc on ne déclare rien.
    """
    if perception.position is None or not agent._trail:
        return False
    current = perception.position
    window = [
        (tick, point)
        for tick, point in agent._trail
        if tick >= perception.tick - NO_PROGRESS_TICKS
    ]
    if not window:
        return False
    oldest_tick, oldest_point = window[0]
    if perception.tick - oldest_tick < NO_PROGRESS_TICKS:
        return False
    travelled = (
        (current[0] - oldest_point[0]) ** 2 + (current[1] - oldest_point[1]) ** 2
    ) ** 0.5
    return travelled < NO_PROGRESS_METRES


# ---------------------------------------------------------------------------
# contexte (paliers)
# ---------------------------------------------------------------------------
def perception_key(perception: Perception) -> str:
    """Empreinte de la **situation pertinente** (jamais du tick seul).

    On n'y met pas les voisins bruts : quelqu'un passe à côté de moi à chaque
    tick. On y met des **paliers** (densité, partants, menace) et les signaux
    discrets (fumée, annonce, fermetures, sorties vues, distance au danger).
    SHA-256 : jamais ``hash()``, salé par processus (leçon v2).
    """
    if perception.distance_to_danger is None:
        distance_bucket = None
    else:
        distance_bucket = int(perception.distance_to_danger // 5)
    payload = {
        "fumee": bool(perception.smoke_visible),
        "annonce": perception.announcement,
        "fermees": sorted(perception.closed_exits),
        "densite": int(perception.crowding / DENSITY_STEP),
        "partants": min(4, perception.seen_leaving_elsewhere // 2),
        "menace": int(perception.threat / 0.2),
        "distance": distance_bucket,
        "voisins": min(4, len(perception.seen_agents) // 2),
        "sorties": sorted(perception.exits_visible),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    )
    return digest.hexdigest()


def review_due(agent: Agent, perception: Perception) -> bool:
    """Revue périodique **sous menace** : un filet, pas une horloge."""
    last = agent._last_decision
    if last is None:
        return False
    if perception.tick - last.tick < REVIEW_INTERVAL:
        return False
    return (
        perception.threat > 0.0
        or bool(perception.smoke_visible)
        or perception.crowding >= DENSITY_STEP
    )


# ---------------------------------------------------------------------------
# escalade (bras hybride)
# ---------------------------------------------------------------------------
def escalation_cause(
    agent: Agent,
    perception: Perception,
    *,
    base: Decision,
    appraisal: Appraisal,
    epsilon: float = 0.0,
    run_id: str = "v3",
) -> Escalation | None:
    """Le monde est-il assez ambigu pour que le modèle parle ?

    L'ordre est celui d'`agents-et-llm.md` §3 ; les contradictions passent
    avant le reste parce qu'elles sont le cas où une règle ne peut pas
    trancher seule.
    """
    contradiction = _live_contradiction(agent, perception)
    if contradiction is not None:
        return contradiction
    ambiguous = _ambiguous_announcement(agent, perception)
    if ambiguous is not None:
        return ambiguous
    unprecedented = _unprecedented(agent, perception)
    if unprecedented is not None:
        return unprecedented
    if _rules_uncertain(base, appraisal):
        return Escalation(
            "regles_indecises",
            {
                "action_regles": base.action.value,
                "menace": round(appraisal.menace, 2),
            },
        )
    if review_due(agent, perception):
        last = agent._last_decision
        return Escalation(
            "revue",
            {"dernier_avis": last.tick if last else None},
        )
    if epsilon_hit(run_id, perception.tick, agent.uid.uid, epsilon):
        return Escalation("quota", {"epsilon": epsilon})
    return None


def _live_contradiction(agent: Agent, perception: Perception) -> Escalation | None:
    """Une information **nouvelle** contredit ce que l'agent croit déjà.

    On ne signale pas une contradiction ancienne à chaque tick : seuls les
    messages et annonces pas encore mémorisés comptent. C'est ce qui évite
    de rappeler le modèle huit fois pour la même rumeur.
    """
    for message in perception.heard:
        if agent.memory.has_seen_signal("message", message.fact):
            continue
        for label in labels_in(message.fact, agent.known_exits):
            if closure_word(message.fact):
                if agent.knowledge.beliefs.get(f"exit:{label}") is not None:
                    return Escalation(
                        "information_contradictoire",
                        {
                            "sortie": label,
                            "message": message.fact,
                            "croyance": "praticable",
                            "source": str(message.from_agent),
                        },
                    )
            elif agent.knowledge.beliefs.get(f"hazard:{label}") is not None:
                return Escalation(
                    "information_contradictoire",
                    {
                        "sortie": label,
                        "message": message.fact,
                        "croyance": "bloquee",
                        "source": str(message.from_agent),
                    },
                )
    announcement = perception.announcement
    if announcement and not agent.memory.has_seen_signal(
        "annonce", announcement
    ):
        for label in named_exits(announcement, agent.known_exits):
            if _believed_blocked(agent.knowledge, label):
                return Escalation(
                    "information_contradictoire",
                    {
                        "sortie": label,
                        "annonce": announcement,
                        "croyance": "bloquee",
                    },
                )
    return None


def _ambiguous_announcement(
    agent: Agent, perception: Perception
) -> Escalation | None:
    announcement = perception.announcement
    if not announcement or agent.memory.has_seen_signal("annonce", announcement):
        return None
    named = named_exits(announcement, agent.known_exits)
    if len(named) == 0 or len(named) >= 2:
        return Escalation(
            "annonce_ambigue",
            {"texte": announcement, "sorties_citees": named},
        )
    return None


def _unprecedented(agent: Agent, perception: Perception) -> Escalation | None:
    if not any(key.startswith("exit:") for key in agent.knowledge.beliefs):
        return Escalation("situation_inedite", {"quoi": "aucune_sortie_connue"})
    if (
        perception.smoke_visible
        and not agent.memory.has_seen_signal("fumée", True)
        and perception.distance_to_danger is not None
        and perception.distance_to_danger < CLOSE_DANGER_M
    ):
        return Escalation(
            "situation_inedite",
            {
                "quoi": "fumee_proche",
                "distance": round(perception.distance_to_danger, 1),
            },
        )
    if (
        perception.crowding >= DENSITY_UNSEEN
        and not agent.memory.has_seen_signal("densite_forte", True)
    ):
        return Escalation(
            "situation_inedite",
            {"quoi": "densite_forte", "densite": round(perception.crowding, 2)},
        )
    return None


def _rules_uncertain(base: Decision, appraisal: Appraisal) -> bool:
    """L'ancien critère, conservé et **nommé** : il n'est plus le seul."""
    return (
        appraisal.menace >= 0.4
        and base.action in (Action.RESTER, Action.CHERCHER)
    ) or base.action is Action.SUIVRE


def epsilon_hit(run_id: str, tick: int, uid: int, epsilon: float) -> bool:
    """Tirage déterministe pour le quota ε (instrument, jamais un bras)."""
    if epsilon <= 0.0:
        return False
    if epsilon >= 1.0:
        return True
    digest = hashlib.sha256(f"{run_id}:{tick}:{uid}".encode()).digest()
    draw = int.from_bytes(digest[:8], "big") / 2**64
    return draw < epsilon


# ---------------------------------------------------------------------------
# calendrier par bras
# ---------------------------------------------------------------------------
def should_decide(agent: Agent, perception: Perception) -> Reconsideration:
    """Le calendrier propre au bras (fronts, changement pertinent, hybride)."""
    front = novel_front(agent, perception)
    if front is not None:
        return Reconsideration(True, front)
    if agent._last_decision is None:
        # au spawn on reste immobile : pas d'intention sans signal (ADR-014,
        # marche de référence — le premier appel vient du message de t2).
        return Reconsideration(False)
    if agent.policy is PolicyName.RULES:
        return Reconsideration(False)
    plan = plan_invalidated(agent, perception)
    if plan is not None:
        return Reconsideration(True, plan)
    if review_due(agent, perception):
        return Reconsideration(True, "revue")
    key = perception_key(perception)
    if agent._last_perception_key is not None and key != agent._last_perception_key:
        return Reconsideration(True, "contexte_change")
    return Reconsideration(False)


# ---------------------------------------------------------------------------
# petites analyses de texte (français, étiquettes de sortie)
# ---------------------------------------------------------------------------
def labels_in(text: str, known: frozenset[str] | set[str]) -> tuple[str, ...]:
    """Étiquettes de sortie **connues** citées dans un texte, triées."""
    import re

    tokens = {
        token
        for token in re.findall(r"\b[A-Z](?:\d{1,2})?\b", text.upper())
        if not token.isdigit()
    }
    return tuple(sorted(token for token in tokens if token in known))


def closure_word(text: str) -> bool:
    """Le texte annonce-t-il une fermeture (et non un ordre d'évacuation) ?"""
    lowered = text.lower()
    return any(
        word in lowered
        for word in ("bloqué", "bloquée", "bloqu", "fermé", "fermée", "close", "inaccessible")
    )


def named_exits(text: str, known: frozenset[str] | set[str]) -> list[str]:
    """Toutes les sorties nommées par une annonce (0, 1 ou plusieurs)."""
    return list(labels_in(text, known))


__all__ = [
    "Escalation",
    "Reconsideration",
    "epsilon_hit",
    "escalation_cause",
    "labels_in",
    "named_exits",
    "novel_front",
    "perception_key",
    "plan_invalidated",
    "review_due",
    "should_decide",
]
