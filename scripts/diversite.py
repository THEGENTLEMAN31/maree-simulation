"""B3, troisième contrôle : la diversité des justifications.

Le cahier des charges demande de démontrer que l'indicateur d'émergence
« distingue un run où un contexte commun émerge d'un run où il n'émerge
pas ». Le contrôle évident est de couper la communication (X8, fait).
Mais il reste une objection : et si les agents ne faisaient que
**paraphraser le même modèle** ? Un seul modèle produirait alors des
justifications quasi identiques, et « consensus » ne voudrait rien dire
de plus que « même gabarit de prompt ».

Ce script mesure la distance cosinus entre les justifications d'un run :

  * **intra-modèle** — deux décisions du même modèle ;
  * **inter-modèle** — deux décisions de modèles différents.

Lecture :

  * si intra ≈ inter, un seul modèle produit déjà des justifications
    aussi variées que deux modèles entre eux : la diversité n'est pas un
    artefact de gabarit, et I1 mesure autre chose ;
  * si intra << inter, la convergence peut venir du modèle, et il faut
    le dire.

Usage ::

    uv run python scripts/diversite.py --pattern 'run_x12_deux_tiers_s*'
    uv run python scripts/diversite.py --pattern 'run_x12_deux_tiers_s*' \
        --url http://$(docker inspect maree-llama-cpp --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'):8080/v1
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import math
import os
import statistics
from collections import Counter, defaultdict


def load_reasons(pattern: str, runs: str) -> list[tuple[str, str]]:
    """(modèle rendu, justification) pour chaque décision LLM lisible."""
    items: list[tuple[str, str]] = []
    paths = sorted(glob.glob(os.path.join(runs, pattern, "events.jsonl")))
    if not paths:
        raise SystemExit(f"aucun journal pour {pattern!r} dans {runs}/")
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") != "agent.decision":
                    continue
                data = event.get("data") or {}
                if data.get("kind") != "llm":
                    continue
                reason = str(data.get("reason") or "").strip()
                model = str((data.get("llm") or {}).get("model") or "?")
                # Une justification de moins de huit caractères n'apprend
                # rien (et polluerait la distance).
                if len(reason) < 8:
                    continue
                items.append((model, reason))
    return items


async def embed_all(url: str, texts: list[str], batch: int = 24) -> list[list[float]]:
    from maree.adapters.llm import LlamaCppLLM

    llm = LlamaCppLLM(base_url=url)
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), batch):
            vectors.extend(await llm.embed(texts[start : start + batch]))
    finally:
        await llm.close()
    return vectors


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def distances(vectors: list[list[float]], labels: list[str]) -> tuple[list[float], list[float]]:
    intra: list[float] = []
    inter: list[float] = []
    n = len(vectors)
    for i in range(n):
        for j in range(i + 1, n):
            d = 1.0 - cosine(vectors[i], vectors[j])
            (intra if labels[i] == labels[j] else inter).append(d)
    return intra, inter


def describe(values: list[float]) -> str:
    if not values:
        return "—"
    ordered = sorted(values)
    return (
        f"n={len(values)}  moyenne {statistics.fmean(values):.3f}  "
        f"médiane {statistics.median(values):.3f}  "
        f"[{ordered[0]:.3f} – {ordered[-1]:.3f}]"
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pattern",
        default="run_x12_deux_tiers_s*",
        help="motif de répertoires de runs (glob sous --runs)",
    )
    parser.add_argument("--runs", default="runs")
    parser.add_argument(
        "--url",
        default=os.environ.get("MAREE_LLM_URL", "http://127.0.0.1:8080/v1"),
        help="base URL OpenAI-compatible pour bge-m3 (défaut : MAREE_LLM_URL)",
    )
    args = parser.parse_args()

    items = load_reasons(args.pattern, args.runs)
    models = Counter(model for model, _ in items)
    print(f"justifications LLM : {len(items)}")
    for model, count in models.most_common():
        print(f"  {model:<16} {count}")
    if len(items) < 4:
        raise SystemExit("pas assez de justifications pour conclure")

    texts = [reason for _, reason in items]
    print(f"embeddings via {args.url} …")
    vectors = await embed_all(args.url, texts)
    if len(vectors) != len(texts):
        raise SystemExit("le serveur n'a pas renvoyé un vecteur par texte")

    labels = [model for model, _ in items]
    intra, inter = distances(vectors, labels)
    print()
    print("intra-modèle :", describe(intra))
    print("inter-modèle :", describe(inter))

    by_model: dict[str, list[int]] = defaultdict(list)
    for index, label in enumerate(labels):
        by_model[label].append(index)
    for model, indexes in sorted(by_model.items()):
        if len(indexes) < 2:
            continue
        sub = [vectors[i] for i in indexes]
        inside, _ = distances(sub, [model] * len(sub))
        print(f"  {model:<16} intra : {describe(inside)}")

    if intra and inter:
        med_intra = statistics.median(intra)
        med_inter = statistics.median(inter)
        ratio = med_intra / med_inter if med_inter else float("inf")
        print()
        print(f"rapport des médianes intra/inter : {ratio:.2f}")
        if ratio >= 0.8:
            print(
                "→ la diversité intra-modèle est du même ordre que "
                "l'inter-modèle : la variété des justifications ne vient "
                "pas d'un seul gabarit de modèle."
            )
        else:
            print(
                "→ intra nettement plus faible : une part de la convergence "
                "peut venir du modèle. À discuter, ne pas masquer."
            )
    else:
        print()
        print(
            "→ un seul modèle dans cet échantillon : le contrôle "
            "inter-modèle n'est pas possible ici (utiliser un run "
            "`deux_tiers`)."
        )


if __name__ == "__main__":
    asyncio.run(main())
