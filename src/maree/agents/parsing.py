"""Analyse de la sortie d'un modèle.

Isolé du graphe LangGraph pour deux raisons :
  * testable sans installer LangGraph ;
  * le rejeu (E3) doit pouvoir re-parser une sortie brute sans reconstruire
    tout l'édifice de décision.
"""

from __future__ import annotations

import json
import re
from typing import Any

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def parse_decision(text: str) -> dict[str, Any] | None:
    """Extrait le premier objet JSON d'une sortie, même entourée de prose.

    Un petit modèle bavard reste exploitable : on ne perd pas une décision
    pour un préambule. Si rien n'est parsable, on renvoie None et l'appelant
    replie sur les règles (décision 7) — le repli est journalisé.
    """
    if not text:
        return None
    match = _JSON_OBJ.search(text)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None
