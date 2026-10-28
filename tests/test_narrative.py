"""Le chroniqueur : omniscient, mais stérile.

Deux propriétés à prouver :

  1. le digest ne contient que ce que le narrateur a le droit de dire ;
  2. le validateur refuse un texte qui invente une sortie ou un chiffre.

La seconde est la vraie garde-fou : un narrateur qui hallucine ruine la
démonstration, parce qu'on ne peut plus distinguer ce qu'il a observé de
ce qu'il a supposé.
"""

from __future__ import annotations

from maree.narrative.chroniqueur import validate
from maree.narrative.digest import WorldDigest


def _digest(**kwargs) -> WorldDigest:
    base = dict(
        tick=18,
        sim_time="3:00",
        total=60,
        evacuated=12,
        remaining=48,
        density_max=2.4,
        open_exits=("A", "C"),
        closed_exits=("B",),
        belief_shares={"A": 0.5, "C": 0.2},
        unknown_share=0.3,
        consensus=0.7,
        recent_events=("t10 fumée près de la scène",),
    )
    base.update(kwargs)
    return WorldDigest(**base)


def test_prompt_contient_les_faits_du_moment() -> None:
    prompt = _digest().to_prompt()
    assert "3:00" in prompt
    assert "12" in prompt and "60" in prompt
    assert "sortie A" in prompt
    assert "Sorties fermées : B" in prompt
    assert "fumée" in prompt


def test_empreinte_stable() -> None:
    assert _digest().digest_hash() == _digest().digest_hash()
    assert _digest().digest_hash() != _digest(tick=19).digest_hash()


def test_texte_conforme_est_accepte() -> None:
    text = "À 3:00, 12 personnes sur 60 ont quitté l'esplanade. La sortie A reste ouverte."
    ok, problems = validate(text, _digest())
    assert ok, problems


def test_sortie_inventee_est_refusee() -> None:
    ok, problems = validate("La sortie D est désormais fermée.", _digest())
    assert not ok
    assert any("sortie inconnue" in p for p in problems)


def test_chiffre_invente_est_refuse() -> None:
    ok, problems = validate("42 personnes courent vers la sortie A.", _digest())
    assert not ok
    assert any("nombre absent" in p for p in problems)


def test_chiffre_invente_en_lettres_nest_pas_detecte() -> None:
    """Limite assumée : le validateur lit les chiffres, pas les mots.

    On l'écrit noir sur blanc plutôt que de prétendre à une vérification
    sémantique qu'on ne fait pas.
    """
    ok, _ = validate("Quarante-deux personnes courent vers la sortie A.", _digest())
    assert ok  # « quarante-deux » n'est pas un token numérique


def test_sortie_fermee_peut_etre_citee() -> None:
    ok, problems = validate("La sortie B est fermée.", _digest())
    assert ok, problems
