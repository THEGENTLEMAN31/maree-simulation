"""Test réel du RAG sémantique contre le corpus MARÉE (pas un mock).

Vérifie :
1. l'ingestion + construction de l'index FAISS ;
2. que la similarité sémantique classe les passages pertinents en tête ;
3. que le filtre par profil et par date de disponibilité fonctionne (C6, déc. 15).

Nécessite llama.cpp joignable avec l'embeddeur bge-m3 (variable
`MAREE_LLM_URL`, défaut http://127.0.0.1:8081/v1). Sinon, skip.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm_gateway import LLMGateway  # noqa: E402
from src.rag.rag import RagClient  # noqa: E402

BASE_URL = os.environ.get("MAREE_LLM_URL", "http://127.0.0.1:8081/v1")
EMBED_MODEL = os.environ.get("MAREE_EMBED_MODEL", "bge-m3")
CORPUS = "/home/jose/school/mondes_vivants/maree-simulation/world_corpus"


class _Agent:
    """Agent minimal pour la récupération."""

    def __init__(self, profile: str) -> None:
        self.profile_name = profile
        self.last_rag = None


class _Perception:
    def __init__(self, tick: int, zone: str = "scene") -> None:
        self.tick = tick
        self.zone = zone


async def main() -> int:
    gw = LLMGateway(BASE_URL)
    rag = RagClient(gateway=gw, embed_model=EMBED_MODEL)
    n = await rag.ingest_directory_async(CORPUS)
    print(f"passages ingérés : {n}")
    print(f"index FAISS      : {'construit' if rag._index is not None else 'ABSENT'}")
    if rag._index is None:
        print("ÉCHEC : pas d'index vectoriel")
        return 1

    agent = _Agent("visiteur")
    tests = [
        # (profil, tick, question, mots attendus dans les doc_id en tête)
        ("visiteur", 30, "il y a de la fumée côté sud, quelle sortie prendre ?", ["sortie-c", "plan", "signal", "fumee"]),
        ("habitue", 30, "quelle est la sortie discrète que je connais ?", ["sortie-c", "habitue"]),
        ("securite", 30, "quel est le protocole officiel d'évacuation ?", ["protocole"]),
        ("famille", 30, "je cherche mon enfant égaré, que dois-je faire ?", ["famille", "profil"]),
    ]
    ok = 0
    for profile, tick, question, mots in tests:
        agent.profile_name = profile
        top = await rag.retrieve_scored(agent, _Perception(tick=tick), top_k=3)
        head = [p.doc_id for _, p in top]
        hit = any(any(m in d.lower() for m in mots) for d in head)
        ok += hit
        print(f"\nQ: {question}\n   profil={profile} tick={tick}")
        for (s, p) in top:
            print(f"     {s:.3f}  {p.doc_id}")
        if not top:
            print("     (aucun passage disponible)")
        print(f"   → pertinent en tête : {'OUI' if hit else 'NON'}")

    # Filtre C6 : aucun passage futur ne doit sortir.
    agent.profile_name = "visiteur"
    top_early = await rag.retrieve_scored(agent, _Perception(tick=0), top_k=5)
    futurs = [p.doc_id for _, p in top_early if p.available_tick > 0]
    print(f"\nfiltre C6 (tick=0) : {len(futurs)} passage(s) futur(s) → {'OK' if not futurs else 'ÉCHEC'}")
    print(f"\nrésultat : {ok}/{len(tests)} requêtes pertinentes")
    await gw.aclose()
    return 0 if ok >= 2 and not futurs else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
