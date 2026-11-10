"""bootstrap — point d'assemblage unique de la v3.

La règle (docs/v3/architecture.md §4) : le domaine et le moteur n'importent
aucun adaptateur concret. Tout le câblage passe par ce fichier, comme la
CLI v2. En semaine 1, le point d'assemblage existe et connaît les couches ;
les adaptateurs concrets (ports -> implémentations) seront branchés ici
semaine après semaine.

Rien ici n'est une configuration morte : chaque entrée est lue par
`assemble()` et exposée au runtime. Le contrat d'abstraction (ports) vit
dans `core/` et sera rempli par la suite.
"""

from __future__ import annotations

from dataclasses import dataclass

import maree.v3 as _v3
from maree.v3 import agents as _agents
from maree.v3 import api as _api
from maree.v3 import core as _core
from maree.v3 import knowledge as _knowledge
from maree.v3 import sim as _sim
from maree.v3 import storage as _storage
from maree.v3 import verify as _verify
from maree.v3 import world as _world

#: Nom canonique des couches, dans l'ordre où elles s'assemblent.
#: (ordre de dépendance : core -> monde -> moteur -> agents/API …)
_SUBSYSTEMS = (
    "core",
    "world",
    "sim",
    "agents",
    "knowledge",
    "storage",
    "api",
    "verify",
)

_MODULES = {
    "core": _core,
    "world": _world,
    "sim": _sim,
    "agents": _agents,
    "knowledge": _knowledge,
    "storage": _storage,
    "api": _api,
    "verify": _verify,
}


@dataclass(frozen=True, slots=True)
class Runtime:
    """L'application assemblée.

    Porte la version et la table des responsabilités de chaque couche.
    Les adaptateurs concrets seront greffés ici au fil des semaines sans
    que les couches le voient.
    """

    version: str
    responsibilities: dict[str, str]


def assemble() -> Runtime:
    """Construit le runtime de la v3 à partir du squelette des couches.

    En semaine 1, expose l'inventaire des couches (squelette + CI). Une
    couche n'apparaît ici que si elle est importable ; toute couche absente
    de ``_SUBSYSTEMS`` ferait échouer l'assemblage (pas de trou silencieux).
    """
    missing = [name for name in _SUBSYSTEMS if name not in _MODULES]
    if missing:
        raise ImportError(f"Sous-paquets v3 manquants : {', '.join(missing)}")

    responsibilities = {
        name: _MODULES[name].RESPONSIBILITY for name in _SUBSYSTEMS
    }
    return Runtime(version=_v3.__version__, responsibilities=responsibilities)


__all__ = ["Runtime", "assemble"]