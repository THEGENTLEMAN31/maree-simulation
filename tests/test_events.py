"""Enveloppe et schémas d'événements (F4).

Le journal est la source de vérité : une ligne illisible n'est pas un
détail, c'est un trou dans la preuve. On teste donc deux choses :

    * `validate()` attrape les défauts de **forme** (champ manquant) et de
      **temps** (`t_prod > t_trait`, C3) ;
    * `SCHEMAS` ne référence que des types qui existent vraiment — une
      faute de frappe y créerait une règle morte, jamais appliquée.
"""

from __future__ import annotations

from maree.domain.events import SCHEMAS, Event, EventType, validate


def _event(type_: EventType, data: dict, *, t_prod: int = 0, t_trait: int = 0, seq: int = 1):
    return Event(
        seq=seq,
        run_id="run_test",
        type=type_,
        t_prod=t_prod,
        t_trait=t_trait,
        t_real=0.0,
        data=data,
    )


def test_un_evenement_conforme_ne_produit_aucun_probleme() -> None:
    event = _event(EventType.ANNOUNCEMENT, {"text": "Évacuation."})
    assert validate(event) == []


def test_un_champ_manquant_est_signale() -> None:
    problems = validate(_event(EventType.ANNOUNCEMENT, {}))
    assert problems and "text" in problems[0]


def test_un_instantane_sans_agents_est_refuse() -> None:
    """Le client lit `agents` : sans lui, la trame est inutilisable."""
    problems = validate(_event(EventType.SNAPSHOT, {"tick": 3}))
    assert any("agents" in p for p in problems)


def test_un_evenement_produit_apres_son_traitement_est_refuse() -> None:
    """C3 — `t_prod > t_trait` n'a aucun sens et masquerait un décalage."""
    event = _event(EventType.ANNOUNCEMENT, {"text": "x"}, t_prod=5, t_trait=3)
    assert any("t_prod" in p for p in validate(event))


def test_un_seq_non_positif_est_refuse() -> None:
    event = _event(EventType.ANNOUNCEMENT, {"text": "x"}, seq=0)
    assert any("seq" in p for p in validate(event))


def test_les_schemas_ne_referencent_que_des_types_reels() -> None:
    for type_ in SCHEMAS:
        assert isinstance(type_, EventType)


def test_les_types_critiques_ont_un_schema() -> None:
    """Sans schéma, un type passerait en quarantaine sans qu'on le sache."""
    for type_ in (
        EventType.DECISION,
        EventType.EVACUATED,
        EventType.INDICATORS,
        EventType.SNAPSHOT,
        EventType.INJECTION,
        EventType.TEMPORAL_VIOLATION,
        EventType.INVALID,
    ):
        assert type_ in SCHEMAS
