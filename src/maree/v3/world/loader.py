"""world.loader — charger un WorldSpec depuis un fichier YAML du dépôt.

Le moteur construit ses mondes en Python (``generate.py``) ou depuis un
dict (``worldspec.from_dict``) ; les plans réels, eux, vivent en YAML
(``configs/world/*.yaml``). Ce module fait le pont : lecture YAML,
``from_dict``, puis **validation bloquante** — un plan invalide est refusé
avec la raison, jamais corrigé en silence (monde-et-rendu §1).

``configs/world/port_aubel.yaml`` n'est pas concerné : c'est un plan v2
(format ``walkable``/``zones``), lu par ``maree.domain.geometry``, et ce
module ne le touche pas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]  # comme faiss_corpus : pas de stubs

from maree.v3.world.validate import validate_or_raise
from maree.v3.world.worldspec import WorldSpec, from_dict


def load(path: str | Path) -> WorldSpec:
    """Lit un WorldSpec YAML, le parse et le valide (refus motivé sinon)."""
    data: dict[str, Any] = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    world = from_dict(data)
    validate_or_raise(world)
    return world


__all__ = ["load"]
