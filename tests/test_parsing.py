"""Analyse de la sortie du modèle.

Un petit modèle bavard ne doit pas coûter une décision. Un modèle qui
n'émet pas de JSON doit, lui, échouer proprement (repli sur les règles).
"""

from __future__ import annotations

import pytest

from maree.agents.parsing import parse_decision


def test_json_nu() -> None:
    parsed = parse_decision('{"action": "go_exit", "target": "A", "confidence": 0.8}')
    assert parsed == {"action": "go_exit", "target": "A", "confidence": 0.8}


def test_json_enrobe_de_prose() -> None:
    text = (
        "Bien sûr. Voici ma décision :\n"
        '{"action": "follow", "target": "A03", "confidence": 0.6, "reason": "il sait"}\n'
        "Voilà."
    )
    parsed = parse_decision(text)
    assert parsed is not None
    assert parsed["action"] == "follow"


def test_json_sur_plusieurs_lignes() -> None:
    text = '{\n  "action": "stay",\n  "target": null,\n  "confidence": 0.3\n}'
    assert parse_decision(text)["action"] == "stay"


@pytest.mark.parametrize("text", ["", "je ne sais pas", "{pas du json}", "[1, 2, 3]"])
def test_sorties_invalides(text: str) -> None:
    assert parse_decision(text) is None


def test_json_valide_mais_pas_un_objet() -> None:
    assert parse_decision('["a", "b"]') is None
