"""Fixtures partagées.

Le plan est chargé depuis le **vrai** YAML du monde : un test qui
utiliserait un plan bidon ne prouverait rien sur Port-Aubel.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from maree.domain.geometry import Plan

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def world_dict() -> dict:
    return yaml.safe_load((ROOT / "configs" / "world" / "port_aubel.yaml").read_text("utf-8"))


@pytest.fixture(scope="session")
def plan(world_dict: dict) -> Plan:
    return Plan.from_dict(world_dict)
