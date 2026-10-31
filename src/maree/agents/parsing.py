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


#: Le protocole du tier « small » (A5/E5) : une **politique explicite**.
#:
#: Trois formats ont été essayés sur `qwen3-0-6b`, et deux ont échoué
#: pour la même raison : le modèle ne raisonne pas, il suit la forme.
#:
#:   JSON ouvert      → `search`, confiance 0, prompt recopié (55/55)
#:   liste de mots    → toujours la **première option**, quel que soit le
#:                      contexte (`RESTER` en tête → RESTER même avec de
#:                      la fumée ; `SORTIR A` en tête → SORTIR A sans
#:                      fumée, donc évacuation au tick 3)
#:   question binaire → instable : dépend du prompt système, répond OUI
#:                      par défaut selon la formulation
#:
#: Ce qui marche, et qui est mesuré (6 essais par cas, persona réelle) :
#: une **règle écrite noir sur blanc** avec des drapeaux oui/non.
#: `calme` → RESTER 6/6 ; `fumée` → SORTIR 6/6 ; `annonce` → 2/6 (le petit
#: modèle ignore à moitié les annonces, c'est consigné comme limite).
#:
#: Conséquence à assumer : le tier « small » **applique** une politique, le
#: tier « big » la **juge**. Ce n'est pas la même tâche, et c'est dit dans
#: `docs/resultats/vague4.md`.
_SORTIR = re.compile(r"\bsortir\b|\bpartir\b|\bevacuer\b|\bévacuer\b", re.I)
_RESTER = re.compile(
    r"\brester\b|\breste\b|\battendre\b|\bpas\b[^.]*\b(sortir|partir)\b",
    re.I,
)


def parse_choice(text: str, *, known_exits: list[str]) -> dict[str, Any] | None:
    """Lit la réponse du tier « small » : `SORTIR` ou `RESTER`.

    `RESTER` → `stay`. `SORTIR` → `go_exit` vers la première sortie connue
    et ouverte ; s'il n'en connaît aucune, `search` — vouloir partir sans
    savoir par où, c'est chercher, pas rester.

    Renvoie `None` si la réponse ne dit ni l'un ni l'autre : c'est un
    incident nommé (A4), pas une intention inventée.
    """
    if not text:
        return None
    cleaned = text.replace("*", " ").replace("_", " ").strip()
    # `RESTER` d'abord : « je ne veux pas sortir » contient « sortir ».
    if _RESTER.search(cleaned):
        return {
            "action": "stay",
            "target": None,
            "confidence": 0.6,
            "reason": cleaned[:140],
        }
    if _SORTIR.search(cleaned):
        if known_exits:
            return {
                "action": "go_exit",
                "target": known_exits[0],
                "confidence": 0.6,
                "reason": cleaned[:140],
            }
        return {
            "action": "search",
            "target": None,
            "confidence": 0.6,
            "reason": cleaned[:140],
        }
    return None
