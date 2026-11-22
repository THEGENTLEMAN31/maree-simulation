"""P1.2 — la calibration tient-elle sur d'autres salles ?

Critère **pré-enregistré** (ADR-015, avant ces mesures) : le bras `règles`
sur une salle de la famille produit

- un pic de densité I5 ∈ [0,8 ; 1,6] pers/m²,
- un pic **après** le spawn (la foule se forme en marchant),
- et 60/60 agents sortis.

Si un seul monde sort de la bande, la campagne macro ne peut pas être
généralisée et il faut recalibrer — pas relâcher le critère.
"""

from __future__ import annotations

import pytest

from maree.v3.core.ports import PolicyName
from maree.v3.verify import scenario_crowd as sc
from maree.v3.verify import worlds

BAND = (0.8, 1.6)


def test_la_famille_de_mondes_est_valide_et_reproductible() -> None:
    for seed in (1, 2, 3):
        spec = worlds.draw(seed)
        assert 20.0 <= spec.width <= 24.0
        assert 14.0 <= spec.height <= 18.0
        assert 1.1 <= spec.exit_width <= 1.3
        assert spec.center_a < spec.center_b
        # déterministe à graine égale
        assert worlds.draw(seed) == spec
        # le WorldSpec se construit et se valide (Simulation.build valide)
        w = worlds.build(spec)
        assert w.id == f"crowd_w{seed}"


def test_deux_mondes_differents_ne_sont_pas_le_meme_monde() -> None:
    a, b = worlds.draw(1), worlds.draw(2)
    assert (a.width, a.height, a.exit_width) != (b.width, b.height, b.exit_width)


@pytest.mark.parametrize("seed", [1, 2])
def test_chaque_monde_produit_un_goulot_dans_la_bande(seed: int) -> None:
    world = worlds.build(worlds.draw(seed))
    result = sc.measure(PolicyName.RULES, seed=seed, world=world, speak=False)
    summary = result["summary"]
    peak = float(summary["I5_max_density"])
    assert BAND[0] <= peak <= BAND[1], f"monde {seed} : I5 pic {peak}"
    assert result["peak_tick"] >= 3          # le goulot se forme en marchant
    assert result["evacuated"] == sc.N_AGENTS
    assert float(summary["I3_evacuated"]) == 1.0
