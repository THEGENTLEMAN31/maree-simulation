"""A5 — le tier « petit » : une règle et deux drapeaux, pas un contrat JSON.

Leçons v2, toutes mesurées sur qwen3-0-6B et reproduites ici à coût nul :

- JSON à vocabulaire ouvert → il recopie le gabarit, jamais une sortie ;
- liste de mots-clés → il choisit **la première option**, quel que soit le
  contexte (c'est une position, pas une lecture) ;
- question binaire → instable ;
- **règle écrite + deux drapeaux** → calme 6/6, fumée 6/6, annonce 2/6.

Ce que l'on verrouille donc :

- le prompt du petit ne contient **aucun** contrat JSON (les deux consignes
  mêlées le faisaient répondre « oui » à t1, sans fumée) ;
- il tient en quelques dizaines de caractères : deux faits, pas un dossier ;
- ``parse_choice`` lit ``RESTER`` / ``SORTIR <sortie>`` et refuse une sortie
  inconnue (repli ``unknown_exit``, pas une évacuation devinée) ;
- le grand garde son contrat JSON.
"""

from __future__ import annotations

from maree.v3.adapters.chat_stub import StubChat
from maree.v3.agents.agent import make_agent
from maree.v3.agents.appraisal import Action, appraise
from maree.v3.agents.catalog import register_provider
from maree.v3.agents.perception import Perception
from maree.v3.agents.policy_llm import (
    SYSTEM_PROMPT,
    LLMPolicy,
    parse_choice,
    small_messages,
)
from maree.v3.agents.state import State
from maree.v3.core.ids import ZoneId

KNOWN = frozenset({"A", "B"})


def _perc(smoke: bool = False, announcement: str | None = None) -> Perception:
    return Perception(
        tick=10,
        zone=ZoneId("z"),
        state=State(),
        smoke_visible=smoke,
        announcement=announcement,
        seen_agents=(),
        exits_visible=frozenset(),
    )


def _decide(policy: LLMPolicy, perception: Perception) -> object:
    agent = make_agent(1, "visiteur", known_exits=KNOWN)
    ap = appraise(
        perception=perception,
        traits=agent.traits,
        knowledge=agent.knowledge,
        social=agent.social,
        name=agent.name,
    )
    return policy.decide(
        perception=perception,
        knowledge=agent.knowledge,
        social=agent.social,
        traits=agent.traits,
        appraisal=ap,
        known_exits=KNOWN,
        name=agent.name,
    )


def test_le_prompt_du_petit_ne_contient_pas_le_contrat_json() -> None:
    messages = small_messages(_perc(smoke=True), KNOWN)
    system = messages[0].content
    user = messages[1].content
    assert "{" not in system and "{" not in user
    assert "JSON" not in system
    # le grand, lui, garde son contrat
    assert "{" in SYSTEM_PROMPT and "JSON" in SYSTEM_PROMPT


def test_le_prompt_du_petit_tient_en_deux_drapeaux() -> None:
    user = small_messages(_perc(smoke=True), KNOWN)[1].content
    assert "Fumée visible : oui" in user
    assert "Annonce d'évacuation : non" in user
    # la fumée est le dernier **drapeau** (avant la liste des sorties et la
    # question) : un petit modèle pèse la fin du prompt
    lines = user.splitlines()
    assert lines.index("Décide :") == len(lines) - 1
    assert lines[2].startswith("Fumée visible")
    assert len(user) < 200            # deux faits, pas un dossier
    calm = small_messages(_perc(), KNOWN)[1].content
    assert "Fumée visible : non" in calm


def test_une_annonce_de_fermeture_n_est_pas_un_ordre_pour_le_petit() -> None:
    user = small_messages(_perc(announcement="La sortie A est bloquée"), KNOWN)[1].content
    assert "Annonce d'évacuation : non" in user


def test_parse_choice_lit_le_vocabulaire_du_petit() -> None:
    assert parse_choice("RESTER", KNOWN) == (Action.RESTER, None)
    assert parse_choice("SORTIR A", KNOWN) == (Action.EVACUER, "A")
    assert parse_choice("sortir b", KNOWN) == (Action.EVACUER, "B")
    # une sortie inconnue n'est pas devinée
    assert parse_choice("SORTIR Z", KNOWN) is None
    # pas d'étiquette (ou le gabarit recopié) : le moteur choisira la porte
    assert parse_choice("SORTIR", frozenset({"C"})) == (Action.EVACUER, None)
    assert parse_choice("SORTIR <lettre de la sortie>", KNOWN) == (
        Action.EVACUER, None,
    )


def test_le_petit_obtient_un_prompt_court_et_suit_les_drapeaux() -> None:
    seen: list[str] = []

    def obey(request: object) -> str:
        content = request.messages[-1].content  # type: ignore[attr-defined]
        seen.append(content)
        if "Fumée visible : oui" not in content and "Annonce d'évacuation : oui" not in content:
            return "RESTER"
        for line in content.splitlines():
            if line.startswith("Sortie indiquée : "):
                target = line.split(": ", 1)[1].strip()
                if target in KNOWN:
                    return f"SORTIR {target}"
        return "SORTIR A"

    register_provider("llamacpp-small", StubChat(obey))
    policy = LLMPolicy(alias="petit")

    calm = _decide(policy, _perc())
    assert calm.action is Action.RESTER          # type: ignore[attr-defined]
    assert calm.fallback is False                # type: ignore[attr-defined]

    smoke = _decide(policy, _perc(smoke=True))
    assert smoke.action is Action.EVACUER        # type: ignore[attr-defined]
    assert smoke.target == "A"                   # type: ignore[attr-defined]

    announced = _decide(policy, _perc(announcement="Veuillez évacuer par la sortie B"))
    assert announced.target == "B"               # type: ignore[attr-defined]

    # aucun prompt envoyé ne contient de JSON : c'est le protocole, pas le hasard
    assert all("{" not in content for content in seen)
    # et ils sont courts (le petit modèle n'a que 2 048 jetons de contexte)
    assert max(len(content) for content in seen) < 200


def test_une_sortie_inconnue_replie_avec_la_bonne_cause() -> None:
    register_provider("llamacpp-small", StubChat(lambda _r: "SORTIR Z"))
    decision = _decide(LLMPolicy(alias="petit"), _perc(smoke=True))
    assert decision.fallback is True                    # type: ignore[attr-defined]
    assert decision.fallback_cause == "unknown_exit"    # type: ignore[attr-defined]


def test_une_cible_resolue_par_le_moteur_est_marquee() -> None:
    """La mesure ne doit pas créditer le modèle d'un choix qu'il n'a pas fait."""
    register_provider("llamacpp-small", StubChat(lambda _r: "SORTIR <lettre de la sortie>"))
    decision = _decide(LLMPolicy(alias="petit"), _perc(smoke=True))
    assert decision.action is Action.EVACUER        # type: ignore[attr-defined]
    assert decision.target in KNOWN                 # type: ignore[attr-defined]
    assert decision.target_resolved is True         # type: ignore[attr-defined]
    assert decision.fallback is False               # type: ignore[attr-defined]
