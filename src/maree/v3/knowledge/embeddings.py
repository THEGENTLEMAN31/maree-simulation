"""knowledge.embeddings — l'embedder de la base de connaissances (F1/F2).

Le corpus du monde (fictif) est écrit par nous ; les décisions LLM doivent
pouvoir s'appuyer sur des passages **retrouvés**, pas seulement leur prompt.

Deux implémentations derrière un ``Protocol`` :
- ``StubEmbedder`` (déterministe, hors-ligne) : un **sac-de-mots** réellement
  sémantique au niveau des termes — les tests et la CI peuvent vérifier la
  pertinence sans modèle ni réseau ;
- ``BgeM3Embedder`` : le vrai (bge-m3, pooling CLS), servi par un llama-server
  qui expose ``/v1/embeddings`` (dialecte OpenAI, comme le chat).
"""

from __future__ import annotations

import re
from typing import Protocol

import numpy as np

#: mots-outils français retirés du sac-de-mots (sinon le bruit domine).
_STOPWORDS = frozenset({
    "la", "le", "les", "de", "des", "du", "au", "aux", "un", "une", "et", "est",
    "en", "que", "qui", "pour", "par", "avec", "sur", "se", "ne", "pas", "il",
    "elle", "son", "sa", "ses", "ce", "cette", "dans", "plus", "bien",
})


class Embedder(Protocol):
    """Ce que le retriever exige : des textes → des vecteurs (2D)."""

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


class StubEmbedder:
    """Embeddings **déterministes** par mots-clés (tests/CI, sans réseau).

    Sac-de-mots normalisé ; le vocabulaire est gelé au premier
    ``embed_documents``. La similarité est *réellement* pertinente au niveau
    des termes : « sortie nord » retrouve le passage qui parle du nord.
    """

    def __init__(self) -> None:
        self._vocab: list[str] = []
        self._col: dict[str, int] = {}

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [t for t in re.findall(r"[a-zà-ÿ0-9']{2,}", text.lower()) if t not in _STOPWORDS]

    def _ensure_vocab(self, texts: list[str]) -> None:
        if self._col:
            return
        seen = sorted({t for text in texts for t in self._tokens(text)})
        self._vocab = seen
        self._col = {w: i for i, w in enumerate(seen)}

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(len(self._vocab), dtype="float32")
        for t in self._tokens(text):
            i = self._col.get(t)
            if i is not None:
                v[i] += 1.0
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        self._ensure_vocab(texts)
        return np.stack([self._vec(t) for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._vec(text)


class BgeM3Embedder:
    """bge-m3 réel derrière un llama-server avec ``/v1/embeddings``.

    bge-m3 est un BERT : llama.cpp fait déjà le pooling ; on ne touche pas à
    l'embedding raw. Dimension par défaut : 1 024 (bge-m3).
    """

    def __init__(self, base_url: str, model: str = "bge-m3", dim: int = 1024) -> None:
        from openai import OpenAI

        self._client = OpenAI(base_url=base_url, api_key="sk-local", max_retries=0)
        self.model = model
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        resp = self._client.embeddings.create(model=self.model, input=texts)
        rows = [d.embedding for d in resp.data]
        return np.asarray(rows, dtype="float32")

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


__all__ = ["BgeM3Embedder", "Embedder", "StubEmbedder"]