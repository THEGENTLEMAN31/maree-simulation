"""P1 — le monde n'est pas figé : des configurations → des bâtiments valides.

« Des bâtiments différents (étages, sorties) » : chaque preset génère un
WorldSpec qui passe le validateur, et les bâtiments diffèrent réellement
(nb de sorties, nb d'étages).
"""

from __future__ import annotations

from maree.v3.world import generate
from maree.v3.world.validate import validate


def test_chaque_preset_generé_valide() -> None:
    for name in generate.PRESETS:
        world = generate.build(name)
        assert validate(world) == [], f"{name} invalide: {validate(world)}"


def test_les_batiments_differrent() -> None:
    h1 = generate.build("hall_1")
    h3 = generate.build("hall_3")
    t2 = generate.build("two_floor")
    # nb de sorties
    def nb_exits(world):
        return sum(len(lv.exits) for lv in world.levels)
    assert nb_exits(h1) == 1
    assert nb_exits(h3) == 3
    assert nb_exits(t2) == 2
    # étages
    assert len(h1.levels) == 1 and len(h3.levels) == 1
    assert len(t2.levels) == 2
    # deux étages reliés
    assert len(t2.vertical) == 1


def test_hall_config_personnalisable() -> None:
    spec = generate.hall_config(
        exits=(generate.ExitSpec("A", "bottom", 30.0, 5.0),
               generate.ExitSpec("B", "left", 20.0, 3.0)),
    )
    from maree.v3.world.worldspec import from_dict
    w = from_dict(spec)
    assert validate(w) == []
    labels = {e.id for lv in w.levels for e in lv.exits}
    assert labels == {"A", "B"}