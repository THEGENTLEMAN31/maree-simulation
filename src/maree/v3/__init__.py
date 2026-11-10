"""MARÉE v3 — plan de conception.

v3 change de mission par rapport à la v2 : simuler des individus qui se
comportent comme des êtres humains en évacuation, et *montrer* que deux
agents du même archétype divergent à cause de leur mémoire personnelle.

La v3 ne réutilise pas la v2 : elle en tire les leçons (ce qu'on veut, ce
qu'on ne veut pas). Voir `docs/v3/README.md` et `docs/v3/decisions.md`.

Ce module est le squelette livré par la semaine 1 de la feuille de route.
Les sous-paquets (`core`, `world`, `sim`, `agents`, `knowledge`,
`storage`, `api`, `verify`) sont les emplacements des couches définies par
`docs/v3/architecture.md` §3.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]