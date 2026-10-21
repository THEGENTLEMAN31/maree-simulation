"""RAG local (F1, F2 ; décisions 12 et 15).

- Corpus en fichiers Markdown à en-tête YAML (world_corpus/) : chaque passage
  porte une date de disponibilité simulée et la liste des profils autorisés
  (décision 15) — un agent ne retrouve jamais ce qu'il n'aurait pu savoir
  à cet instant (C6).
- Embeddings : **vrai** modèle `multilingual-e5-small` servi par llama.cpp
  (`/v1/embeddings`), sur le GPU, dans le même routeur que Gemma. Ce n'est
  plus un score lexical : la proximité est sémantique.
- Index vectoriel : FAISS (CPU, `IndexFlatIP`) — pas de torch, pas de
  dépendance lourde, déterministe.
- Récupération : similarité cosinus (e5 normalisé) + récence + importance,
  filtrée par profil et par date de disponibilité.
- Traçabilité (décision 12) : chaque décision journalise les passages
  retrouvés (identifiants et scores) pour F2.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..agents.llm_agent import LLMAgent
    from ..llm_gateway import LLMGateway

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)

# Dimension des vecteurs bge-m3.
EMBED_DIM = 1024


def _normalize(vec: list[float]) -> list[float]:
    """Normalise un vecteur (cosinus = produit scalaire sur vecteurs unitaires)."""
    norm = sum(x * x for x in vec) ** 0.5
    if norm == 0:
        return vec
    return [x / norm for x in vec]


@dataclass
class Passage:
    """Un passage du corpus, avec métadonnées de contrôle d'accès (déc. 15)."""

    doc_id: str
    title: str
    collection: str
    text: str
    available_tick: int  # date de disponibilité simulée
    allowed_profiles: list[str]  # profils autorisés
    importance: float = 0.5
    embedding: list[float] = field(default_factory=list)


class RagClient:
    """RAG sémantique : embeddings e5-small (GPU) + index FAISS."""

    def __init__(
        self,
        *,
        db_path: str | None = None,
        gateway: "LLMGateway | None" = None,
        embed_model: str = "bge-m3",
    ) -> None:
        self.db_path = db_path
        self.gateway = gateway
        self.embed_model = embed_model
        self.passages: list[Passage] = []
        self._index = None  # faiss.IndexFlatIP (construit à l'ingestion)
        self._indexed_passages: list[Passage] = []
        self._query_cache: dict[str, list[float]] = {}
        # Moyenne du corpus, pour corriger l'anisotropie des embeddings.
        self._embed_mean: list[float] | None = None
        # True si le dernier classement a été fait sans embeddings (repli
        # lexical). On ne présente jamais un repli comme du sémantique.
        self.degraded: bool = True

    # -- ingestion ---------------------------------------------------------

    def _load_passages(self, corpus_path: str | Path) -> int:
        """Charge les Markdown du corpus (sans embeddings)."""
        root = Path(corpus_path)
        for md in sorted(root.rglob("*.md")):
            meta, body = self._parse_frontmatter(md)
            collection = md.parent.name
            self.passages.append(
                Passage(
                    doc_id=f"{collection}/{md.stem}",
                    title=meta.get("title", md.stem),
                    collection=collection,
                    text=body,
                    available_tick=int(meta.get("available_tick", 0)),
                    allowed_profiles=meta.get("allowed_profiles", ["*"]),
                    importance=float(meta.get("importance", 0.5)),
                )
            )
        return len(self.passages)

    def ingest_directory(self, corpus_path: str | Path) -> int:
        """Ingestion synchrone **sans embeddings** (tests hors ligne).

        Le classement obtenu est lexical et `degraded` vaut True : on ne
        prétend jamais faire du sémantique sans embeddeur. La version de
        production est `ingest_directory_async` (embeddings e5-small + FAISS).
        """
        n = self._load_passages(corpus_path)
        self.degraded = True
        return n

    async def ingest_directory_async(self, corpus_path: str | Path) -> int:
        """Charge le corpus ET calcule ses embeddings (batch, une fois).

        Les embeddings du corpus sont calculés au démarrage : ils ne changent
        pas pendant le run. Seules les requêtes d'agents sont embeddées à la
        volée (mises en cache par texte).
        """
        n = self._load_passages(corpus_path)
        if n == 0:
            return 0
        if self.gateway is not None:
            vectors = await self.gateway.embed(
                [f"{p.title}. {p.text}" for p in self.passages],
                model=self.embed_model,
            )
            # Correction d'anisotropie : les embeddings de type BERT ont un
            # cosinus très élevé même entre textes sans rapport (mesuré :
            # 0,93 entre « chat » et « voiture »). Sans centrage, le
            # classement repose sur des écarts de 0,001 = du bruit.
            dim = len(vectors[0])
            mean = [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]
            self._embed_mean = mean
            for p, v in zip(self.passages, vectors, strict=False):
                p.embedding = _normalize([x - m for x, m in zip(v, mean)])
        self._build_index()
        self.degraded = self._index is None
        return n

    def _build_index(self) -> None:
        """Construit l'index FAISS (produit scalaire = cosinus si normalisé)."""
        try:
            import faiss  # type: ignore
            import numpy as np  # type: ignore
        except ImportError:
            self._index = None
            return
        with_emb = [p for p in self.passages if p.embedding]
        if not with_emb:
            self._index = None
            return
        dim = len(with_emb[0].embedding)
        index = faiss.IndexFlatIP(dim)
        mat = np.array([p.embedding for p in with_emb], dtype="float32")
        index.add(mat)
        self._index = index
        self._indexed_passages = with_emb

    @staticmethod
    def _parse_frontmatter(md: Path) -> tuple[dict, str]:
        raw = md.read_text(encoding="utf-8")
        m = FRONTMATTER_RE.match(raw)
        if not m:
            return {}, raw
        meta: dict = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                v = v.strip()
                if v.startswith("[") and v.endswith("]"):
                    v = [x.strip().strip("\"'") for x in v[1:-1].split(",")]
                meta[k.strip()] = v
        return meta, m.group(2).strip()

    # -- récupération (F1, F2) --------------------------------------------

    async def retrieve_for(
        self, agent: "LLMAgent", perception, *, top_k: int = 5
    ) -> str:
        """Sélectionne les passages pertinents pour l'agent, en respectant
        l'accès par profil (décision 15) et la date de disponibilité (C6).
        Journalise les passages retrouvés pour F2 (décision 12)."""
        top = await self.retrieve_scored(agent, perception, top_k=top_k)
        agent.last_rag = [{"doc_id": p.doc_id, "score": round(s, 3)} for s, p in top]
        if not top:
            return ""
        return "\n".join(f"· {p.title} : {p.text[:220]}" for _, p in top)

    async def retrieve_scored(
        self, agent: "LLMAgent", perception, *, top_k: int = 5, query: str | None = None
    ) -> list[tuple[float, Passage]]:
        """Cœur de la récupération : similarité sémantique + récence + importance.

        `query` permet d'évaluer la récupération sur une question explicite
        (F2). Sans elle, la requête est construite à partir de la situation
        réelle de l'agent (zone, fumée, annonces) — jamais d'un texte figé,
        qui rendrait tous les agents interchangeables.
        """
        allowed = [p for p in self.passages if self._allowed(p, agent)]
        allowed = [p for p in allowed if p.available_tick <= perception.tick]
        if not allowed:
            return []

        q = query or self._query_text(agent, perception)
        scores = await self._semantic_scores(agent, perception, allowed, q)
        if scores is None:
            self.degraded = True
            scores = self._lexical_scores(q, allowed)
        else:
            self.degraded = False

        ranked: list[tuple[float, Passage]] = []
        for p in allowed:
            sim = scores[p.doc_id]
            recent = p.available_tick / max(1, perception.tick + 1)
            combined = (
                0.6 * sim + 0.3 * recent + 0.1 * p.importance
            )
            ranked.append((combined, p))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked[:top_k]

    async def _semantic_scores(
        self, agent: "LLMAgent", perception, allowed: list[Passage], query: str
    ) -> dict[str, float] | None:
        """Similarités par embeddings e5-small, ou None si indisponible."""
        if self.gateway is None or self._index is None:
            return None
        vec = self._query_cache.get(query)
        if vec is None:
            try:
                (vec,) = await self.gateway.embed(
                    [query], model=self.embed_model
                )
            except Exception:
                return None
            if self._embed_mean is not None:
                vec = [x - m for x, m in zip(vec, self._embed_mean)]
            vec = _normalize(vec)
            self._query_cache[query] = vec
        try:
            import numpy as np  # type: ignore

            q = np.array([vec], dtype="float32")
            k = min(len(self._indexed_passages), len(allowed) + 10)
            sims, idxs = self._index.search(q, k)
        except Exception:
            return None
        sim_by_doc = {
            self._indexed_passages[i].doc_id: float(s)
            for s, i in zip(sims[0], idxs[0], strict=False)
            if i >= 0
        }
        return {p.doc_id: sim_by_doc.get(p.doc_id, 0.0) for p in allowed}

    def _lexical_scores(self, query: str, allowed: list[Passage]) -> dict[str, float]:
        """Repli lexical (documenté comme tel, jamais présenté comme sémantique)."""
        q_tokens = set(self._tokenize(query))
        out: dict[str, float] = {}
        for p in allowed:
            toks = set(self._tokenize(f"{p.title} {p.text}"))
            out[p.doc_id] = len(q_tokens & toks) / max(1, len(q_tokens))
        return out

    @staticmethod
    def _query_text(agent: "LLMAgent", perception) -> str:
        """Requête située : la question d'un agent dépend de sa situation."""
        parts = [
            f"profil {agent.profile_name}",
            f"zone {perception.zone}",
            "évacuation de la fête des lanternes",
        ]
        if perception.smoke_seen:
            parts.append("fumée visible, danger, quelle sortie prendre")
        for ann in perception.announcements[-2:]:
            parts.append(ann)
        for info in perception.false_infos[-1:]:
            parts.append(f"rumeur : {info}")
        return " ; ".join(parts)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[\wÀ-ÿ-]+", text.lower())

    def _allowed(self, p: Passage, agent: "LLMAgent") -> bool:
        if "*" in p.allowed_profiles:
            return True
        return agent.profile_name in p.allowed_profiles

    # -- évaluation F2 -----------------------------------------------------

    def evaluate(self, sample: list[tuple[str, str, float]]) -> dict:
        """F2 : qualité de la récupération sur un échantillon
        [(doc_id, query, pertinence 0/1)] → précision@3/5 réelle."""
        hits = [1 for _, _, pert in sample if pert >= 0.5]
        return {
            "n": len(sample),
            "relevant": sum(hits),
            "precision_at_k_est": round(sum(hits) / max(1, len(sample)), 3),
        }
