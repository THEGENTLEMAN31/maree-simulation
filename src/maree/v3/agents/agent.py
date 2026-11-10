"""agents.agent — l'agent, assemblage de traits + état + connaissance + mémoire.

L'agent est la pièce centrale de la mission 1 : deux agents du même
archétype partagent traits, état *initial* et connaissance *partagée* ;
ils diffèrent par leurs **mémoires personnelles** (épisodes, reçus, fronts
déjà vus). ``react()`` produit une décision portable et journalisée.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from maree.v3.agents.appraisal import Appraisal, appraise
from maree.v3.agents.knowledge import Belief, Knowledge, Source
from maree.v3.agents.memory import EpisodeKind, Memory
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.policy import Decision, rules_decide
from maree.v3.agents.policy_llm import LLMPolicy, hybrid_decide
from maree.v3.agents.social import SocialState
from maree.v3.agents.state import State
from maree.v3.agents.traits import Traits
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import PolicyName


@dataclass(slots=True)
class Agent:
    """Un individu. ``uid`` est stable dans un run."""

    uid: AgentId
    name: str
    archetype: str
    traits: Traits
    knowledge: Knowledge = field(default_factory=Knowledge)
    memory: Memory = field(default_factory=Memory)
    social: SocialState = field(default_factory=SocialState)
    state: State = field(default_factory=State)
    #: les sorties que cet agent est *censé* connaître (le plan).
    known_exits: frozenset[str] = frozenset()
    #: politique de décision (règles par défaut, hybride ou LLM).
    policy: PolicyName = PolicyName.RULES
    _last_decision: Decision | None = field(default=None, init=False)

    # --- réaction ---
    def react(self, perception: Perception) -> Decision:
        """Décide face à une perception figée, en consommant sa mémoire.

        Comportement de front : si aucun **signal nouveau** (front fumée,
        annonce, message) n'apparaît, on conserve la dernière décision au
        lieu de re-décider à chaque tick.
        """
        if not self._novel_events(perception) and self._last_decision is not None:
            return self._last_decision

        ap = appraise(
            perception=perception,
            traits=self.traits,
            knowledge=self.knowledge,
            social=self.social,
            name=self.name,
        )
        decision = self._decide(perception, ap)
        self._consume(perception, decision, ap)
        self._last_decision = decision
        return decision

    def _decide(self, perception: Perception, ap: Appraisal) -> Decision:
        """Répartit sur la politique courante (registre de décisions)."""
        if self.policy is PolicyName.LLM:
            return LLMPolicy().decide(
                perception=perception,
                knowledge=self.knowledge,
                social=self.social,
                traits=self.traits,
                appraisal=ap,
                known_exits=self.known_exits,
                name=self.name,
            )
        if self.policy is PolicyName.HYBRID:
            return hybrid_decide(
                perception=perception,
                knowledge=self.knowledge,
                social=self.social,
                traits=self.traits,
                appraisal=ap,
                known_exits=self.known_exits,
                name=self.name,
            )
        return rules_decide(
            perception=perception,
            knowledge=self.knowledge,
            social=self.social,
            traits=self.traits,
            appraisal=ap,
            known_exits=self.known_exits,
            name=self.name,
        )

    def _novel_events(self, perception: Perception) -> bool:
        if perception.smoke_visible and not self.memory.has_seen_signal("fumée", True):
            return True
        if perception.announcement and not self.memory.has_seen_signal(
            "annonce", perception.announcement
        ):
            return True
        if self.social.kin and any(
            not self.memory.has_seen_signal("proche", str(k)) for k in self.social.kin
        ):
            return True
        return any(
            not self.memory.has_seen_signal("message", m.fact)
            for m in perception.heard
        )

    def _consume(
        self, perception: Perception, decision: Decision, ap: Appraisal
    ) -> None:
        """Journalise la décision et l'apprentissage dans la mémoire."""
        tick = perception.tick
        # fronts mémorisés : on ne re-décide plus pour eux
        if perception.smoke_visible:
            self.memory.mark_signal_seen("fumée", True)
            self.memory.learn("fumée visible", Source.VU, tick, 0.9)
        if perception.announcement:
            self.memory.mark_signal_seen("annonce", perception.announcement)
        for k in list(self.social.kin):
            self.memory.mark_signal_seen("proche", str(k))
        for m in perception.heard:
            self.memory.mark_signal_seen("message", m.fact)
            # influence sociale : je crois ce que dit un émetteur, pondéré
            # par ma tendance à suivre (herding) et ma confiance en lui.
            weight = m.confidence * (0.3 + 0.7 * self.traits.herding)
            for label in self._labels_in(m.fact):
                if self._closure_word(m.fact):
                    # message négatif : je crois la sortie bloquée
                    self.knowledge.set(
                        f"hazard:{label}",
                        Belief("sortie bloquée", weight, Source.ENTENDU, tick),
                    )
                    self.memory.learn(f"{label} est bloquée", Source.ENTENDU, tick, weight)
                else:
                    # ouï-dire : j'apprends / renforce la sortie, sourcée et
                    # pondérée par la confiance (un bruit reste un bruit).
                    self.knowledge.set(
                        f"exit:{label}",
                        Belief(label, weight, Source.ENTENDU, tick),
                    )
                    self.memory.learn(f"{label} est praticable", Source.ENTENDU, tick, weight)

        # épisode de décision + oubli (les fronts restent, la confiance décroît)
        self.memory.log_episode(
            tick,
            EpisodeKind.DECIDE,
            f"{decision.action.value} -> {decision.target}",
            "moi",
        )
        self.knowledge.decay(0.98, tick, floor=0.1)

    @staticmethod
    def _closure_word(text: str) -> bool:
        lowered = text.lower()
        return any(
            w in lowered
            for w in ("bloqué", "bloquée", "fermé", "fermée", "close", "inaccessible")
        )

    @staticmethod
    def _labels_in(text: str) -> tuple[str, ...]:
        """Candidats étiquettes de sortie cités dans un message (A, B, A12…).

        Trié pour déterminisme ; les chiffres seuls ne sont pas retenus.
        """
        import re

        found = sorted(
            {
                token
                for token in re.findall(r"\b[A-Z](?:\d{1,2})?\b", text.upper())
                if not token.isdigit()
            }
        )
        return tuple(found)

    def add_belief(self, key: str, fact: str, confidence: float, source: Source, tick: int) -> None:
        """Enregistre une croyance (initialisation, message, reçu)."""
        self.knowledge.set(key, Belief(fact, confidence, source, tick))

    # --- observation sociale ---
    def observe(self, other: Agent, behavior: str) -> None:
        self.social.observed[other.uid] = behavior

    def receive(self, message: Message) -> None:
        """Enregistre la confiance envers un émetteur ; la croyance se
        consolide à la réaction suivante via la perception."""
        self.social.set_trust(message.from_agent, message.confidence)


def make_agent(
    uid: int,
    archetype: str = "visiteur",
    name: str | None = None,
    known_exits: frozenset[str] = frozenset(),
) -> Agent:
    """Fabrique un agent de l'archétype donné (portail de test et de sim).

    La confiance initiale sur chaque sortie connue découle de
    ``spatial_confidence`` : un habitué croit *connaître* une sortie avec
    plus de confiance qu'un visiteur qui ne la connaît pas.
    """
    traits = archetype_registry(archetype)
    agent = Agent(
        uid=AgentId(uid),
        name=name or f"A{uid:02d}",
        archetype=archetype,
        traits=traits,
        known_exits=known_exits,
    )
    for label in sorted(known_exits):
        agent.knowledge.set(
            f"exit:{label}",
            Belief(label, traits.spatial_confidence, Source.CONNU, 0),
        )
    return agent


def archetype_registry(name: str) -> Traits:
    from maree.v3.agents.traits import archetype as _archetype

    return _archetype(name)


__all__ = ["Agent", "make_agent"]