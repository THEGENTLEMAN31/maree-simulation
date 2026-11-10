"""Semaine 2 — le cœur comportemental.

Critère de sortie (roadmap S2) : un agent réagit à une annonce, à une
fumée et à un message ; chaque décision a une explication complète. On
verrouille aussi un aperçu de la mission 1 : deux agents du même
archétype, mêmes traits et mêmes sorties connues, mais des **mémoires
personnelles** différentes (messages reçus) → **décisions différentes**.
"""

from __future__ import annotations

from maree.v3.agents.agent import Agent, make_agent
from maree.v3.agents.appraisal import Action
from maree.v3.agents.knowledge import Source
from maree.v3.agents.memory import EpisodeKind
from maree.v3.agents.perception import Message, Perception
from maree.v3.agents.state import State
from maree.v3.core.ids import AgentId, ZoneId


def _perception(
    tick: int = 10,
    *,
    smoke: bool = False,
    announcement: str | None = None,
    heard: tuple[Message, ...] = (),
) -> Perception:
    return Perception(
        tick=tick,
        zone=ZoneId("z1"),
        state=State(),
        smoke_visible=smoke,
        announcement=announcement,
        heard=heard,
        seen_agents=(),
        exits_visible=frozenset(),
    )


def _sage(tick: int = 10, *, know: frozenset[str] = frozenset({"A"})) -> Agent:
    return make_agent(uid=1, archetype="visiteur", known_exits=know)


# ---------------------------------------------------------------
# réactions aux signaux
# ---------------------------------------------------------------


def test_reagit_a_une_annonce_devacuation() -> None:
    a = _sage()
    d = a.react(_perception(announcement="Veuillez évacuer immédiatement par la sortie A"))
    assert d.action == Action.EVACUER
    assert d.target == "A"


def test_reagit_a_la_fumee_visible() -> None:
    a = _sage()
    d = a.react(_perception(smoke=True))
    assert d.action == Action.EVACUER
    assert d.target == "A"


def test_reagit_a_un_message_devacuation() -> None:
    a = _sage(know=frozenset({"A", "B"}))
    d = a.react(_perception(heard=(Message("Évacuez par B, vite !", AgentId(7), 10),)))
    assert d.action == Action.EVACUER
    assert d.target == "B"


def test_une_annonce_ne_vaut_pas_ordre_sil_n_y_a_pas_dordre() -> None:
    a = _sage()
    d = a.react(_perception(announcement="Veuillez rester calmes, tout va bien"))
    assert d.action is not Action.EVACUER


# ---------------------------------------------------------------
# explication complète
# ---------------------------------------------------------------


def test_chaque_decision_a_une_explication_complete() -> None:
    a = _sage()
    d = a.react(_perception(smoke=True))
    assert d.explanation
    assert d.appraisal is not None
    for dim in ("menace", "urgence", "efficacite", "preuve_sociale", "responsabilite"):
        assert dim in d.appraisal.raisons
    # l'explication cite l'agent et au moins une raison d'appraisal
    assert "A01" in d.explanation
    assert any(r in d.explanation for r in d.appraisal.raisons.values())


def test_un_message_positif_apprend_une_croyance_sourcee() -> None:
    a = _sage()
    a.react(_perception(heard=(Message("la sortie B est libre", AgentId(3), 10),)))
    belief = a.knowledge.beliefs.get("exit:B")
    assert belief is not None
    assert belief.source == Source.ENTENDU
    assert belief.confidence > 0.0


def test_un_message_negatif_ecrit_le_recu_en_memoire() -> None:
    """La croyance de danger (et son reçu) doit être tracée pour la divergence."""
    from maree.v3.agents.knowledge import Source as Src

    a = _sage()
    a.react(_perception(heard=(Message("B est bloquée", AgentId(3), 10),)))
    recu = a.memory.receipt_for("B est bloquée")
    assert recu is not None
    assert recu.source == Src.ENTENDU
    hazard = a.knowledge.beliefs.get("hazard:B")
    assert hazard is not None and hazard.confidence >= 0.5


# ---------------------------------------------------------------
# fronts mémorisés : un signal déjà vu ne re-décide pas
# ---------------------------------------------------------------


def test_un_front_deja_vu_ne_redecide_pas() -> None:
    a = _sage()
    first = a.react(_perception(smoke=True))
    n_episodes = len(a.memory.episodes)
    second = a.react(_perception(smoke=True))  # même fumée, rien de nouveau
    assert second is first                      # décision conservée
    assert len(a.memory.episodes) == n_episodes  # pas de doublon


def test_la_memoire_journalise_un_episode_de_decision() -> None:
    a = _sage()
    a.react(_perception(smoke=True))
    kinds = {e.kind for e in a.memory.episodes}
    assert EpisodeKind.DECIDE in kinds


# ---------------------------------------------------------------
# mission 1 : deux jumeaux, mêmes traits, mémoires différentes
# ---------------------------------------------------------------


def test_les_jumeaux_divergent_par_leur_memoire_personnelle() -> None:
    """Deux visiteurs identiques connaissent A et B ; seul leur passé diffère.

    - l'un a entendu « B est bloquée » ;
    - l'autre « B est libre ».
    Face à la même fumée, ils ne prennent pas la même sortie.
    """
    know = frozenset({"A", "B"})
    a1 = make_agent(uid=1, archetype="visiteur", known_exits=know)
    a2 = make_agent(uid=2, archetype="visiteur", known_exits=know)

    # état initial strictement identique
    assert a1.knowledge.beliefs == a2.knowledge.beliefs
    assert a1.traits == a2.traits

    # chacun vit une histoire différente (message reçu)
    a1.react(_perception(tick=5, heard=(Message("B est bloquée", AgentId(3), 5),)))
    a2.react(_perception(tick=5, heard=(Message("B est libre", AgentId(3), 5),)))

    # même situation ensuite : fumée
    d1 = a1.react(_perception(tick=10, smoke=True))
    d2 = a2.react(_perception(tick=10, smoke=True))

    assert d1.action == Action.EVACUER and d1.target == "A"
    assert d2.action == Action.EVACUER and d2.target == "B"
    assert d1.target != d2.target


def test_abolition_memoire_gomme_la_divergence() -> None:
    """Sans histoire personnelle, les jumeaux prennent la même sortie."""
    know = frozenset({"A", "B"})
    a1 = make_agent(uid=1, archetype="visiteur", known_exits=know)
    a2 = make_agent(uid=2, archetype="visiteur", known_exits=know)
    assert a1.react(_perception(tick=10, smoke=True)).target == (
        a2.react(_perception(tick=10, smoke=True)).target
    )