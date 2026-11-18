"""E2/E1 — le runner de campagne : multi-graines, agrégats, déterminisme.

- `rules` fait 0 appel LLM ; `llm` (stub) fait des appels et décide ;
- le coût se lit **par décision** (C4) : `llm_attempted` compte les appels
  tentés, `llm_ok` les réussis, les jetons la somme des traces ;
- une même graine + même config ⇒ mêmes indicateurs (déterminisme) ;
- `aggregate` groupe par config et rend la dispersion entre graines.
"""

from __future__ import annotations

from maree.v3.adapters.chat_stub import StubChat
from maree.v3.agents.catalog import register_provider
from maree.v3.core.ports import PolicyName
from maree.v3.verify.campaign import CampConfig, aggregate, run_once
from maree.v3.world.generate import build


def _seed_stub() -> None:
    register_provider(
        "llamacpp", StubChat(lambda _r: '{"action": "evacuer", "cible": "A", "confiance": 0.8}')
    )


def test_rules_ne_fait_aucun_appel() -> None:
    world = build("hall_3")
    r = run_once(world, CampConfig("rules", policy=PolicyName.RULES), seed=1, run_id_prefix="t")
    assert r.llm_attempted == 0
    assert r.llm_ok == 0
    assert r.tokens == 0
    assert r.decisions >= 1
    assert r.indicators["I1_consensus"] > 0.0     # les I1–I7 sont calculés


def test_llm_stub_appelle_et_decide() -> None:
    _seed_stub()
    world = build("hall_3")
    cfg = CampConfig("llm_big", policy=PolicyName.LLM, llm_alias="decision")
    r = run_once(world, cfg, seed=1, run_id_prefix="t")
    assert r.llm_attempted >= 1
    assert r.llm_ok == r.llm_attempted            # un stub réussit toujours
    assert r.tokens > 0
    assert r.replis == 0
    assert r.config == "llm_big"


def test_le_cout_se_lit_par_decision_et_pas_par_agent() -> None:
    """Un agent qui reconsidère dix fois compte dix appels, pas un (C4)."""
    _seed_stub()
    world = build("hall_3")
    cfg = CampConfig("llm_big", policy=PolicyName.LLM, llm_alias="decision")
    r = run_once(world, cfg, seed=1, run_id_prefix="t")
    # 6 agents mais plusieurs moments de reconsidération : les appels suivent
    # les décisions, ils ne sont pas plafonnés au nombre d'agents.
    assert r.llm_attempted > 6
    assert r.llm_attempted <= r.decisions


def test_determinisme_meme_graine() -> None:
    _seed_stub()
    world = build("hall_3")
    cfg = CampConfig("llm_big", policy=PolicyName.LLM, llm_alias="decision")
    a = run_once(world, cfg, seed=3, run_id_prefix="d")
    b = run_once(world, cfg, seed=3, run_id_prefix="d")
    # comparer les champs déterministes (exclure les temps muraux)
    skip = {"wall_s", "wall_llm_s", "wall_physics_s"}
    det_a = {k: v for k, v in a.as_dict().items() if k not in skip}
    det_b = {k: v for k, v in b.as_dict().items() if k not in skip}
    assert det_a == det_b
    # graine différente => on laisse varier (pas d'appariement)
    c = run_once(world, cfg, seed=4, run_id_prefix="d")
    assert c.seed == 4


def test_aggregation_par_config_et_dispersion() -> None:
    _seed_stub()
    world = build("hall_3")
    rows = [
        run_once(world, CampConfig("rules", policy=PolicyName.RULES), seed, run_id_prefix="a")
        for seed in (1, 2, 3)
    ] + [
        run_once(world, CampConfig("llm_big", policy=PolicyName.LLM, llm_alias="decision"), seed, run_id_prefix="a")
        for seed in (1, 2, 3)
    ]
    agg = aggregate(rows)
    assert set(agg) == {"rules", "llm_big"}
    assert agg["rules"]["n_runs"] == 3 and agg["llm_big"]["n_runs"] == 3
    assert agg["rules"]["llm_attempted_med"] == 0.0
    assert agg["rules"]["tokens_med"] == 0.0
    lo, hi = agg["llm_big"]["llm_attempted_span"]
    assert lo <= hi and hi >= 1
    # les indicateurs de foule sont agrégés aussi (médiane par config)
    assert "I7_med" in agg["llm_big"]
    assert agg["rules"]["I3_med"] <= 1.0
