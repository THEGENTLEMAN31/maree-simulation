"""F3 — l'état courant a son propre domicile, et F5 — les requêtes reproductibles.

Deux tests de stockage, pas de moteur : ce qui est vérifié ici est
l'endroit où vivent les données et la façon dont on les interroge, pas la
simulation qui les produit.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import duckdb
import pytest
import yaml

from maree.adapters.bus import InMemoryBus
from maree.adapters.journal.jsonl import JsonlJournal
from maree.adapters.state import JsonStateStore
from maree.domain.geometry import Plan
from maree.engine.simulation import PopulationEntry, RunConfig, Simulation
from maree.memory.store import EventSourcedMemory
from maree.ports import LLMResult


class _NoLLM:
    async def chat(self, messages, *, seed, **kwargs) -> LLMResult:
        return LLMResult(text="{}", prompt="", seed=seed, model="x", ok=False)

    async def embed(self, texts):
        return []


def test_f3_l_etat_est_remplace_et_ne_garde_que_le_dernier(tmp_path: Path) -> None:
    """Un fichier par run, remplacé : l'histoire reste dans le journal."""
    store = JsonStateStore(tmp_path)
    assert store.load("r1") is None

    store.save("r1", {"tick": 1, "agents": [{"id": "A01"}]})
    assert store.load("r1")["tick"] == 1

    store.save("r1", {"tick": 2, "agents": [{"id": "A01"}]})
    snapshot = store.load("r1")
    assert snapshot["tick"] == 2
    # Rétention = dernière valeur seulement : pas d'historique parallèle.
    assert "tick" not in json.loads(store.path_for("r1").read_text()).get(
        "historique", {}
    )
    assert store.runs() == ["r1"]
    # Le fichier temporaire d'écriture ne doit pas traîner.
    assert not list(tmp_path.glob("*/state.json.tmp"))


def test_f3_la_simulation_ecrit_l_etat_courant(tmp_path: Path) -> None:
    """Le moteur alimente le magasin à chaque instantané."""
    plan = Plan.from_dict(
        yaml.safe_load(Path("configs/world/port_aubel.yaml").read_text("utf-8"))
    )
    journal = JsonlJournal(tmp_path)
    store = JsonStateStore(tmp_path)
    simulation = Simulation(
        config=RunConfig(
            run_id="f3",
            seed=0,
            max_ticks=8,
            smoke_tick=3,
            smoke_position=(44.0, 15.0),
            population=(PopulationEntry("habitue", 4, "rules"),),
        ),
        plan=plan,
        physics=__import__(
            "tests.test_simulation", fromlist=["FakePhysics"]
        ).FakePhysics(plan),
        llm=_NoLLM(),
        retriever=None,
        memory=EventSourcedMemory(n_exits=len(plan.exits)),
        journal=journal,
        bus=InMemoryBus(),
        narrator=None,
        state_store=store,
    )
    asyncio.run(simulation.run())

    snapshot = store.load("f3")
    assert snapshot is not None
    assert snapshot["tick"] >= 1
    assert len(snapshot["agents"]) == 4
    # L'état est plus petit que le journal : c'est tout l'intérêt.
    assert store.path_for("f3").stat().st_size < journal.path_for("f3").stat().st_size


def _run_sql(sql_file: Path, runs_dir: Path) -> list[tuple]:
    """Exécute une requête de `queries/` sur un répertoire de runs donné."""
    base = (Path("queries") / "_base.sql").read_text("utf-8").replace(
        "'runs/*/events.jsonl'", f"'{runs_dir}/*/events.jsonl'"
    )
    con = duckdb.connect()
    try:
        con.execute(base)
        return con.execute(sql_file.read_text("utf-8")).fetchall()
    finally:
        con.close()


@pytest.mark.skipif(
    not Path("queries/runs.sql").exists(), reason="requêtes absentes"
)
def test_f5_une_requete_compte_les_runs_sans_inference_de_schema(
    tmp_path: Path,
) -> None:
    """F5 — la même requête sur deux runs, avec des `data` de formes différentes.

    Le piège que ce test garde : `data` change de forme à chaque type
    d'événement. Une lecture qui infère un schéma commun sur cent runs
    finit par convertir silencieusement une décision en chaîne, et le
    compte devient faux sans erreur.
    """
    for run_id, ticks in (("run_a", 2), ("run_b", 3)):
        path = tmp_path / run_id / "events.jsonl"
        path.parent.mkdir(parents=True)
        events = [
            {
                "seq": 1,
                "run_id": run_id,
                "type": "run.started",
                "t_prod": 0,
                "t_trait": 0,
                "t_real": 0.0,
                "data": {"seed": 0, "population": []},
            },
            {
                "seq": 2,
                "run_id": run_id,
                "type": "agent.decision",
                "t_prod": 1,
                "t_trait": 1,
                "t_real": 0.5,
                "data": {
                    "agent_id": "A01",
                    "kind": "llm",
                    "llm": {"tier": "big", "model": "gemma", "tokens_in": 10},
                },
            },
        ]
        for tick in range(1, ticks + 1):
            events.append(
                {
                    "seq": 2 + tick,
                    "run_id": run_id,
                    "type": "metrics.indicators",
                    "t_prod": tick,
                    "t_trait": tick,
                    "t_real": float(tick),
                    "data": {"I3_evacuated": 0.5, "I7_delay_seconds": 10.0 * tick},
                }
            )
        events.append(
            {
                "seq": 100,
                "run_id": run_id,
                "type": "run.ended",
                "t_prod": ticks,
                "t_trait": ticks,
                "t_real": float(ticks),
                "data": {},
            }
        )
        path.write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
        )

    rows = _run_sql(Path("queries/runs.sql"), tmp_path)
    by_run = {row[0]: row for row in rows}
    assert set(by_run) == {"run_a", "run_b"}
    # ticks, termine, I3, I7, decisions, decisions_llm, incidents, mural
    assert by_run["run_a"][1] == 2
    assert by_run["run_b"][1] == 3
    assert all(row[2] == 1 for row in rows)
    # I7 est comparé numériquement, pas comme une chaîne : « 30.0 » ne doit
    # pas battre « 100.0 ».
    assert by_run["run_b"][4] == pytest.approx(30.0)

    models = _run_sql(Path("queries/appels_par_modele.sql"), tmp_path)
    assert {row[2] for row in models} == {"gemma"}
    assert all(row[3] == 1 for row in models)


@pytest.mark.skipif(
    not Path("queries/runs.sql").exists(), reason="requêtes absentes"
)
def test_f5_les_requetes_du_depot_sont_executables() -> None:
    """Toutes les requêtes livrées tournent : une requête cassée ne se voit pas
    à la lecture, elle se voit au rapport."""
    queries = sorted(
        p for p in Path("queries").glob("*.sql") if p.stem != "_base"
    )
    assert len(queries) >= 4
    runs = Path("runs")
    if not runs.exists() or not any(runs.glob("*/events.jsonl")):
        pytest.skip("aucun run local")
    for query in queries:
        # Ne lève pas : c'est tout ce qui est demandé ici.
        _run_sql(query, runs)


def test_f5_le_dossier_queries_est_versionne() -> None:
    """Les requêtes sont du code : elles vivent dans le dépôt, pas dans un shell."""
    assert Path("queries/_base.sql").exists()
    assert (Path("queries") / "runs.sql").exists()
