"""P3.1 — le bras `decision_head` : une distribution, pas une phrase.

Ce qu'un modèle de décision « System 1 » apporte, et ce qu'il n'apporte pas :

- il rend une **probabilité par option** sur un ensemble fermé — donc pas de
  JSON fragile, pas de cible inventée, et une trace auditable (marge,
  confiance) ;
- il ne raisonne pas : il **classe**. Mesuré sur Kev-4B (2026-11-22) : un état
  qui dit « Fumée visible » le laisse sur `RESTER` (0,42) ; le même état qui
  dit « Danger : fumée visible » le fait sortir (0,41) — et il reste sur
  `RESTER` en calme (0,79). C'est la **formulation de l'état**, pas le modèle,
  qui décide si la fumée est un danger.

Les tests ci-dessous n'appellent pas le réseau : ils vérifient le câblage
(options, état, argmax, replis) avec un head bouchon.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from maree.v3.adapters.decision_head import HeadAnswer
from maree.v3.agents.agent import make_agent
from maree.v3.agents.appraisal import Action, appraise
from maree.v3.agents.knowledge import Belief, Source
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.policy_head import (
    DecisionHeadPolicy,
    criteria_for,
    state_text,
)
from maree.v3.agents.state import State
from maree.v3.core.ids import ZoneId

KNOWN = frozenset({"A", "B"})


def _perc(*, smoke: bool = False, announcement: str | None = None,
          heard: tuple[Message, ...] = ()) -> Perception:
    return Perception(
        tick=10, zone=ZoneId("L0"), state=State(), smoke_visible=smoke,
        announcement=announcement, heard=heard, seen_agents=(),
        exits_visible=frozenset(),
    )


@dataclass
class FakeHead:
    """Head bouchon : rend la distribution demandée, sans réseau."""

    choice: str = "RESTER"
    probabilities: dict[str, float] = field(default_factory=lambda: {"RESTER": 1.0})
    ok: bool = True
    model: str = "fake"

    def choose(self, state: str, instructions: str, criteria: dict[str, str]) -> HeadAnswer:
        return HeadAnswer(
            choice=self.choice,
            probabilities=dict(self.probabilities),
            confidence=0.9,
            input_tokens=42,
            ok=self.ok,
            error=None if self.ok else "panne simulée",
        )


def _decide(head: object, perception: Perception) -> object:
    agent = make_agent(1, "visiteur", known_exits=KNOWN)
    ap = appraise(
        perception=perception, traits=agent.traits, knowledge=agent.knowledge,
        social=agent.social, name=agent.name,
    )
    return DecisionHeadPolicy(head=head).decide(  # type: ignore[arg-type]
        perception=perception, knowledge=agent.knowledge, social=agent.social,
        traits=agent.traits, appraisal=ap, known_exits=KNOWN, name=agent.name,
    )


def test_les_options_sont_fermees_et_connues_du_moteur() -> None:
    criteria = criteria_for(KNOWN)
    assert set(criteria) == {"RESTER", "SORTIR A", "SORTIR B"}
    # jamais d'option sur une sortie inconnue de l'agent
    assert not any(label.endswith("C") for label in criteria)


def test_l_etat_dit_le_danger_et_les_croyances() -> None:
    agent = make_agent(1, "visiteur", known_exits=KNOWN)
    agent.knowledge.beliefs["hazard:B"] = Belief("bloquée", 0.8, Source.ENTENDU, 1)
    text = state_text(_perc(smoke=True), agent.knowledge, KNOWN)
    # l'état nomme la fumée comme **danger** (un System 1 lit l'étiquette)
    assert "Danger : fumee visible" in text
    assert "Sorties connues : A, B" in text
    assert "signalees dangereuses : B" in text


def test_un_choix_rester_donne_une_decision_rester() -> None:
    d = _decide(FakeHead(choice="RESTER", probabilities={"RESTER": 0.8, "SORTIR A": 0.2}), _perc())
    assert d.action is Action.RESTER          # type: ignore[attr-defined]
    assert d.fallback is False                # type: ignore[attr-defined]
    trace = d.llm_trace                        # type: ignore[attr-defined]
    assert trace is not None and trace.response.ok
    assert "probabilities" in trace.response.text


def test_un_choix_sortir_donne_la_cible_nommee() -> None:
    d = _decide(FakeHead(choice="SORTIR B", probabilities={"SORTIR B": 0.7}), _perc(smoke=True))
    assert d.action is Action.EVACUER         # type: ignore[attr-defined]
    assert d.target == "B"                     # type: ignore[attr-defined]


def test_une_sortie_inconnue_replie() -> None:
    d = _decide(FakeHead(choice="SORTIR Z", probabilities={"SORTIR Z": 0.9}), _perc(smoke=True))
    assert d.fallback is True                  # type: ignore[attr-defined]
    assert d.fallback_cause == "unknown_exit"  # type: ignore[attr-defined]


def test_une_panne_replie_sur_les_regles_et_le_dit() -> None:
    d = _decide(FakeHead(ok=False), _perc(smoke=True))
    assert d.fallback is True                  # type: ignore[attr-defined]
    assert d.fallback_cause == "no_response"   # type: ignore[attr-defined]
    assert d.action is Action.EVACUER          # type: ignore[attr-defined]  # les règles sortent
