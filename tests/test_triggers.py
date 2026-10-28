"""Déclencheurs : la réponse au coût des 60 agents.

Chaque test vérifie qu'une **nouveauté** provoque une décision, et que
l'absence de nouveauté n'en provoque pas. C'est ce qui fait passer le
run de 2 160 appels LLM à quelques dizaines.
"""

from __future__ import annotations

from maree.agents.triggers import Message, Percept, should_decide


def _percept(**kwargs) -> Percept:
    base = dict(tick=10, position=(10.0, 10.0), zone="Z1", exits_open=frozenset({"A", "B", "C"}))
    base.update(kwargs)
    return Percept(**base)


def _decide(percept: Percept, **kwargs):
    base = dict(last_decision_tick=9, current_exit="A", known_messages=frozenset(), max_idle=6)
    base.update(kwargs)
    return should_decide(percept, **base)


def test_sortie_fermee_est_prioritaire() -> None:
    trigger = _decide(_percept(exits_open=frozenset({"B", "C"})), current_exit="A")
    assert trigger.needed
    assert trigger.reason == "sortie_fermee"
    assert trigger.urgency == 1.0


def test_fumee_visible() -> None:
    trigger = _decide(_percept(smoke_visible=True, smoke_intensity=0.6))
    assert trigger.reason == "fumee_visible"


def test_la_fumee_ne_declenche_qu_une_fois() -> None:
    """Signal de front, pas de niveau.

    La fumée reste visible jusqu'à la fin du run. Si elle redéclenchait à
    chaque tick, les 60 agents redécideraient 60 fois par tick : on
    aurait reconstruit le coût de la v1.
    """
    trigger = _decide(
        _percept(smoke_visible=True, smoke_intensity=0.6),
        known_signals=frozenset({"smoke"}),
    )
    assert trigger.reason != "fumee_visible"


def test_l_annonce_ne_declenche_qu_une_fois() -> None:
    trigger = _decide(
        _percept(announcement="Évacuation."),
        known_signals=frozenset({"announcement"}),
    )
    assert trigger.reason != "annonce"


def test_fumee_imperceptible_ne_declenche_pas() -> None:
    trigger = _decide(_percept(smoke_visible=True, smoke_intensity=0.01))
    assert trigger.reason != "fumee_visible"


def test_annonce() -> None:
    assert _decide(_percept(announcement="Évacuation.")).reason == "annonce"


def test_message_nouveau() -> None:
    message = Message(sender="A03", content="la sortie B est libre", tick=10)
    trigger = _decide(_percept(messages=(message,)))
    assert trigger.reason == "message:A03"


def test_message_deja_connu_est_ignore() -> None:
    message = Message(sender="A03", content="la sortie B est libre", tick=10)
    trigger = _decide(
        _percept(messages=(message,)), known_messages=frozenset({"A03:10"})
    )
    assert trigger.reason != "message:A03"


def test_proche_disparu() -> None:
    assert _decide(_percept(missing_kin=True)).reason == "proche_disparu"


def test_densite_critique() -> None:
    assert _decide(_percept(density=3.4)).reason == "densite_critique"


def test_premiere_decision() -> None:
    trigger = should_decide(_percept(), last_decision_tick=None, current_exit=None)
    assert trigger.reason == "premiere_decision"


def test_filet_periodique() -> None:
    trigger = _decide(_percept(tick=40), last_decision_tick=20)
    assert trigger.reason == "periodique"


def test_rien_de_nouveau_ne_coute_rien() -> None:
    trigger = _decide(_percept(tick=11), last_decision_tick=10)
    assert not trigger
    assert trigger.reason == "rien_de_nouveau"
