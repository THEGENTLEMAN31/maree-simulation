"""agents.agent — l'agent, assemblage de traits + état + connaissance + mémoire.

L'agent est la pièce centrale de la mission 1 : deux agents du même
archétype partagent traits, état *initial* et connaissance *partagée* ;
ils diffèrent par leurs **mémoires personnelles** (épisodes, reçus, fronts
déjà vus). ``react()`` produit une décision portable et journalisée.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from maree.v3.agents.appraisal import Action, Appraisal, appraise
from maree.v3.agents.knowledge import Belief, Knowledge, Source
from maree.v3.agents.memory import EpisodeKind, Memory
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.policy import Decision, _believed_blocked, rules_decide
from maree.v3.agents.policy_llm import LLMPolicy, hybrid_decide
from maree.v3.agents.preference import preferred_exit
from maree.v3.agents.prehistory import prehistory_for, seed_prehistory
from maree.v3.agents.schedule import (
    DENSITY_UNSEEN,
    Reconsideration,
    novel_front,
    perception_key,
    should_decide,
)
from maree.v3.agents.social import SocialState
from maree.v3.agents.state import State
from maree.v3.agents.traits import Traits
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import PolicyName
from maree.v3.world.worldspec import Point


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
    #: base de connaissances (retriever RAG) que la politique LLM interroge.
    retriever: Any = None
    #: alias du modèle LLM pour cet agent (A5) : "decision" (grand) ou "petit".
    llm_alias: str | None = None
    #: identifiant du run (tirage ε déterministe, quota instrumenté).
    run_id: str = "v3"
    #: quota ε (0 = jamais) — instrument de sensibilité, jamais un bras.
    epsilon: float = 0.0
    #: vrai si un ouï-dire a **effectivement changé** la sortie préférée (B2) ;
    #: une rumeur qui confirme n'est pas une construction sociale.
    preference_changed_by_hearsay: bool = False
    _last_decision: Decision | None = field(default=None, init=False)
    #: empreinte de la dernière perception *décidée* (calendrier LLM/hybride).
    _last_perception_key: str | None = field(default=None, init=False)
    #: (tick, position) récents — mesure « pas de progression » (plan invalidé).
    _trail: list[tuple[int, Point]] = field(default_factory=list, init=False)

    # --- réaction ---
    def react(self, perception: Perception, *, force: bool = False) -> Decision:
        """Décide face à une perception figée, en consommant sa mémoire.

        ``force=True`` saute le calendrier : utilisé par l'orchestrateur qui
        l'a déjà consulté (sinon une décision asynchrone, gardée pour un tick
        passé, serait refusée par son propre calendrier).
        Comportement de front : si aucun **signal nouveau** n'apparaît, on
        conserve la dernière décision au lieu de redécider à chaque tick.
        """
        self._note_position(perception)
        if not force and self._last_decision is not None:
            gate = should_decide(self, perception)
            if not gate.decide:
                return self._last_decision

        # Ce que l'on croyait bloqué **avant** ce tick : sert à distinguer
        # « je viens de l'apprendre » (une correction reste à faire) de « je le
        # savais et j'ai quand même choisi » (on ne rappelle pas le modèle à
        # chaque tick pour la même cible).
        blocked_before = {
            label
            for label in self.known_exits
            if _believed_blocked(self.knowledge, label)
        }
        # La perception est **consommée avant** la décision : un message entendu
        # à t fait partie de ce que l'agent sait lorsqu'il décide à t. Avant ce
        # correctif (2026-11-18), la croyance n'était écrite qu'après la
        # décision : « A est bloquée » au même tick que la fumée n'était donc
        # jamais utilisée, et les règles partaient vers la porte qu'elles
        # venaient d'apprendre fermée.
        self._learn(perception)

        ap = appraise(
            perception=perception,
            traits=self.traits,
            knowledge=self.knowledge,
            social=self.social,
            name=self.name,
        )
        decision = self._decide(perception, ap)
        if decision.action is Action.EVACUER and decision.target:
            decision = replace(
                decision,
                target_believed_blocked=_believed_blocked(
                    self.knowledge, decision.target
                ),
            )
        self._record(perception, decision, blocked_before)
        self._last_decision = decision
        self._last_perception_key = perception_key(perception)
        return decision

    def should_decide(self, perception: Perception) -> Reconsideration:
        """Le calendrier de ce bras (ADR-014), journalisé par sa cause."""
        self._note_position(perception)
        return should_decide(self, perception)

    def _note_position(self, perception: Perception) -> None:
        """Garde la trace du corps pour détecter l'absence de progression."""
        if perception.position is None:
            return
        if self._trail and self._trail[-1][0] >= perception.tick:
            return
        self._trail.append((perception.tick, perception.position))
        if len(self._trail) > 16:
            del self._trail[:-16]

    def _decide(self, perception: Perception, ap: Appraisal) -> Decision:
        """Répartit sur la politique courante (registre de décisions)."""
        rag = self._rag_context(perception)
        if self.policy is PolicyName.LLM:
            return LLMPolicy(alias=self.llm_alias or "decision").decide(
                perception=perception,
                knowledge=self.knowledge,
                social=self.social,
                traits=self.traits,
                appraisal=ap,
                known_exits=self.known_exits,
                name=self.name,
                memory=self.memory,
                rag=rag,
            )
        if self.policy is PolicyName.DECISION_HEAD:
            from maree.v3.agents.policy_head import (
                DecisionHeadPolicy,
                default_head,
            )

            return DecisionHeadPolicy(head=default_head()).decide(
                perception=perception,
                knowledge=self.knowledge,
                social=self.social,
                traits=self.traits,
                appraisal=ap,
                known_exits=self.known_exits,
                name=self.name,
                memory=self.memory,
                rag=rag,
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
                memory=self.memory,
                rag=rag,
                alias=self.llm_alias or "decision",
                run_id=self.run_id,
                epsilon=self.epsilon,
                agent=self,
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

    def _rag_context(self, perception: Perception) -> list[dict[str, object]] | None:
        """Interroge la base de connaissances (retriever) pour une décision LLM.

        La requête est construite depuis la situation perçue ; le retriever
        filtre par **temps simulé** (C6 : rien de t > now) et **profil**
        (F1). Pas de retriever ⇒ pas de RAG (décision sans base, journalisée).
        """
        if self.retriever is None:
            return None
        query = (
            "quelle sortie est sûre pour évacuer ? "
            f"fumée={perception.smoke_visible} "
            f"annonce={perception.announcement or ''}"
        )
        try:
            hits = self.retriever.retrieve(
                query, now=perception.tick, profile=self.archetype, k=3
            )
        except Exception:
            return None
        return [
            {
                "id": doc.metadata.get("id"),
                "titre": doc.metadata.get("title"),
                "collection": doc.metadata.get("collection"),
                "contenu": doc.page_content,
            }
            for doc, _score in hits
        ]

    def _novel_events(self, perception: Perception) -> bool:
        """Compatibilité : un front nouveau existe-t-il ? (usage interne)."""
        return novel_front(self, perception) is not None

    def _learn(self, perception: Perception) -> None:
        """Intègre la perception dans les croyances — **avant** de décider.

        Un message, une annonce de fermeture et une sortie vue fermée sont des
        perceptions : ils doivent peser sur la décision du tick où ils sont
        perçus, pas seulement sur la suivante. Le calendrier reste inchangé :
        ce sont les *fronts* qui déclenchent une reconsidération, pas
        l'écriture d'une croyance.
        """
        tick = perception.tick
        # fronts mémorisés : on ne re-décide plus pour eux
        if perception.smoke_visible:
            self.memory.mark_signal_seen("fumée", True, tick)
            self.memory.learn("fumée visible", Source.VU, tick, 0.9)
        if perception.announcement:
            self.memory.mark_signal_seen("annonce", perception.announcement, tick)
            # D8 : une annonce n'est pas qu'un drapeau, c'est une **croyance**
            # datée, pondérée par la confiance en l'autorité. Ce que dit la
            # sono et ce que dit un voisin n'ont pas le même poids.
            from maree.v3.agents.policy import _is_evacuation_order, _named_exit

            if _is_evacuation_order(perception.announcement):
                named = _named_exit(perception.announcement, set(self.known_exits))
                if named is not None:
                    self.knowledge.set(
                        f"exit:{named}",
                        Belief(
                            named,
                            0.5 + 0.5 * self.traits.authority_trust,
                            Source.ANNONCE,
                            tick,
                        ),
                    )
            if self._closure_word(perception.announcement):
                weight = 0.6 + 0.4 * self.traits.authority_trust
                for label in self._labels_in(perception.announcement):
                    if label not in self.known_exits:
                        continue
                    self.knowledge.set(
                        f"hazard:{label}",
                        Belief("sortie fermée", weight, Source.ANNONCE, tick),
                    )
        for label in sorted(perception.closed_exits):
            if label not in self.known_exits:
                continue
            self.memory.mark_signal_seen("fermeture", label, tick)
            self.knowledge.set(
                f"hazard:{label}",
                Belief("sortie fermée", 1.0, Source.VU, tick),
            )
            self.memory.learn(f"{label} est fermée", Source.VU, tick, 1.0)
        for k in list(self.social.kin):
            self.memory.mark_signal_seen("proche", str(k), tick)
        before_preference = preferred_exit(self)
        for m in perception.heard:
            self.memory.mark_signal_seen("message", m.fact, tick)
            # influence sociale : je crois ce que dit un émetteur, pondéré
            # par ma tendance à suivre (herding) et ma confiance en lui.
            weight = m.confidence * (0.3 + 0.7 * self.traits.herding)
            for label in self._labels_in(m.fact):
                if label not in self.known_exits:
                    # la géographie ne s'apprend pas par ouï-dire (C3) : un
                    # visiteur ne crée pas une croyance sur une sortie inconnue.
                    continue
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

        # B2 : couplage réel = la préférence a **changé** à cause d'un ouï-dire.
        # « la source est ENTENDU » ne suffit pas : un message qui confirme la
        # sortie déjà préférée est de la diffusion, pas une construction.
        if perception.heard:
            after_preference = preferred_exit(self)
            if (
                after_preference is not None
                and after_preference != before_preference
            ):
                self.preference_changed_by_hearsay = True

    def _record(
        self,
        perception: Perception,
        decision: Decision,
        blocked_before: set[str],
    ) -> None:
        """Journalise la décision, les marques de calendrier et l'oubli."""
        tick = perception.tick
        # plan invalidé : on mémorise ce qui a déjà été signalé pour ne pas
        # rappeler le modèle pour la même cible à chaque tick.
        if decision.action is Action.EVACUER and decision.target:
            # La cible choisie était déjà crue bloquée **avant** ce tick : le
            # calendrier a donc déjà eu sa chance de corriger (plan invalidé).
            # On note la cible pour ne pas escalader en boucle ; si l'agent
            # apprend le blocage *maintenant*, on ne note rien, pour laisser
            # passer la reconsidération du tick suivant.
            if decision.target in blocked_before:
                self.memory.mark_signal_seen(
                    "cible_bloquee", decision.target, tick
                )
            if (
                perception.exits_visible
                and decision.target not in perception.exits_visible
            ):
                self.memory.mark_signal_seen(
                    "cible_invisible", decision.target, tick
                )
            if perception.crowding >= 1.0:
                self.memory.mark_signal_seen(
                    "cible_saturee", decision.target, tick
                )
        if perception.crowding >= DENSITY_UNSEEN:
            self.memory.mark_signal_seen("densite_forte", True, tick)

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

    # --- déplacement (caractéristiques physiques, pour le moteur) ---
    @property
    def speed_max(self) -> float:
        """Vitesse de déplacement maximale (m/s) du profil, hors fatigue.

        La ``mobility`` du trait (0..1) s'échelonne de marche lente (0,5 m/s)
        à un pas soutenu (1,4 m/s) — une caractéristique par agent, pas globale.
        """
        return 0.5 + 0.9 * self.traits.mobility

    def current_speed(self) -> float:
        """La vitesse *réelle* maintenant, réduite par la fatigue et la densité."""
        speed = self.speed_max
        speed *= 1.0 - 0.5 * self.state.fatigue              # la fatigue ralentit
        speed *= 1.0 - 0.3 * min(1.0, self.state.crowding / 3.0)  # la foule freine
        return max(0.0, speed)


def make_agent(
    uid: int,
    archetype: str = "visiteur",
    name: str | None = None,
    known_exits: frozenset[str] = frozenset(),
    prehistory: bool = False,
    retriever: Any = None,
) -> Agent:
    """Fabrique un agent de l'archétype donné (portail de test et de sim).

    La confiance initiale sur chaque sortie connue découle de
    ``spatial_confidence`` : un habitué croit *connaître* une sortie avec
    plus de confiance qu'un visiteur qui ne la connaît pas.
    ``prehistory=True`` amorce la mémoire avec les échanges J−3 de
    l'archétype (A1) ; ``retriever`` branche la base de connaissances (RAG).
    """
    traits = archetype_registry(archetype)
    agent = Agent(
        uid=AgentId(uid),
        name=name or f"A{uid:02d}",
        archetype=archetype,
        traits=traits,
        known_exits=known_exits,
        retriever=retriever,
    )
    for label in sorted(known_exits):
        agent.knowledge.set(
            f"exit:{label}",
            Belief(label, traits.spatial_confidence, Source.CONNU, 0),
        )
    if prehistory:
        seed_prehistory(agent.memory, prehistory_for(archetype))
    return agent


def archetype_registry(name: str) -> Traits:
    from maree.v3.agents.traits import archetype as _archetype

    return _archetype(name)


__all__ = ["Agent", "make_agent"]