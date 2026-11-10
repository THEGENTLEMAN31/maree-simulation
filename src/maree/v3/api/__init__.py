"""api — REST, WebSocket versionné, dossier agent, schémas.

Aucun calcul de simulation. Expose le RunStream et la fiche agent aux
fronts (Godot d'abord), via des contrats versionnés. Voir
`docs/v3/architecture.md` §3.
"""

from __future__ import annotations

RESPONSIBILITY = "REST + OpenAPI, WebSocket versionné, dossier agent, schémas"

__all__ = ["RESPONSIBILITY"]