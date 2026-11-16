"""E2/E1 — le runner de campagne : multi-graines, agrégats, déterminisme.

- `rules` fait 0 appel LLM ; `llm` (stub) fait des appels et décide ;
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
    assert r.llm_calls == 0
    assert r.decisions >= 1


def test_llm_stub_appelle_et_decide() -> None:
    _seed_stub()
    world = build("hall_3")
    cfg = CampConfig("llm_big", policy=PolicyName.LLM, llm_alias="decision")
    r = run_once(world, cfg, seed=1, run_id_prefix="t")
    assert r.llm_calls >= 1
    assert r.replis == 0
    assert r.config == "llm_big"


def test_determinisme_meme_graine() -> None:
    _seed_stub()
    world = build("hall_3")
    cfg = CampConfig("llm_big", policy=PolicyName.LLM, llm_alias="decision")
    a = run_once(world, cfg, seed=3, run_id_prefix="d")
    b = run_once(world, cfg, seed=3, run_id_prefix="d")
    # comparer les champs déterministes (exclure la mesure wall_s)
    det_a = {k: v for k, v in a.as_dict().items() if k != "wall_s"}
    det_b = {k: v for k, v in b.as_dict().items() if k != "wall_s"}
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
    assert agg["rules"]["llm_calls_med"] == 0.0
    lo, hi = agg["llm_big"]["llm_calls_span"]
    assert lo <= hi and hi >= 1