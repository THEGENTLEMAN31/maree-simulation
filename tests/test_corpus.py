"""Intégrité du corpus RAG — les passages doivent être *atteignables*.

Le corpus est du contenu : un passage mal daté ou tagué d'un profil
inexistant ne provoque aucune erreur, il est simplement invisible. C'est
arrivé deux fois, silencieusement :

  * les 43 annonces étaient datées t120–t590 alors qu'un run dure 90
    ticks : la collection la plus utile au scénario n'était jamais lue ;
  * 16 passages étaient tagués « amis », profil absent du moteur.

Ces tests transforment ces oublis en échecs.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml

from maree.adapters.retrieval.faiss_corpus import load_corpus
from maree.agents.profiles import PROFILES

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "world_corpus"

#: Un passage daté au-delà du plus long scénario n'est jamais lu.
MAX_TICKS = int(
    yaml.safe_load((ROOT / "configs" / "run" / "e2e.yaml").read_text(encoding="utf-8"))[
        "max_ticks"
    ]
)


@pytest.fixture(scope="module")
def passages():
    return load_corpus(CORPUS)


def test_le_corpus_est_present(passages) -> None:
    assert len(passages) >= 200
    assert {p.collection for p in passages} == {
        "annonces",
        "consignes_securite",
        "plan_signalétique",
        "savoir_profils",
        "souvenirs_editions",
    }


def test_aucun_profil_inconnu(passages) -> None:
    """Un profil absent du moteur rend le passage illisible pour tout le monde."""
    inconnus = {p for x in passages for p in x.allowed_profiles} - set(PROFILES)
    assert not inconnus, f"profils inconnus : {sorted(inconnus)}"


def test_aucun_passage_mort(passages) -> None:
    morts = [p.doc_id for p in passages if not set(p.allowed_profiles) & set(PROFILES)]
    assert not morts


def test_aucun_passage_date_apres_la_fin_du_run(passages) -> None:
    tardifs = sorted({p.available_tick for p in passages if p.available_tick > MAX_TICKS})
    assert not tardifs, f"ticks au-delà de max_ticks={MAX_TICKS} : {tardifs}"


def test_les_collections_declarees_existent(passages) -> None:
    """Une collection mal orthographiée ne filtre rien : elle rend le vide.

    `plan_signaletique` (sans accent) ne correspondait à aucun passage du
    corpus (`plan_signalétique`) : la sécurité et les habitués — les deux
    profils qui la déclarent — ne pouvaient pas lire 44 passages du plan,
    et rien ne le signalait. Un nom de collection est une clé, pas une
    étiquette : il se vérifie.
    """
    collections = {p.collection for p in passages}
    declarees = {c for profil in PROFILES.values() for c in profil.rag_collections}
    assert declarees <= collections, f"collections inconnues : {sorted(declarees - collections)}"


def test_chaque_profil_lit_au_moins_un_passage(passages) -> None:
    """Le filtre croise `rag_collections` **et** `allowed_profiles`.

    Déclarer une collection que le corpus n'ouvre pas au profil donne zéro
    passage, silencieusement : le visiteur déclarait `consignes_securite`,
    où aucun passage ne l'autorise. Il ne retrievait jamais rien.
    """
    for profil in PROFILES.values():
        # au dernier tick du scénario : avant l'annonce, un profil n'a
        # légitimement rien à lire (les annonces s'ouvrent à t10).
        lisibles = [
            p
            for p in passages
            if p.collection in profil.rag_collections
            and p.allowed_for(profil.id, MAX_TICKS)
        ]
        assert lisibles, f"{profil.id} ne peut lire aucun passage"


def test_chaque_profil_a_du_savoir(passages) -> None:
    par_profil = Counter(
        p.allowed_profiles[0] for p in passages if p.collection == "savoir_profils"
    )
    manquants = [prof for prof in PROFILES if par_profil[prof] < 5]
    assert not manquants, f"savoir insuffisant : {manquants}"


def test_chaque_profil_lit_plus_de_passages_avec_le_temps(passages) -> None:
    """`available_tick` doit servir à quelque chose : le savoir s'ouvre."""
    for prof in PROFILES:
        debut = sum(1 for p in passages if p.allowed_for(prof, 0))
        fin = sum(1 for p in passages if p.allowed_for(prof, MAX_TICKS))
        assert debut >= 20, prof
        assert fin > debut, f"{prof} ne gagne aucun passage entre t0 et t{MAX_TICKS}"


def test_les_annonces_sont_lisibles_au_moment_de_l_annonce(passages) -> None:
    """Le scénario annonce à t18 : il doit y avoir de quoi retrouver le texte."""
    annonces = [
        p for p in passages if p.collection == "annonces" and p.allowed_for("visiteur", 18)
    ]
    assert annonces, "aucune annonce lisible à t18"
