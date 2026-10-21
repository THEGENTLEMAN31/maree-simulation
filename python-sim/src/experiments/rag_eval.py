"""Évaluation F2 du RAG : précision@1, précision@3 et MRR.

Exigence F2 : la qualité de la récupération est **mesurée**, pas supposée.
L'échantillon ci-dessous est annoté à la main (document attendu pour chaque
question), avec le profil autorisé à le retrouver (décision 15).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from ..llm_gateway import LLMGateway
from ..rag.rag import RagClient


@dataclass
class QueryCase:
    query: str
    profile: str
    expected: str  # sous-chaîne du doc_id attendu


# 30 cas : questions réalistes d'agents, réparties sur les 5 collections.
CASES: list[QueryCase] = [
    # annonces
    QueryCase("quelle annonce indique une sortie précise ?", "visiteur", "annonces/claire"),
    QueryCase("y a-t-il eu une annonce ambiguë qui ne dit pas quoi faire ?", "famille", "ambigue"),
    QueryCase("est-ce que la sortie B est condamnée ?", "amis", "annonces/rumeur"),
    QueryCase("le message du haut-parleur parle de rester calme", "visiteur", "ambigue"),
    QueryCase("on nous dit d'évacuer par la sortie la plus proche", "famille", "annonces/claire"),
    # consignes
    QueryCase("quel est le protocole officiel en cas de fumée ?", "securite", "consignes_securite/protocole"),
    QueryCase("qui prévient la régie et comment ?", "securite", "consignes_securite/protocole-etape"),
    QueryCase("que faire en cas de départ de feu dans une tente ?", "securite", "consignes_securite/fiche-incident"),
    QueryCase("quelle est la capacité de la sortie A ?", "securite", "consignes_securite/fiche-sortie-A"),
    QueryCase("que faire si la sortie B est fermée ?", "securite", "consignes_securite/fiche-sortie-B"),
    QueryCase("combien d'agents faut-il pour tenir la zone ouest ?", "securite", "consignes_securite/consigne-zone"),
    QueryCase("comment déclarer la fin de l'évacuation ?", "securite", "consignes_securite/protocole-etape"),
    # plan / signalétique
    QueryCase("où se trouve la passerelle sur le plan ?", "habitue", "plan_signalétique/plan-zone-passerelle"),
    QueryCase("quel est le chemin le plus court vers la sortie C ?", "habitue", "plan_signalétique/cheminement-C"),
    QueryCase("la sortie A est-elle large ?", "visiteur", "plan_signalétique/plan-zone-sortie_a"),
    QueryCase("où sont les panneaux lumineux de secours ?", "securite", "plan_signalétique/signaletique"),
    QueryCase("quelle zone mène directement à la sortie B ?", "habitue", "plan_signalétique/plan-zone-passerelle"),
    QueryCase("combien de temps pour rejoindre la sortie depuis la scène ?", "visiteur", "plan_signalétique/cheminement"),
    QueryCase("quelles zones sont reliées à la scène ?", "visiteur", "plan_signalétique/plan-zone-scene"),
    # savoirs profils
    QueryCase("je suis un habitué, quelle sortie je prends d'habitude ?", "habitue", "savoir_profils/habitue"),
    QueryCase("je connais le protocole et les points de blocage", "securite", "savoir_profils/securite"),
    QueryCase("j'ai un enfant en bas âge, comment je le garde ?", "famille", "savoir_profils/famille"),
    QueryCase("c'est ma première fois ici, je ne connais pas les sorties", "visiteur", "savoir_profils/visiteur"),
    QueryCase("nous sommes un groupe d'amis et on filme", "amis", "savoir_profils/amis"),
    QueryCase("la poussette passe-t-elle sur la passerelle ?", "famille", "savoir_profils/famille"),
    # souvenirs
    QueryCase("que s'est-il passé lors de l'édition 2023 ?", "visiteur", "souvenirs_editions/2023"),
    QueryCase("une sortie avait été fermée sans explication, c'était quand ?", "habitue", "souvenirs_editions/"),
    QueryCase("l'année où il y a eu une bousculade près de la sortie A", "amis", "souvenirs_editions/2023"),
    QueryCase("l'édition avec des travaux qui fermaient une sortie", "habitue", "souvenirs_editions/2024"),
    QueryCase("le souvenir d'une fumée de barbecue", "famille", "souvenirs_editions/2022"),
]


class _Agent:
    def __init__(self, profile: str) -> None:
        self.profile_name = profile
        self.last_rag = None


class _Perception:
    def __init__(self, tick: int) -> None:
        self.tick = tick
        self.zone = "scene"


async def evaluate(
    corpus_path: str, base_url: str, *, model: str = "bge-m3", top_k: int = 3
) -> dict:
    gw = LLMGateway(base_url)
    rag = RagClient(gateway=gw, embed_model=model)
    n = await rag.ingest_directory_async(corpus_path)
    try:
        hits1 = hits3 = 0
        rr = 0.0
        details = []
        for case in CASES:
            agent = _Agent(case.profile)
            top = await rag.retrieve_scored(
                agent, _Perception(tick=10_000), top_k=top_k, query=case.query
            )
            ids = [p.doc_id for _, p in top]
            rank = next(
                (i + 1 for i, d in enumerate(ids) if case.expected in d), None
            )
            hits1 += 1 if rank == 1 else 0
            hits3 += 1 if rank and rank <= 3 else 0
            rr += 1.0 / rank if rank else 0.0
            details.append(
                {
                    "query": case.query,
                    "profile": case.profile,
                    "expected": case.expected,
                    "rank": rank,
                    "top3": ids,
                }
            )
        n_cases = len(CASES)
        return {
            "passages": n,
            "n_queries": n_cases,
            "precision_at_1": round(hits1 / n_cases, 3),
            "precision_at_3": round(hits3 / n_cases, 3),
            "mrr": round(rr / n_cases, 3),
            "degraded": rag.degraded,
            "details": details,
        }
    finally:
        await gw.aclose()


if __name__ == "__main__":
    import sys

    corpus = sys.argv[1] if len(sys.argv) > 1 else "world_corpus"
    url = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:18081/v1"
    res = asyncio.run(evaluate(corpus, url))
    print(json.dumps({k: v for k, v in res.items() if k != "details"}, indent=2))
    Path("/tmp/f2_details.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
