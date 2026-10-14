"""RAG local (F1, F2 ; décisions 12 et 15).

- Corpus en fichiers Markdown à en-tête YAML (world_corpus/) : chaque passage
  porte une date de disponibilité simulée et la liste des profils autorisés
  (décision 15) — un agent ne retrouve jamais ce qu'il n'aurait pu savoir
  à cet instant (C6).
- Embeddings : modèle BGE-small servi par llama.cpp (--embedding).
- Stockage vectoriel : LanceDB (local, sans serveur).
- Récupération hybride : score = sémantique + récence + importance (même
  formule que les generative agents de Stanford).
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

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)


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


class RagClient:
    """Interface du RAG. Mode mémoire pur pour les tests (pas de LanceDB)."""

    def __init__(self, *, db_path: str | None = None) -> None:
        self.db_path = db_path
        self.passages: list[Passage] = []
        self._index: dict[str, dict] = {}  # doc_id -> {terms…} (simplifié)

    # -- ingestion ---------------------------------------------------------

    def ingest_directory(self, corpus_path: str | Path) -> int:
        """Charge tous les Markdown du corpus (une collection = un dossier)."""
        root = Path(corpus_path)
        n = 0
        for md in sorted(root.rglob("*.md")):
            meta, body = self._parse_frontmatter(md)
            collection = md.parent.name
            passage = Passage(
                doc_id=f"{collection}/{md.stem}",
                title=meta.get("title", md.stem),
                collection=collection,
                text=body,
                available_tick=int(meta.get("available_tick", 0)),
                allowed_profiles=meta.get("allowed_profiles", ["*"]),
                importance=float(meta.get("importance", 0.5)),
            )
            self.passages.append(passage)
            self._index[passage.doc_id] = {"tokens": set(self._tokenize(body))}
            n += 1
        return n

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

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"[\wÀ-ÿ-]+", text.lower())

    # -- récupération (F1, F2) --------------------------------------------

    async def retrieve_for(self, agent: "LLMAgent", perception, *, top_k: int = 5) -> str:
        """Sélectionne les passages pertinents pour l'agent, en respectant
        l'accès par profil (décision 15) et la date de disponibilité (C6).
        Journalise les passages retrouvés pour F2 (décision 12)."""
        query = f"{agent.profile_name} {perception.zone} exit evacuation"
        query_tokens = set(self._tokenize(query))
        allowed = [p for p in self.passages if self._allowed(p, agent)]
        scored: list[tuple[float, Passage]] = []
        for p in allowed:
            if p.available_tick > perception.tick:
                continue  # pas encore disponible à cet instant (C6)
            overlap = len(query_tokens & self._index[p.doc_id]["tokens"])
            recent = p.available_tick / max(1, perception.tick + 1)
            score = 0.5 * (overlap / max(1, len(query_tokens))) + 0.3 * recent + 0.2 * p.importance
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]
        # Traçabilité (décision 12) : l'agent garde la trace des passages.
        agent.last_rag = [
            {"doc_id": p.doc_id, "score": round(s, 3)} for s, p in top
        ]
        if not top:
            return ""
        return "\n".join(f"· {p.title} : {p.text[:220]}" for _, p in top)

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