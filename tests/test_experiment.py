"""Un bras d'expérience qui choisit un scénario doit vraiment le charger.

Régression réelle (X13, 31 octobre) : le protocole écrivait

    run: {name: e2e}

en croyant mesurer le scénario du piège. Hydra ne relit jamais un groupe
après la composition : `name` arrivait dans `cfg.run`, où personne ne le
lit, et `demo` restait en place. Les quatre bras mesuraient le même monde,
une clôture d'issue en moins, et **aucun chiffre ne le signalait** : I3
valait 1,00 partout, ce qui ressemble à un résultat.

Le test vérifie les deux moitiés du contrat : le groupe est résolu, et le
bras garde le droit de surcharger une valeur du scénario.
"""

from __future__ import annotations

from omegaconf import OmegaConf

from maree.cli import _arm_run


def test_arm_run_resout_le_groupe() -> None:
    arm = OmegaConf.create({"run": {"name": "e2e"}})
    run = _arm_run(arm)
    assert run is not None
    # Ce qui distingue e2e de demo, et que personne ne pouvait voir avant.
    assert run["close_exit"] == "A"
    assert run["close_tick"] == 14
    assert run["smoke_tick"] == 6
    assert run["max_ticks"] == 90


def test_arm_run_surcharge_le_scenario() -> None:
    arm = OmegaConf.create({"run": {"name": "demo", "close_exit": "B", "close_tick": 30}})
    run = _arm_run(arm)
    assert run is not None
    assert run["close_exit"] == "B"
    assert run["close_tick"] == 30
    # Le reste vient bien de demo.
    assert run["smoke_tick"] == 10


def test_arm_run_sans_scenario_ne_touche_rien() -> None:
    """`run: {mode: async}` reste un simple réglage, pas une sélection."""
    arm = OmegaConf.create({"run": {"mode": "async"}})
    assert _arm_run(arm) == {"mode": "async"}


def test_arm_sans_run() -> None:
    assert _arm_run(OmegaConf.create({"population": {"total": 20}})) is None
