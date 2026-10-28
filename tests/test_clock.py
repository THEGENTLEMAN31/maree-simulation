"""Les trois horloges."""

from __future__ import annotations

import pytest

from maree.domain.clock import Clocks, SimClock


def test_steps_per_tick_est_le_rapport_cognition_physique() -> None:
    clocks = Clocks(physics_dt=0.05, cognition_s=10.0)
    assert clocks.steps_per_tick == 200


def test_steps_per_tick_jamais_nul() -> None:
    assert Clocks(physics_dt=20.0, cognition_s=10.0).steps_per_tick == 1


def test_aucune_horloge_systeme() -> None:
    clock = SimClock(tick=45, clocks=Clocks(cognition_s=10.0))
    assert clock.seconds == 450.0
    assert clock.fmt() == "7:30"
    assert clock.advance().tick == 46


def test_conversions_aller_retour() -> None:
    clocks = Clocks(cognition_s=10.0)
    assert clocks.seconds_to_tick(95.0) == 9
    assert clocks.tick_to_seconds(9) == pytest.approx(90.0)
