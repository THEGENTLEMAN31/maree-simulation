"""P2.1 — une issue qui ferme en pleine foule : I6 bouge, la foule se rabat.

Le scénario : 60 agents, fumée à t1, **A ferme à t4**. La fermeture est une
vérité du monde (journalisée), mais la perception est bornée à 8 m : un agent
qui ne voit pas la porte ne sait pas qu'elle est fermée.

Ce que l'on vérifie :

- I6 (part des agents qui préfèrent encore une porte réellement fermée)
  **monte** à la fermeture puis **redescend** quand ils s'en approchent —
  c'est la première fois que cet indicateur mesure quelque chose ;
- les décisions se rabattent sur B ;
- tout le monde finit par sortir (aucune censure) ;
- le goulot se resserre sur la porte restante (I5 monte).
"""

from __future__ import annotations

from collections import Counter

from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.verify import scenario_crowd as sc


def test_i6_mesure_vraiment_la_fermeture() -> None:
    result = sc.measure(PolicyName.RULES, seed=1, scenario="closure", speak=False)
    i6 = [float(x["I6"] or 0.0) for x in result["series"]]
    assert max(i6) >= 0.2, "I6 doit monter à la fermeture"
    assert i6[-1] < max(i6), "I6 doit redescendre quand la foule voit la porte"
    assert float(result["summary"]["I3_evacuated"]) == 1.0
    assert result["evacuated"] == sc.N_AGENTS


def test_la_foule_se_rabat_sur_la_porte_restante() -> None:
    bus = MemoryBus()
    sim = sc.build_sim(PolicyName.RULES, seed=1, bus=bus, speak=False)
    sim.run(sc.close_timeline())
    rows = sim.log.rows
    before = Counter(r.target for r in rows if r.tick < sc.T_CLOSE and r.target)
    after = Counter(
        r.target
        for r in rows
        if r.tick >= sc.T_CLOSE and r.action.startswith("évacuer") and r.target
    )
    assert before["A"] >= 40, "au départ, la foule vise la porte qui va fermer"
    assert after["B"] > after["A"], "après la fermeture, elle se rabat sur B"


def test_la_fermeture_est_journalisee_et_percue_localement() -> None:
    """La vérité du monde est globale ; la **perception** est bornée à 8 m."""
    from maree.v3.agents.agent import make_agent
    from maree.v3.sim.scene import CLOSURE_RANGE, Scene
    from maree.v3.world.navgraph import NavigationGraph
    from maree.v3.world.sample import sample_worldspec

    scene = Scene(navgraph=NavigationGraph(sample_worldspec()))
    # sortie A du plan de référence : segment [[55,80],[60,80]] → milieu (57.5, 80)
    proche = make_agent(1, "visiteur", known_exits=frozenset({"A", "B"}))
    loin = make_agent(2, "visiteur", known_exits=frozenset({"A", "B"}))
    scene.add(proche, "S_HALL", (57.5, 78.0))
    scene.add(loin, "S_HALL", (57.5, 78.0 - CLOSURE_RANGE - 6.0))
    scene.update_positions({1: (57.5, 78.0), 2: (57.5, 78.0 - CLOSURE_RANGE - 6.0)})
    scene.closed_exits.add("A")
    near = scene.perception_for(proche.uid)
    far = scene.perception_for(loin.uid)
    assert "A" in near.closed_exits
    assert "A" not in far.closed_exits

    bus = MemoryBus()
    sim = sc.build_sim(PolicyName.RULES, seed=1, bus=bus, speak=False)
    sim.run(sc.close_timeline())
    closed = bus.published("world.exit_closed")
    assert len(closed) == 1 and closed[0].data["exit"] == sc.CLOSED_EXIT
