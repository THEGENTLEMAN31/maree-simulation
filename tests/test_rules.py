"""Agents à règles — le bras de comparaison X4.

Ces tests fixent le contrat : mêmes percepts, mêmes intentions. C'est ce
qui rend la comparaison avec le bras LLM interprétable.
"""

from __future__ import annotations

from maree.agents.rules import rules_decide
from maree.agents.triggers import Percept
from maree.domain.geometry import Plan
from maree.domain.intentions import IntentionKind


def _percept(**kwargs) -> Percept:
    # Par défaut : le danger est déjà là (fumée visible). Les tests qui
    # portent sur le choix de sortie se placent après le signal ; ceux qui
    # portent sur l'attente le désactivent explicitement.
    base = dict(
        tick=10,
        position=(10.0, 10.0),
        zone="Z3",
        smoke_visible=True,
        smoke_intensity=0.5,
        exits_open=frozenset({"A", "B", "C"}),
    )
    base.update(kwargs)
    return Percept(**base)


def test_personne_ne_fuit_sans_signal(plan: Plan) -> None:
    """Sans fumée, sans annonce, sans message : on reste.

    C'est la phase « avant » du scénario. Sans elle, les 60 agents
    quittaient l'esplanade au tick 1 et la fumée de t10 ne causait plus
    rien — elle commentait une évacuation déjà finie.
    """
    calme = _percept(smoke_visible=False, smoke_intensity=0.0)
    for profile in ("visiteur", "habitue", "securite", "famille"):
        intention = rules_decide(calme, plan, profile=profile)
        assert intention.kind is IntentionKind.STAY, profile


def test_une_annonce_suffit_a_declencher(plan: Plan) -> None:
    intention = rules_decide(
        _percept(smoke_visible=False, smoke_intensity=0.0, announcement="Évacuation."),
        plan,
        profile="visiteur",
    )
    assert intention.kind is IntentionKind.GO_EXIT


def test_visiteur_ne_connait_que_A(plan: Plan) -> None:
    intention = rules_decide(_percept(), plan, profile="visiteur")
    assert intention.kind is IntentionKind.GO_EXIT
    assert intention.target == "A"


def test_habitué_peut_choisir_la_ruelle(plan: Plan) -> None:
    """Près de B, l'habitué doit préférer B malgré son étroitesse."""
    intention = rules_decide(_percept(position=(53.0, 16.0)), plan, profile="habitue")
    assert intention.kind is IntentionKind.GO_EXIT
    assert intention.target == "B"


def test_vendeur_garde_son_stand_sans_danger(plan: Plan) -> None:
    intention = rules_decide(
        _percept(smoke_visible=False, smoke_intensity=0.0), plan, profile="vendeur"
    )
    assert intention.kind is IntentionKind.STAY


def test_vendeur_part_quand_la_fumee_est_visible(plan: Plan) -> None:
    intention = rules_decide(
        _percept(smoke_visible=True, smoke_intensity=0.7), plan, profile="vendeur"
    )
    assert intention.kind is IntentionKind.GO_EXIT


def test_famille_cherche_son_proche_avant_de_fuir(plan: Plan) -> None:
    intention = rules_decide(_percept(missing_kin=True), plan, profile="famille")
    assert intention.kind is IntentionKind.SEARCH


def test_securite_guide_quand_il_y_a_du_monde(plan: Plan) -> None:
    intention = rules_decide(_percept(nearby=("A01", "A02")), plan, profile="securite")
    assert intention.kind is IntentionKind.GUIDE
    assert intention.target in {"A", "B", "C"}


def test_sortie_fermee_force_le_repli(plan: Plan) -> None:
    """Le visiteur ne connaît que A ; si A ferme, il ne sait plus où aller."""
    intention = rules_decide(
        _percept(exits_open=frozenset({"B", "C"})), plan, profile="visiteur"
    )
    assert intention.kind is IntentionKind.STAY


def test_habitué_survit_a_la_fermeture_de_A(plan: Plan) -> None:
    intention = rules_decide(
        _percept(position=(53.0, 16.0), exits_open=frozenset({"B", "C"})),
        plan,
        profile="habitue",
    )
    assert intention.kind is IntentionKind.GO_EXIT
    assert intention.target == "B"


def test_les_regles_sont_deterministes(plan: Plan) -> None:
    percept = _percept(position=(20.0, 20.0), density=1.2)
    first = rules_decide(percept, plan, profile="visiteur")
    second = rules_decide(percept, plan, profile="visiteur")
    assert first == second


def test_la_densite_devant_une_sortie_ecarte_le_choix(plan: Plan) -> None:
    """Deux sorties presque équidistantes : c'est la file d'attente qui tranche.

    La densité prise en compte est celle DEVANT la sortie, pas celle de
    l'agent : sinon le terme serait constant et ne changerait rien.
    """
    calme = rules_decide(
        _percept(
            position=(22.0, 20.0),
            exit_density={"A": 0.1, "B": 0.1, "C": 0.1},
        ),
        plan,
        profile="habitue",
    )
    sature = rules_decide(
        _percept(
            position=(22.0, 20.0),
            exit_density={"A": 3.5, "B": 0.1, "C": 0.1},
        ),
        plan,
        profile="habitue",
    )
    assert calme.target == "A"
    assert sature.target == "C"
