"""C6 — la campagne macro se monte et compte ce qu'elle prétend compter.

Aucun modèle ici : un fournisseur bouchon répond « évacuer A ». Ce que l'on
vérifie est le **câblage de mesure**, pas la qualité d'un modèle :

- les deux scénarios (croyances clivées, annonce contradictoire) se jouent
  sur le monde calibré, avec la physique ;
- le coût est compté par décision (`llm_attempted`), les escalades par cause,
  et les décisions visant une porte crue bloquée sont dénombrées ;
- la cible résolue par le moteur est comptée à part ;
- l'agrégat publie médianes **et** intervalles observés ;
- le bras `regles` ne paie aucun appel, même ici.
"""

from __future__ import annotations

from maree.v3.adapters.chat_stub import StubChat
from maree.v3.agents.catalog import register_provider
from maree.v3.core.ports import PolicyName
from maree.v3.verify.campaign_crowd import (
    ARMS,
    Arm,
    aggregate,
    campaign,
    run_arm,
)


def _stub() -> None:
    text = '{"action": "evacuer", "cible": "A", "confiance": 0.9}'
    for name in ("stub", "llamacpp", "llamacpp-small"):
        register_provider(name, StubChat(lambda _r: text))


def test_les_deux_scenarios_se_jouent_et_evacuent() -> None:
    r = run_arm(Arm("regles", PolicyName.RULES), "split", seed=1)
    assert r.evacuations == 60
    assert float(r.indicators["I3_evacuated"]) == 1.0
    c = run_arm(Arm("regles", PolicyName.RULES), "contradiction", seed=1)
    assert c.evacuations == 60


def test_les_regles_ne_paient_aucun_appel_macro() -> None:
    r = run_arm(Arm("regles", PolicyName.RULES), "split", seed=1)
    assert r.llm_attempted == 0
    assert r.tokens == 0
    assert r.target_resolved == 0


def test_le_cout_et_les_escalades_sont_comptes() -> None:
    _stub()
    r = run_arm(Arm("hybride", PolicyName.HYBRID, "decision"), "contradiction", seed=1)
    assert r.llm_attempted > 0
    assert r.llm_ok <= r.llm_attempted
    assert r.tokens > 0
    # l'annonce qui contredit la croyance d'un agent est une escalade nommée
    assert r.escalations.get("information_contradictoire", 0) > 0


def test_les_decisions_vers_une_porte_crue_bloquee_sont_denombrees() -> None:
    _stub()
    # le bouchon envoie tout le monde vers A ; la moitié croit A bloquée
    r = run_arm(Arm("llm_grand", PolicyName.LLM, "decision"), "split", seed=1)
    assert r.targeted_blocked > 0
    assert 0.0 < r.part_decisions_bloquees <= 1.0


def test_l_agregat_publie_medianes_et_intervalles() -> None:
    _stub()
    runs = campaign(
        arms=(Arm("regles", PolicyName.RULES), Arm("llm_grand", PolicyName.LLM, "decision")),
        scenarios=("split",),
        seeds=(1, 2),
    )
    agg = aggregate(runs)
    assert set(agg) == {"regles|split", "llm_grand|split"}
    regles = agg["regles|split"]
    assert regles["n_runs"] == 2
    assert regles["llm_attempted_med"] == 0.0
    grand = agg["llm_grand|split"]
    assert grand["llm_attempted_med"] > 0
    assert len(grand["I5_span"]) == 2 and grand["I5_span"][0] <= grand["I5_span"][1]


def test_les_quatre_bras_sont_declares() -> None:
    assert [a.name for a in ARMS] == [
        "regles", "hybride", "llm_grand", "llm_petit", "decision_head",
    ]
    # deux tailles pour le même bras : c'est l'axe « la taille compte-t-elle ? »
    assert ARMS[2].policy is ARMS[3].policy
    assert ARMS[2].alias != ARMS[3].alias
