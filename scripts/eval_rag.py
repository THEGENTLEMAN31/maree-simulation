#!/usr/bin/env python3
"""Évaluation de la récupération (F2) — un chiffre, pas une impression.

Deux modes :

    --index data/rag      évalue le récupérateur sur `eval/rag_queries.yaml`
                          (P@1, P@3, MRR), et écrit un JSON versionnable ;
    --run <run_id>        relit un journal et décrit ce qui a *réellement*
                          été retrouvé à chaque décision (couverture, scores,
                          collections, décisions sans aucun passage).

Le mode `--run` est celui qui répond à la question du jury : « montrez une
décision prise à partir d'une information mal retrouvée ». Les passages
sont journalisés depuis le correctif F2 (`retrieved` dans
`agent.decision`), donc l'analyse ne demande aucun nouvel appel LLM.

Usage :
    uv run python scripts/eval_rag.py --index data/rag
    uv run python scripts/eval_rag.py --run run_x1_hybride_s0_ab12
    uv run python scripts/eval_rag.py --index data/rag --lexical   # sans GPU
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load_queries(path: Path) -> list[dict]:
    return list(yaml.safe_load(path.read_text(encoding="utf-8"))["queries"])


def _score(ranked: list[str], expected: list[str]) -> tuple[bool, bool, float]:
    """(hit@1, hit@3, rang réciproque) pour une requête."""
    first = next((i for i, doc in enumerate(ranked, start=1) if doc in expected), None)
    return (
        first == 1,
        first is not None and first <= 3,
        (1.0 / first) if first else 0.0,
    )


async def evaluate_index(index: Path, queries_path: Path, *, lexical: bool) -> dict:
    from maree.adapters.llm import LlamaCppLLM
    from maree.adapters.retrieval.faiss_corpus import FaissRetriever

    embedder = None
    if not lexical:
        embedder = LlamaCppLLM(
            base_url=__import__("os").environ.get("MAREE_LLM_URL", "http://llama-cpp:8080/v1"),
            model="gemma4-e2b",
            embed_model="bge-m3",
        )
    retriever = FaissRetriever.load(index, embedder)
    queries = _load_queries(queries_path)
    rows = []
    try:
        for q in queries:
            passages = await retriever.retrieve(
                q["query"], profile=q["profile"], tick=int(q["tick"]), k=3
            )
            ranked = [p.doc_id for p in passages]
            expected = list(q["expected_any"])
            hit1, hit3, rr = _score(ranked, expected)
            rows.append(
                {
                    "id": q["id"],
                    "query": q["query"],
                    "profile": q["profile"],
                    "tick": q["tick"],
                    "expected_any": expected,
                    "ranked": ranked,
                    "scores": [round(p.score, 4) for p in passages],
                    "hit@1": hit1,
                    "hit@3": hit3,
                    "rr": round(rr, 4),
                }
            )
    finally:
        if embedder is not None:
            await embedder.close()
    n = len(rows) or 1
    return {
        "mode": "lexical" if lexical else "semantic",
        "degraded": retriever.degraded,
        "index": str(index).replace(str(ROOT) + "/", ""),
        "queries": str(queries_path).replace(str(ROOT) + "/", ""),
        "n": len(rows),
        "p@1": round(sum(r["hit@1"] for r in rows) / n, 4),
        "p@3": round(sum(r["hit@3"] for r in rows) / n, 4),
        "mrr": round(sum(r["rr"] for r in rows) / n, 4),
        "rows": rows,
    }


def evaluate_run(runs: Path, run_id: str) -> dict:
    """Ce qui a été retrouvé pendant un run réel, lu depuis le journal."""
    from maree.adapters.journal.jsonl import JsonlJournal

    events = JsonlJournal(runs).read(run_id)
    decisions = [e for e in events if str(e.type) == "agent.decision"]
    with_retrieval = [e for e in decisions if e.data.get("retrieved")]
    scores: list[float] = []
    collections: dict[str, int] = {}
    for e in with_retrieval:
        for p in e.data["retrieved"]:
            scores.append(float(p.get("score", 0.0)))
            collections[p.get("collection", "?")] = collections.get(p.get("collection", "?"), 0) + 1
    return {
        "run_id": run_id,
        "decisions": len(decisions),
        "avec_recuperation": len(with_retrieval),
        "couverture": round(len(with_retrieval) / len(decisions), 4) if decisions else 0.0,
        "passages": len(scores),
        "score_moyen": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "collections": dict(sorted(collections.items(), key=lambda kv: -kv[1])),
        # Les décisions sans passage sont celles où le RAG n'a pas été
        # sollicité (croyance déjà sûre) : ce n'est pas un échec, mais il
        # faut le dire plutôt que de moyenner sur les seules réussites.
        "sans_passage": [
            {"seq": e.seq, "tick": e.t_prod, "agent": e.data.get("agent_id")}
            for e in decisions
            if not e.data.get("retrieved")
        ][:20],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, default=ROOT / "data" / "rag")
    ap.add_argument("--queries", type=Path, default=ROOT / "eval" / "rag_queries.yaml")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "resultats" / "rag_eval.json")
    ap.add_argument("--run", help="évaluer un run enregistré au lieu de l'index")
    ap.add_argument("--runs", type=Path, default=ROOT / "runs")
    ap.add_argument("--lexical", action="store_true", help="sans bge-m3 (repli lexical)")
    args = ap.parse_args()

    if args.run:
        result = evaluate_run(args.runs, args.run)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    result = asyncio.run(evaluate_index(args.index, args.queries, lexical=args.lexical))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"{result['mode']:<9} n={result['n']:<3} "
        f"P@1={result['p@1']:.3f}  P@3={result['p@3']:.3f}  MRR={result['mrr']:.3f}"
    )
    for row in result["rows"]:
        flag = "✓" if row["hit@1"] else ("~" if row["hit@3"] else "✗")
        print(f"  {flag} {row['id']}  {row['ranked'][:3]}")
    print(f"\n-> {args.out}")


if __name__ == "__main__":
    main()
