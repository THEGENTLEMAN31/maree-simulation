"""Mémoire : le cloisonnement est une garantie, pas une intention.

C'est le test le plus important du projet. Si un agent peut lire la
mémoire d'un autre, un visiteur « sait » ce qu'un habitué sait, et
l'expérience ne mesure plus rien. On le vérifie par propriété, pas par
un exemple choisi.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from maree.memory.store import EventSourcedMemory
from maree.ports import Episode


def _episode(content: str, tick: int = 0, kind: str = "vu") -> Episode:
    return Episode(tick=tick, kind=kind, content=content, source="test", salience=0.5)


def test_deux_agents_ne_partagent_rien() -> None:
    memory = EventSourcedMemory()
    memory.remember("A01", _episode("la sortie B est derrière les stands"))
    memory.remember("A02", _episode("j'ai vu de la fumée"))

    a01 = [e.content for e in memory.recall("A01", k=10)]
    a02 = [e.content for e in memory.recall("A02", k=10)]

    assert "j'ai vu de la fumée" not in a01
    assert "la sortie B est derrière les stands" not in a02


@settings(max_examples=50, deadline=None)
@given(
    text_a=st.text(min_size=1, max_size=60),
    text_b=st.text(min_size=1, max_size=60),
    k=st.integers(min_value=1, max_value=8),
)
def test_isolation_pour_tout_contenu(text_a: str, text_b: str, k: int) -> None:
    memory = EventSourcedMemory()
    memory.remember("A01", _episode(f"A::{text_a}"))
    memory.remember("A02", _episode(f"B::{text_b}"))

    seen_by_a = {e.content for e in memory.recall("A01", k=k)}
    seen_by_b = {e.content for e in memory.recall("A02", k=k)}

    assert all(content.startswith("A::") for content in seen_by_a)
    assert all(content.startswith("B::") for content in seen_by_b)


def test_agent_inconnu_a_une_memoire_vide() -> None:
    memory = EventSourcedMemory()
    assert memory.recall("A99") == []
    assert memory.size("A99") == 0


def test_rappel_est_deterministe() -> None:
    memory = EventSourcedMemory()
    for tick in range(10):
        memory.remember("A01", _episode(f"souvenir {tick}", tick=tick))
    first = [e.content for e in memory.recall("A01", k=4, tick=10)]
    second = [e.content for e in memory.recall("A01", k=4, tick=10)]
    assert first == second


def test_consolidation_borne_la_memoire() -> None:
    memory = EventSourcedMemory(window=4)
    for tick in range(20):
        memory.remember("A01", _episode(f"vu {tick}", tick=tick))
    memory.consolidate("A01", tick=20)
    assert memory.size("A01") == 5  # 1 résumé + 4 récents
    assert any(e.kind == "resume" for e in memory.recall("A01", k=10))


def test_consolidation_sous_la_fenetre_ne_fait_rien() -> None:
    memory = EventSourcedMemory(window=10)
    memory.remember("A01", _episode("un seul"))
    memory.consolidate("A01", tick=1)
    assert memory.size("A01") == 1


def test_acces_global_reserve() -> None:
    memory = EventSourcedMemory()
    memory.remember("A01", _episode("secret"))
    try:
        memory.read_all("A01")
    except PermissionError:
        pass
    else:  # pragma: no cover
        raise AssertionError("un agent a pu lire la mémoire globale")
    assert "A01" in memory.read_all("narrator")
    assert "A01" in memory.read_all("analyst")
