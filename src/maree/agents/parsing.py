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


#: O2 — la « posture d'assistant prudent ».
#:
#: Un modèle aligné sur des consignes de sécurité répond parfois comme un
#: assistant : il refuse de choisir, rappelle les consignes, recommande le
#: calme ou renvoie à « la sortie la plus proche » sans en nommer une.
#: Ce n'est ni une sortie de rôle (il reste poli) ni une réponse
#: inexploitable (elle se parse) : c'est une dérive distincte, que le
#: cahier des charges demande de diagnostiquer.
#:
#: Détection **lexicale**, donc faillible : elle est documentée comme telle.
#: Elle sert à compter un phénomène, pas à juger une décision.
_POSTURE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bje ne (peux|suis) (pas|en mesure)\b", re.I), "refus"),
    (
        re.compile(r"\b(en tant qu|je suis)\b[^.]{0,20}\b(ia|assistant|mod[èe]le)\b", re.I),
        "méta",
    ),
    (
        re.compile(r"\b(restez|gardez)\b[^.]{0,24}\bcalme", re.I),
        "conseil de calme",
    ),
    (
        re.compile(r"\b(il est|il serait) (important|essentiel|primordial)\b", re.I),
        "conseil générique",
    ),
    (
        re.compile(r"\bsuivez\b[^.]{0,24}\b(consignes|instructions)\b", re.I),
        "renvoi aux consignes",
    ),
    (
        re.compile(r"\b(la|une) sortie la plus proche\b", re.I),
        "cible générique",
    ),
)


def detect_posture(text: str) -> str | None:
    """Renvoie la tournure qui trahit une posture d'assistant, sinon None."""
    if not text:
        return None
    for pattern, label in _POSTURE_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"{label} : « {match.group(0)[:60]} »"
    return None


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
