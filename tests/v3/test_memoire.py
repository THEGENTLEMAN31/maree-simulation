"""P0 — mémoire : registre d'opérations rejouable + préhistoire J−3 (A1).

- chaque écriture (learn/episode/signal/consol/forget) est journalisée dans
  ``Memory.ops`` et l'état **se rejoue à l'identique** (event-sourcing) ;
- la préhistoire J−3 inscrit des échanges datés en tick négatif, sourcés,
  qui survivent à l'oubli (reste dans le registre) et alimentent la
  justification d'une décision.
"""

from __future__ import annotations

from maree.v3.agents.knowledge import Source
from maree.v3.agents.memory import EpisodeKind, Memory
from maree.v3.agents.prehistory import (
    J_3,
    PREHISTORY_MAREE,
    prehistory_for,
    seed_prehistory,
)


def test_le_registre_rejoue_la_memoire_a_lidentique() -> None:
    m = Memory()
    m.learn("fumée visible", Source.VU, 10, 0.9)
    m.learn("B est bloquée", Source.ENTENDU, 15, 0.7)
    m.mark_signal_seen("fumée", True, tick=10)
    rejouee = m.replay_register()
    # reçus identiques (sources, ticks, confiances)
    assert rejouee.receipts == m.receipts
    # fronts identiques
    assert rejouee.signals_seen == m.signals_seen
    # épisodes identiques
    assert [(e.kind, e.tick) for e in rejouee.episodes] == [
        (e.kind, e.tick) for e in m.episodes
    ]


def test_le_rejeu_est_idempotent() -> None:
    m = Memory()
    m.learn("A fermée", Source.RUMEUR, -8_640, 0.8)
    m.mark_signal_seen("annonce", "x", tick=5)
    assert m.replay_register().receipts == m.replay_register().receipts


def test_la_prehistoire_j3_est_sourcee_et_ancienne() -> None:
    m = Memory()
    seed_prehistory(m, PREHISTORY_MAREE)
    # 3 reçus, datés en tick négatif
    assert len(m.receipts) == 3
    recu = m.receipt_for("la sortie C existe et évite la passerelle")
    assert recu is not None
    assert recu.tick == J_3
    assert recu.source == Source.ENTENDU
    # un épisode de ouï-dire bien daté
    assert any(e.tick == J_3 and e.kind == EpisodeKind.ENTENDU for e in m.episodes)


def test_la_prehistoire_se_rejoue_dans_le_registre() -> None:
    m = Memory()
    seed_prehistory(m, PREHISTORY_MAREE)
    rejouee = m.replay_register()
    assert rejouee.receipts == m.receipts
    # l'échange vieux de plusieurs jours est toujours là (pas d'évaporation)
    assert rejouee.receipt_for("la sortie A avait été fermée l'an dernier") is not None


def test_prehistory_par_archetype() -> None:
    fam = prehistory_for("famille")
    visit = prehistory_for("visiteur")
    assert len(fam) == 2   # J−2 et J−1
    assert len(visit) == 1  # J−3 seulement
    assert visit[0].target == "visiteur"