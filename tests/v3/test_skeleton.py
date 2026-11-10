"""Squelette v3 (semaine 1) : le paquet s'assemble et s'importe sans effet.

Ce test verrouille la structure posée par le roadmap : les huit couches
sont présentes, chacune a une responsabilité documentée, et l'assemblage
(`bootstrap.assemble`) les expose toutes sans trou silencieux.
"""

from __future__ import annotations

import importlib

import pytest

from maree import v3
from maree.v3 import bootstrap

#: Les huit couches définies par docs/v3/architecture.md §3.
EXPECTED_SUBSYSTEMS = {
    "core",
    "world",
    "sim",
    "agents",
    "knowledge",
    "storage",
    "api",
    "verify",
}


def test_version_declaree() -> None:
    assert v3.__version__ == "0.1.0"
    assert v3.__version__ == bootstrap.assemble().version


def test_chaque_couche_est_importable_et_documentee() -> None:
    imported = {
        name: importlib.import_module(f"maree.v3.{name}")
        for name in EXPECTED_SUBSYSTEMS
    }
    for name, module in imported.items():
        # chaque couche porte sa responsabilité (docs d'architecture, pas de code mort)
        assert getattr(module, "RESPONSIBILITY", "").strip(), f"{name} sans responsabilité"


def test_assemble_expose_toutes_les_couches() -> None:
    rt = bootstrap.assemble()
    assert set(rt.responsibilities) == EXPECTED_SUBSYSTEMS
    # l'ordre suit la chaîne de dépendances déclarée
    assert list(rt.responsibilities) == list(bootstrap._SUBSYSTEMS)


def test_toutes_les_couches_declarees_sont_importables() -> None:
    """Une couche annoncee par assemble() doit être réellement présente."""
    rt = bootstrap.assemble()
    for name in rt.responsibilities:
        importlib.import_module(f"maree.v3.{name}")


def test_pas_de_ruche_silencieuse() -> None:
    """Une couche absente du squelette fait échouer l'assemblage (pas de trou)."""
    original = dict(bootstrap._MODULES)
    dropped = original.pop("verify")
    bootstrap._MODULES.pop("verify")
    try:
        with pytest.raises(ImportError):
            bootstrap.assemble()
    finally:
        bootstrap._MODULES["verify"] = dropped