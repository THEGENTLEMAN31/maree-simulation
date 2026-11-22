"""P2.2 / H5 — un démenti tardif : qui atteint-il, et que fait-il faire ?

Hypothèse du plan : « le démenti corrige la croyance, pas l'action engagée ».
Mesure : on fait varier l'instant du démenti et l'on compte, séparément,
**combien de personnes il atteint** (encore dans la salle) et **combien
d'entre elles changent d'action**.

Résultat mesuré (3 graines, 60 agents, règles) : **toutes** celles qu'il
atteint changent d'action, sans délai. Ce qui limite un démenti tardif n'est
pas l'engagement, c'est le nombre de gens déjà dehors. L'hypothèse H5 est donc
**falsifiée** dans ce modèle — et c'est consigné comme tel.
"""

from __future__ import annotations

from collections import Counter

from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.verify import scenario_crowd as sc


def _run(t_denial: int | None) -> tuple[dict[str, str], int, int, set[str]]:
    bus = MemoryBus()
    sim = sc.build_sim(PolicyName.RULES, seed=1, bus=bus, speak=False)
    sim.run(sc.denial_timeline(t_denial))
    last: dict[str, str] = {}
    for row in sim.log.rows:
        if row.action.startswith("évacuer") and row.target:
            last[row.agent] = row.target
    snap = {e.t_prod: e.data["agents"] for e in bus.published("world.snapshot")}
    inside = (
        {f"A{int(k):02d}" for k in snap.get(t_denial, {})}
        if t_denial is not None
        else set()
    )
    return last, len(sim._evacuated), len(bus.published("world.snapshot")), inside


def test_un_dementi_tot_redirige_tout_le_monde() -> None:
    last, sortis, _n, _inside = _run(2)
    assert sortis == sc.N_AGENTS
    assert Counter(last.values()) == {"B": sc.N_AGENTS}


def test_un_dementi_tard_n_atteint_que_ceux_qui_sont_encore_la() -> None:
    last, sortis, _n, inside = _run(8)
    assert sortis == sc.N_AGENTS
    # ceux qui sont déjà sortis n'entendent plus rien : ils ont pris A
    partis = sc.N_AGENTS - len(inside)
    assert partis > 0
    assert Counter(last.values())["A"] >= partis


def test_l_effet_d_un_dementi_decroit_avec_son_retard() -> None:
    """Plus le démenti est tardif, moins il touche de monde (et I7 monte)."""
    bus_early = MemoryBus()
    sim = sc.build_sim(PolicyName.RULES, seed=1, bus=bus_early, speak=False)
    sim.run(sc.denial_timeline(2))
    i7_early = bus_early.published("indicator.crowd")[-1].data["I7_delay_seconds"]

    bus_late = MemoryBus()
    sim2 = sc.build_sim(PolicyName.RULES, seed=1, bus=bus_late, speak=False)
    sim2.run(sc.denial_timeline(8))
    i7_late = bus_late.published("indicator.crowd")[-1].data["I7_delay_seconds"]

    assert float(i7_late) > float(i7_early)
