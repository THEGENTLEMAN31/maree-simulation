"""P1 — RAG : le retriever LangChain retrouve les passages, filtrés (F1/F2/C6).

- une requête « sortie » retrouve un passage de plan pertinent ;
- un agent ne retrouve **jamais** un passage non diffusé (date > maintenant,
  C6) ni qui n'est pas de son profil (F1) ;
- l'évaluation de base (P@1/P@3) est calculée et reproductible (F2).
"""

from __future__ import annotations

from maree.v3.knowledge.corpus import CORPUS
from maree.v3.knowledge.embeddings import StubEmbedder
from maree.v3.knowledge.rag import RagRetriever


def _build() -> RagRetriever:
    return RagRetriever.build(StubEmbedder(), corpus=CORPUS)


def test_le_retriever_retrouve_une_sortie() -> None:
    r = _build()
    hits = r.retrieve("quelle sortie est au nord ?", now=100, profile="visiteur", k=3)
    assert hits
    top_id = hits[0][0].metadata["id"]
    assert top_id == "plan_A"   # la requête la plus proche du passage du plan A


def test_on_ne_retrouve_jamais_du_futur() -> None:
    r = _build()
    # à t=10, l'annonce (dispo à 60) ne doit pas être retrouvée
    hits = r.retrieve("que dit l'annonce ?", now=10, profile="visiteur", k=10)
    assert not any(d.metadata["collection"] == "annonces" for d, _ in hits)


def test_le_profil_est_respecte() -> None:
    r = _build()
    # un visiteur ne doit pas retrouver la sortie C (réservée habitués/securite)
    hits = r.retrieve("la sortie discrète au sud", now=100, profile="visiteur", k=10)
    assert not any(d.metadata["id"] == "plan_C" for d, _ in hits)
    # mais un habitué peut
    hits_h = r.retrieve("la sortie discrète au sud", now=100, profile="habitue", k=10)
    assert any(d.metadata["id"] == "plan_C" for d, _ in hits_h)


def test_le_langchain_retriever_syintegre() -> None:
    r = _build()
    docs = r.invoke("fumée au sud")
    assert docs  # _get_relevant_documents (top-k, interface LangChain)


def test_evaluation_minimale_f2() -> None:
    r = _build()
    requests = [
        ("sortie nord", "plan_A"),
        ("passerelle est étroite", "plan_B"),
        ("édition 2019 fumée", "souvenir_2019"),
    ]
    p1 = sum(1 for q, expected in requests
             if r.retrieve(q, now=1000, profile="habitue", k=1)[0][0].metadata["id"] == expected)
    assert p1 >= 2  # P@1 >= 2/3 sur ce petit jeu annoté