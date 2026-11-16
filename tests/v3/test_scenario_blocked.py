"""Le scénario « sortie bloquée » est un discriminant *de méthode*.

Rien ici n'appelle un vrai modèle : on prouve que le banc de mesure peut
séparer deux comportements — et que 0,50 est le plafond d'une politique de
position, pas un hasard. Les campagnes réelles rejouent ce même scénario.

- règles (qui ignorent une sortie crue bloquée)            → 1,00
- politique qui répond « toujours A »                       → 0,50
- politique qui lit la mémoire et évite la sortie bloquée    → 1,00
"""

from __future__ import annotations

import json

from maree.v3.adapters.chat_stub import StubChat
from maree.v3.agents.catalog import register_provider
from maree.v3.core.ports import LLMRequest, PolicyName
from maree.v3.verify.scenario_blocked import BLOCKED, run


def _always_a(_request: LLMRequest) -> str:
    return json.dumps(
        {"action": "evacuer", "cible": "A", "confiance": 0.9}, ensure_ascii=False
    )


def _reads_memory(request: LLMRequest) -> str:
    """Un lecteur minimal : la première sortie connue qui n'est pas un danger."""
    payload = json.loads(request.messages[-1].content)
    blocked = {entry[0] for entry in payload["dangers"]}
    known = [entry[0] for entry in payload["sorties_connues"]]
    target = next((label for label in known if label not in blocked), None)
    return json.dumps(
        {"action": "evacuer", "cible": target, "confiance": 0.8}, ensure_ascii=False
    )


def test_les_regles_evitent_la_sortie_crue_bloquee() -> None:
    result = run(seed=1, policy=PolicyName.RULES)
    assert result.accuracy == 1.0
    assert result.choices == {"A01": "B", "A02": "B", "A03": "A", "A04": "A"}


def test_une_politique_de_position_plafonne_a_un_demi() -> None:
    # « toujours A » réussit aux agents qui croient B bloquée, échoue aux autres.
    register_provider("llamacpp", StubChat(_always_a))
    result = run(seed=1, policy=PolicyName.LLM, alias="decision")
    assert result.accuracy == 0.5
    assert set(result.choices.values()) == {"A"}
    # et le plafond vient bien du scénario, pas du moteur : A est bloquée
    # pour deux agents sur quatre.
    assert sorted(BLOCKED.values()) == ["A", "A", "B", "B"]


def test_lire_la_memoire_suffit_a_reussir() -> None:
    register_provider("llamacpp", StubChat(_reads_memory))
    result = run(seed=1, policy=PolicyName.LLM, alias="decision")
    assert result.accuracy == 1.0
    assert result.choices == {"A01": "B", "A02": "B", "A03": "A", "A04": "A"}


def test_le_scenario_ne_dépend_pas_de_la_graine_du_monde() -> None:
    # monde fixe, aucune position dans le prompt : la graine ne doit rien changer.
    register_provider("llamacpp", StubChat(_reads_memory))
    scores = {
        run(seed=seed, policy=PolicyName.LLM, alias="decision").accuracy
        for seed in (1, 2, 3)
    }
    assert scores == {1.0}
