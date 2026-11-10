"""sim — physique, orchestration, dangers, transferts.

Aucune cognition. Exécute le monde : moteur micro par étage (JuPedSim),
moteur réseau, champ de dangers, coordinateur d'étages (v3.1).
Voir `docs/v3/architecture.md` §3.
"""

from __future__ import annotations

RESPONSIBILITY = "physique, orchestration, dangers, transferts d'étages"

__all__ = ["RESPONSIBILITY"]