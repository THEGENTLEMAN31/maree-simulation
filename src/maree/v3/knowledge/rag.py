"""knowledge.rag — le retriever LangChain par-dessus FAISS (F1/F2).

Un ``Retriever`` LangChain (``BaseRetriever``) qui :
- indexe les passages du corpus en **FAISS exact** (IndexFlatIP) avec le
  **centrage d'anisotropie** (bge-m3 : on soustrait la moyenne du corpus) ;
- avant chaque retour, applique les **filtres** (leçon v2 / décision 15) :
  **date de disponibilité** (C6 : rien de t_prod > maintenant) et **profil
  autorisé** — c'est ce qui empêche de retrouver une info future ou privée.

``retrieve()`` rend les passages retrouvés + leur score (la matière de F2).
"""

from __future__ import annotations

from typing import Any

import numpy as np
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from maree.v3.knowledge.corpus import passages
from maree.v3.knowledge.embeddings import Embedder


class RagRetriever(BaseRetriever):
    """Recherche de similarité exacte, filtrée par temps simulé et profil."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    embedder: Any
    vectors: Any
    docs: Any
    mean: Any

    @classmethod
    def build(cls, embedder: Embedder, corpus=passages(), subtract_mean: bool = True) -> RagRetriever:
        """Construit l'index depuis un corpus (embeddings + centrage)."""
        docs = [p.as_langchain_document() for p in corpus]
        vectors = embedder.embed_documents([d.page_content for d in docs]).astype("float32")
        mean = vectors.mean(axis=0) if subtract_mean else np.zeros_like(vectors[0])
        return cls(embedder=embedder, vectors=vectors - mean, docs=docs, mean=mean)

    def _retrieve_candidates(self, query: str, k: int) -> list[tuple[Document, float]]:
        q = self.embedder.embed_query(query).astype("float32") - self.mean
        scores = self.vectors @ q
        order = np.argsort(-scores)[:k]
        return [(self.docs[i], float(scores[i])) for i in order]

    def _get_relevant_documents(self, query: str, *, run_manager: Any) -> list[Document]:
        """Contrat LangChain : top-k sans filtres (intégration à l'écosystème)."""
        return [doc for doc, _ in self._retrieve_candidates(query, k=3)]

    def retrieve(
        self,
        query: str,
        *,
        now: int,
        profile: str,
        k: int = 3,
    ) -> list[tuple[Document, float]]:
        """Retourne les k passages : autorisés au profil, disponibles avant ``now``.

        Le nombre de candidats balayé est borné (ici le corpus entier, petit) ;
        on filtre **avant** de tronquer pour ne jamais retrouver du futur
        (C6) ni une source d'un autre profil (F1).
        """
        kept: list[tuple[Document, float]] = []
        for d, s in self._retrieve_candidates(query, k=len(self.docs)):
            meta = d.metadata
            profiles = meta.get("allowed_profiles") or ["tous"]
            if "tous" not in profiles and profile not in profiles:
                continue
            if int(meta.get("available_tick", 0)) > now:
                continue
            kept.append((d, s))
        kept.sort(key=lambda ds: ds[1], reverse=True)
        return kept[:k]


__all__ = ["RagRetriever"]