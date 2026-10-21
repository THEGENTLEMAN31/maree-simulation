"""Non-régression du socle expérimental (E2, B2, F5).

Ces tests vérifient les propriétés dont dépendent les conclusions :
- chaque paire X1–X7 diffère par un levier réellement câblé ;
- le test de Mann-Whitney exact donne les valeurs attendues ;
- le résumé d'un run contient bien I1–I5 et la distribution des sorties ;
- le rapport se génère et ne contient plus de conclusion « à rédiger ».
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from src.experiments.report import mann_whitney_exact, build_report
from src.experiments.runner import (
    EXPERIMENTS,
    ExperimentRunner,
    validate_experiments,
)


def test_protocole_paires_distinctes() -> None:
    """Aucune expérience ne doit comparer deux configurations identiques."""
    assert validate_experiments() == []
    assert set(EXPERIMENTS) == {"X1", "X2", "X3", "X4", "X5", "X6", "X7"}


def test_chaque_paire_change_un_levier() -> None:
    """Le levier modifié doit être réellement transmis à l'orchestrateur."""
    for exp_id, cfgs in EXPERIMENTS.items():
        a, b = cfgs
        fa, fb = a.flags(), b.flags()
        changed = {k for k in set(fa) | set(fb) if fa.get(k) != fb.get(k)}
        changed |= {k for k in ("mode", "announcement_tick", "announcement_clarity",
                                "close_exit", "close_exit_tick")
                    if getattr(a, k) != getattr(b, k)}
        assert changed, f"{exp_id} ne change aucun paramètre"


def test_mann_whitney_separation_complete() -> None:
    """Séparation totale sur 5 vs 5 : p exacte = 2/252."""
    res = mann_whitney_exact([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
    assert res["U"] == 0.0
    assert res["p"] == pytest.approx(2 / 252, abs=1e-4)
    assert res["r"] == 1.0


def test_mann_whitney_echantillons_identiques() -> None:
    """Aucune séparation : p = 1, effet nul."""
    res = mann_whitney_exact([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert res["p"] == pytest.approx(1.0)
    assert res["r"] == pytest.approx(0.0, abs=1e-9)


def test_summarize_expose_indicateurs_et_sorties() -> None:
    """Le résumé doit porter I1–I5, la distribution des sorties et les bruts."""
    samples = [
        {
            "run_id": f"r{i}",
            "I1_median": 0.4 + i * 0.01,
            "I1_final": 0.5,
            "I2_median": 0.3,
            "I2_final": 0.3,
            "I3_evacuated_ratio": 0.75,
            "I4_median": 0.6,
            "rag_citation_rate": 0.9,
            "calls": 40,
            "tokens_in": 1000,
            "tokens_out": 200,
            "total_ms": 10_000,
            "llm_drifts": 0,
            "temporal_violations": 0,
            "exit_distribution": {"A": 10, "B": 3},
            "agent_last_exits": {"foule_01": "A"},
        }
        for i in range(5)
    ]
    out = ExperimentRunner._summarize(samples)
    for key in ("I1_median", "I2_median", "I3_evacuated_ratio",
                "I4_median", "rag_citation_rate", "exit_distribution",
                "samples", "temporal_violations"):
        assert key in out
    assert out["exit_distribution"] == {"A": 50, "B": 15}
    assert out["I2_median"]["median"] == pytest.approx(0.3)
    assert len(out["samples"]) == 5


def test_rapport_sans_conclusion_a_rediger(tmp_path: Path) -> None:
    """Le rapport est rédigé et contient les tableaux attendus."""
    summary = {
        "X1_clear_early": {
            "n_runs": 5,
            "I1_median": {"median": 0.8, "iqr": 0.1, "min": 0.7, "max": 0.9},
            "I2_median": {"median": 0.1, "iqr": 0.05, "min": 0.05, "max": 0.2},
            "I3_evacuated_ratio": {"median": 0.9, "iqr": 0.0, "min": 0.9, "max": 0.9},
            "I4_median": {"median": 0.5, "iqr": 0.1, "min": 0.4, "max": 0.6},
            "rag_citation_rate": {"median": 1.0, "iqr": 0.0, "min": 1.0, "max": 1.0},
            "exit_distribution": {"A": 20},
            "temporal_violations": 0,
            "samples": [
                {"I2_median": 0.05, "I3_evacuated_ratio": 0.9, "I4_median": 0.4}
                for _ in range(5)
            ],
        },
        "X1_ambig_late": {
            "n_runs": 5,
            "I1_median": {"median": 0.3, "iqr": 0.1, "min": 0.2, "max": 0.4},
            "I2_median": {"median": 0.7, "iqr": 0.1, "min": 0.6, "max": 0.8},
            "I3_evacuated_ratio": {"median": 0.5, "iqr": 0.1, "min": 0.4, "max": 0.6},
            "I4_median": {"median": 0.8, "iqr": 0.1, "min": 0.7, "max": 0.9},
            "rag_citation_rate": {"median": 0.0, "iqr": 0.0, "min": 0.0, "max": 0.0},
            "exit_distribution": {"B": 20},
            "temporal_violations": 0,
            "samples": [
                {"I2_median": 0.6, "I3_evacuated_ratio": 0.5, "I4_median": 0.9}
                for _ in range(5)
            ],
        },
    }
    (tmp_path / "experiments_summary.json").write_text(
        json.dumps(summary), encoding="utf-8"
    )
    (tmp_path / "rag_eval.json").write_text(
        json.dumps(
            {
                "passages": 209,
                "n_queries": 30,
                "precision_at_1": 0.733,
                "precision_at_3": 0.867,
                "mrr": 0.8,
                "degraded": False,
                "details": [],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "report.md"
    tests = build_report(str(tmp_path), str(out))
    text = out.read_text(encoding="utf-8")
    assert "## Conclusion" in text
    assert "à rédiger" not in text
    assert "Précision@1" in text and "0.733" in text
    assert tests["X1"]["p"] == pytest.approx(2 / 252, abs=1e-4)
    # La séparation est complète : la conclusion doit soutenir l'hypothèse.
    assert "Hypothèses soutenues" in text


def test_corpus_f1_complet() -> None:
    """F1 : le corpus doit tenir la barre du cadrage (≥ 200 passages, 5 collections)."""
    root = Path(__file__).resolve().parents[2] / "world_corpus"
    files = sorted(root.rglob("*.md"))
    assert len(files) >= 200, f"corpus trop petit : {len(files)} passages"
    collections = {f.parent.name for f in files}
    assert collections == {
        "annonces",
        "consignes_securite",
        "plan_signalétique",
        "savoir_profils",
        "souvenirs_editions",
    }
    for f in files:
        head = f.read_text(encoding="utf-8").split("---")[1]
        for key in ("title:", "available_tick:", "allowed_profiles:", "importance:"):
            assert key in head, f"{f} : en-tête incomplet ({key})"


@pytest.mark.asyncio
async def test_ws_client_tardif_recoit_etat_courant() -> None:
    """Un client qui se connecte après le début du run ne voit pas un écran vide.

    Régression e2e : un run court pouvait se terminer avant la connexion
    Godot ; les indicateurs n'étaient alors jamais reçus.
    """
    import json

    import websockets

    from src.ws_server import WSRelay

    server = WSRelay(host="127.0.0.1", port=0)
    server._server = await websockets.serve(server._handler, "127.0.0.1", 0)
    port = server._server.sockets[0].getsockname()[1]
    await server.broadcast({"type": "state", "tick": 3, "agents": []})
    async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
        first = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        assert first["type"] == "state"
        assert first["tick"] == 3
    await server.close()
