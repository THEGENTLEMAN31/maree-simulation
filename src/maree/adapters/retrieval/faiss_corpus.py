"""RAG — FAISS exact + correction d'anisotropie, filtré par profil et par date.

Pourquoi pas LlamaIndex ici : le corpus est déjà découpé en 215 passages
d'un paragraphe, avec métadonnées. Il n'y a rien à ingérer ni à découper.
Le seul traitement qui compte est le **centrage sur la moyenne du corpus** :
sans lui, les embeddings de bge-m3 sont anisotropes et la précision@1
s'effondre (mesuré en v1 : 0,167 avec e5-small, 0,733 après correction).
Réécrire ce centrage par-dessus une abstraction générique coûterait plus
qu'il ne rapporte. C'est un choix documenté, pas un oubli.

Décision 15 : un agent ne peut lire que les collections de son profil et
les passages disponibles à son tick simulé.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from maree.domain.ids import Tick
from maree.ports import LLMPort, RetrievedPassage

_WORD = re.compile(r"[a-zàâçéèêëîïôûùüÿñæœ0-9]+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Passage:
    doc_id: str
    text: str
    collection: str
    available_tick: int
    allowed_profiles: tuple[str, ...]
    importance: float
    title: str

    def allowed_for(self, profile: str, tick: Tick) -> bool:
        if self.available_tick > tick:
            return False
        if not self.allowed_profiles:
            return True
        return profile in self.allowed_profiles


def load_corpus(root: str | Path) -> list[Passage]:
    """Lit les fichiers Markdown à front matter YAML du corpus."""
    root = Path(root)
    passages: list[Passage] = []
    for path in sorted(root.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        if not raw.startswith("---"):
            continue
        _, front, body = raw.split("---", 2)
        meta: dict[str, Any] = yaml.safe_load(front) or {}
        passages.append(
            Passage(
                doc_id=str(path.relative_to(root).with_suffix("")),
                text=" ".join(body.split()),
                collection=str(meta.get("collection", path.parent.name)),
                available_tick=int(meta.get("available_tick", 0)),
                allowed_profiles=tuple(meta.get("allowed_profiles") or ()),
                importance=float(meta.get("importance", 0.5)),
                title=str(meta.get("title", path.stem)),
            )
        )
    return passages


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class FaissRetriever:
    """Recherche exacte (IndexFlatIP) sur des vecteurs centrés et normalisés."""

    def __init__(
        self,
        passages: list[Passage],
        matrix: np.ndarray,
        mean: np.ndarray,
        embedder: LLMPort | None,
        *,
        min_score: float = 0.0,
        respect_collections: bool = True,
    ) -> None:
        import faiss

        self._passages = passages
        self._mean = mean
        self._embedder = embedder
        self._min_score = min_score
        #: F1 — un agent ne lit que les collections de son profil. Sans ce
        #: filtre, `rag_collections` était déclaré dans chaque profil mais
        #: jamais appliqué : la seule barrière était `allowed_profiles` du
        #: corpus, ce qui laissait un visiteur lire des consignes de
        #: sécurité si un passage les autorisait.
        self._respect_collections = respect_collections
        self._matrix = _normalise(matrix - mean)
        self._index = faiss.IndexFlatIP(self._matrix.shape[1])
        self._index.add(self._matrix.astype(np.float32))
        self._degraded = embedder is None

    @property
    def degraded(self) -> bool:
        return self._degraded

    # ---- construction -----------------------------------------
    @classmethod
    async def build(
        cls, corpus_dir: str | Path, embedder: LLMPort, *, batch: int = 32
    ) -> FaissRetriever:
        passages = load_corpus(corpus_dir)
        if not passages:
            raise ValueError(f"corpus vide : {corpus_dir}")
        vectors: list[list[float]] = []
        for start in range(0, len(passages), batch):
            chunk = [p.text for p in passages[start : start + batch]]
            vectors.extend(await embedder.embed(chunk))
        matrix = np.asarray(vectors, dtype=np.float32)
        mean = matrix.mean(axis=0)
        return cls(passages, matrix, mean, embedder)

    def save(self, directory: str | Path) -> None:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        np.save(directory / "vectors.npy", self._matrix)
        np.save(directory / "mean.npy", self._mean)
        (directory / "passages.json").write_text(
            json.dumps([asdict(p) for p in self._passages], ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, directory: str | Path, embedder: LLMPort | None) -> FaissRetriever:
        directory = Path(directory)
        matrix = np.load(directory / "vectors.npy")
        mean = np.load(directory / "mean.npy")
        raw = json.loads((directory / "passages.json").read_text(encoding="utf-8"))
        passages = [
            Passage(
                doc_id=p["doc_id"],
                text=p["text"],
                collection=p["collection"],
                available_tick=p["available_tick"],
                allowed_profiles=tuple(p["allowed_profiles"]),
                importance=p["importance"],
                title=p["title"],
            )
            for p in raw
        ]
        # Les vecteurs sont déjà centrés : on annule le centrage pour ne pas
        # l'appliquer deux fois dans __init__.
        return cls(passages, matrix + mean, mean, embedder)

    # ---- requête ----------------------------------------------
    def _allowed(self, passage: Passage, profile: str, tick: Tick,
                 collections: tuple[str, ...] | None) -> bool:
        if not passage.allowed_for(profile, tick):
            return False
        if self._respect_collections and collections is not None:
            return passage.collection in collections
        return True

    async def retrieve(
        self,
        query: str,
        *,
        profile: str,
        tick: Tick,
        k: int = 3,
        collections: tuple[str, ...] | None = None,
    ) -> list[RetrievedPassage]:
        if self._embedder is None:
            return self._lexical(query, profile=profile, tick=tick, k=k, collections=collections)
        vectors = await self._embedder.embed([query])
        if not vectors:
            return self._lexical(query, profile=profile, tick=tick, k=k, collections=collections)
        q = np.asarray(vectors[0], dtype=np.float32) - self._mean
        norm = np.linalg.norm(q) or 1.0
        q = (q / norm).astype(np.float32).reshape(1, -1)
        scores, indices = self._index.search(q, min(len(self._passages), max(k * 8, 24)))
        out: list[RetrievedPassage] = []
        for score, idx in zip(scores[0], indices[0], strict=False):
            if idx < 0:
                continue
            passage = self._passages[int(idx)]
            if not self._allowed(passage, profile, tick, collections):
                continue
            if float(score) < self._min_score:
                continue
            out.append(
                RetrievedPassage(
                    doc_id=passage.doc_id,
                    text=passage.text,
                    score=float(score),
                    collection=passage.collection,
                    metadata={
                        "title": passage.title,
                        "available_tick": passage.available_tick,
                        "importance": passage.importance,
                    },
                )
            )
            if len(out) >= k:
                break
        return out or self._lexical(
            query, profile=profile, tick=tick, k=k, collections=collections
        )

    # ---- repli lexical (signalé, jamais présenté comme sémantique) ----
    def _lexical(
        self,
        query: str,
        *,
        profile: str,
        tick: Tick,
        k: int,
        collections: tuple[str, ...] | None = None,
    ) -> list[RetrievedPassage]:
        wanted = {w.lower() for w in _WORD.findall(query) if len(w) > 2}
        scored: list[tuple[float, Passage]] = []
        for passage in self._passages:
            if not self._allowed(passage, profile, tick, collections):
                continue
            terms = {w.lower() for w in _WORD.findall(passage.text) if len(w) > 2}
            overlap = len(wanted & terms)
            if overlap:
                scored.append((overlap / math.sqrt(len(terms) or 1), passage))
        scored.sort(key=lambda x: (-x[0], x[1].doc_id))
        return [
            RetrievedPassage(
                doc_id=p.doc_id,
                text=p.text,
                score=score,
                collection=p.collection,
                metadata={"title": p.title, "degraded": True},
            )
            for score, p in scored[:k]
        ]
