"""agents.speech — qui parle, de quoi, à qui (C7).

Jusqu'ici la simulation avait un tuyau branché d'un seul côté : les agents
**recevaient** des messages (`Perception.heard`) mais n'en **émettaient**
jamais. Le seul contenu social venait de la chronologie. C'est ce qui
empêchait de mesurer l'émergence (B2/B3) : un accord ne peut pas naître
d'échanges qui n'ont pas lieu.

Trois décisions, toutes déterministes et journalisées :

- **qui parle** : `altruism` au-dessus d'un seuil, ou le rôle
  (`agent_de_securite`, qui a la charge de prévenir) ;
- **de quoi** : la sortie que l'on prend (« la sortie B est praticable ») ou
  un danger cru (« la sortie A est bloquée ») — jamais les deux, et jamais
  une sortie que l'on ne connaît pas ;
- **à qui** : les voisins **vus** (`Perception.seen_agents`), au plus
  `MAX_LISTENERS`, dans l'ordre de la perception.

Aucun message ne part d'un agent qui n'a rien décidé : parler de son intention
est ce qui rend le comportement observable. Un agent qui n'a pas bougé n'a
rien à dire.

Le message émis à t est **perçu à t+1** : la barrière de tick n'est pas
franchie (perception figée, convention n°4). C'est le prix de la lisibilité
du journal, et c'est aussi la vraie latence sociale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from maree.v3.agents.appraisal import Action
from maree.v3.agents.perception import Message
from maree.v3.core.ids import AgentId

if TYPE_CHECKING:
    from maree.v3.agents.agent import Agent
    from maree.v3.agents.perception import Perception

#: altruisme à partir duquel on prévient spontanément les voisins.
#: 0,5 est la valeur **par défaut** de `Traits` : un piéton ordinaire parle.
#: Un archétype franchement égoïste (< 0,5) se taît, et un rôle de sécurité
#: (0,95) parle toujours. Le seuil est un choix de modèle, pas une constante
#: physique — il est donc ici, nommé, et pas enfoui dans une condition.
ALTRIUM_THRESHOLD = 0.5
#: rôles qui parlent toujours (charge de sécurité, guidage).
SPEAKING_ROLES = ("agent_de_securite",)
#: nombre maximal de destinataires d'un même message (anti-explosion).
MAX_LISTENERS = 3


@dataclass(frozen=True, slots=True)
class Utterance:
    """Ce qu'un agent dit : un fait, sa confiance, ses destinataires."""

    fact: str
    confidence: float
    to: tuple[int, ...]
    kind: str  # "praticable" | "bloquee"

    def as_dict(self) -> dict[str, object]:
        return {
            "fact": self.fact,
            "confidence": round(self.confidence, 3),
            "to": list(self.to),
            "kind": self.kind,
        }


def _blocked_belief(agent: Agent) -> str | None:
    """La sortie que l'agent croit bloquée (la plus confiante au-dessus de 0,5)."""
    best: tuple[float, str] | None = None
    for key, belief in agent.knowledge.beliefs.items():
        if not key.startswith("hazard:"):
            continue
        label = key[len("hazard:"):]
        if label not in agent.known_exits or belief.confidence < 0.5:
            continue
        if best is None or belief.confidence > best[0]:
            best = (belief.confidence, label)
    return best[1] if best else None


def utterance(agent: Agent, perception: Perception) -> Utterance | None:
    """Le message que cet agent émet ce tick, ou ``None``.

    Déterministe : dépend de l'altruisme, du rôle, de la dernière décision et
    des croyances — jamais d'un tirage.
    """
    last = agent._last_decision
    if last is None or last.tick != perception.tick:
        # on ne parle que d'une décision prise à cet instant : un agent
        # immobile n'a rien à annoncer, et répéter la même phrase à chaque
        # tick saturerait les boîtes aux lettres.
        return None
    speaks = agent.traits.altruism >= ALTRIUM_THRESHOLD or agent.archetype in SPEAKING_ROLES
    if not speaks:
        return None
    listeners = tuple(a.uid for a in perception.seen_agents[:MAX_LISTENERS])
    if not listeners:
        return None

    blocked = _blocked_belief(agent)
    if blocked is not None:
        return Utterance(
            f"La sortie {blocked} est bloquée",
            agent.knowledge.beliefs[f"hazard:{blocked}"].confidence,
            listeners,
            "bloquee",
        )
    if last.action is Action.EVACUER and last.target in agent.known_exits:
        confidence = 0.5 + 0.5 * agent.traits.altruism
        return Utterance(
            f"La sortie {last.target} est praticable",
            confidence,
            listeners,
            "praticable",
        )
    return None


def as_message(item: Utterance, sender: AgentId, tick: int) -> Message:
    """Convertit une prise de parole en message perceptible au tick suivant."""
    return Message(item.fact, sender, tick + 1, item.confidence)


__all__ = [
    "ALTRIUM_THRESHOLD",
    "MAX_LISTENERS",
    "SPEAKING_ROLES",
    "Utterance",
    "as_message",
    "utterance",
]
