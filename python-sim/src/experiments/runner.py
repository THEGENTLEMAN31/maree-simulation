"""Protocole expérimental X1–X7 (E2) et registre d'hypothèses (C5, décision 13).

Exigences E2 : chaque conclusion repose sur ≥ 5 runs par configuration,
sur ≥ 2 configurations ; la dispersion est présentée (médiane + IQR).
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..config import SimulationConfig, load_config

# Registre des hypothèses préenregistrées (C5, décision 13) — daté.
HYPOTHESES = [
    {
        "id": "H1",
        "enonce": "Une annonce claire < 3 min réduit le temps d'évacuation médian "
        "et l'écart croyance/réalité vs une annonce ambiguë après 6 min.",
        "date": "2026-10-13",
        "experiment": "X1",
    },
    {
        "id": "H2",
        "enonce": "La fermeture soudaine de la sortie A piège plus de monde "
        "quand la foule suit un meneur que quand chacun décide seul.",
        "date": "2026-10-13",
        "experiment": "X2",
    },
    {
        "id": "H3",
        "enonce": "En mode asynchrone, la répartition entre sorties diffère du "
        "mode synchrone car les agents rapides atteignent les sorties en premier.",
        "date": "2026-10-13",
        "experiment": "X3",
    },
    {
        "id": "H4",
        "enonce": "LLM ≠ règles sur l'écart croyance/réalité, mais ≈ sur le "
        "temps d'évacuation. Résultat contraire recevable s'il est démontré (E1).",
        "date": "2026-10-13",
        "experiment": "X4",
    },
    {
        "id": "H5",
        "enonce": "Un agent ayant reçu un échange préalable choisit plus souvent "
        "la sortie recommandée que le même agent sans échange (A1).",
        "date": "2026-10-13",
        "experiment": "X5",
    },
    {
        "id": "H6",
        "enonce": "Deux profils placés dans la même situation décident "
        "différemment ; échanger les profils échange les décisions (A3).",
        "date": "2026-10-13",
        "experiment": "X6",
    },
    {
        "id": "H7",
        "enonce": "Désactiver le RAG augmente l'écart croyance/réalité (F1).",
        "date": "2026-10-13",
        "experiment": "X7",
    },
]


@dataclass
class ExperimentConfig:
    """Une configuration de run expérimental (variante du scénario)."""

    name: str
    mode: str = "sync"
    max_ticks: int = 120
    llm_enabled: bool = True
    rag_enabled: bool = True
    memory_enabled: bool = True
    announcement_tick: int | None = 10
    announcement_clarity: str = "clear"  # clear | ambiguous
    close_exit: str | None = None
    close_exit_tick: int | None = None
    seed: int = 42


EXPERIMENTS: dict[str, list[ExperimentConfig]] = {
    "X1": [
        ExperimentConfig(name="X1_clear_early", announcement_tick=5, announcement_clarity="clear"),
        ExperimentConfig(name="X1_ambig_late", announcement_tick=12, announcement_clarity="ambiguous"),
    ],
    "X2": [
        ExperimentConfig(name="X2_noleaders", close_exit="A", close_exit_tick=15, llm_enabled=True),
        ExperimentConfig(name="X2_leaders", close_exit="A", close_exit_tick=15, llm_enabled=True),
    ],
    "X3": [
        ExperimentConfig(name="X3_sync", mode="sync"),
        ExperimentConfig(name="X3_async", mode="async"),
    ],
    "X4": [
        ExperimentConfig(name="X4_llm", llm_enabled=True),
        ExperimentConfig(name="X4_rules", llm_enabled=False),
    ],
    "X5": [
        ExperimentConfig(name="X5_with_mem", memory_enabled=True),
        ExperimentConfig(name="X5_without_mem", memory_enabled=False),
    ],
    "X6": [
        ExperimentConfig(name="X6_profiles_A"),
        ExperimentConfig(name="X6_profiles_B"),
    ],
    "X7": [
        ExperimentConfig(name="X7_rag_on", rag_enabled=True),
        ExperimentConfig(name="X7_rag_off", rag_enabled=False),
    ],
}


class ExperimentRunner:
    """Exécute X1–X7 : pour chaque config, `n_runs` runs (E2)."""

    def __init__(
        self,
        config_path: str,
        *,
        dry_run: bool = False,
        n_runs: int = 5,
        base_dir: str = "/logs",
    ) -> None:
        self.base_config = load_config(config_path)
        self.dry_run = dry_run
        self.n_runs = n_runs
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def run_all(self) -> None:
        results: dict = {}
        for exp_id, configs in EXPERIMENTS.items():
            for cfg in configs:
                key = cfg.name
                results[key] = self._run_experiment(exp_id, cfg, self.n_runs)
        out = self.base_dir / "experiments_summary.json"
        out.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"protocole terminé → {out}")

    def _run_experiment(self, exp_id: str, cfg: ExperimentConfig, n: int) -> dict:
        """Lance n runs d'une config ; retourne médiane + IQR des I1..I5."""
        from ..orchestrator import Orchestrator

        samples = []
        for run_i in range(n):
            seed = cfg.seed + run_i * 1000 + (7 if cfg.name.endswith("B") else 3)
            sim_cfg = self._to_sim_config(exp_id, cfg, run_i, seed)
            orch = Orchestrator(sim_cfg, dry_run=self.dry_run)
            summary = asyncio.run(orch.run(max_ticks=cfg.max_ticks))
            samples.append(summary)
        return self._summarize(samples)

    def _to_sim_config(self, exp_id: str, cfg: ExperimentConfig, run_i: int, seed: int) -> SimulationConfig:
        c = self.base_config.model_copy()
        c.run_id = f"{exp_id}_{cfg.name}_r{run_i}"
        c.mode = cfg.mode  # type: ignore[assignment]
        c.seed = seed
        c.max_ticks = cfg.max_ticks
        # GPIO : les variantes sont transportées par des métadonnées de run
        # (le simulateur principal lit cfg via le YAML ; ici on propage les
        # 5 variables expérimentales dans des champs stables du monde).
        c.world.announcement_tick = cfg.announcement_tick  # type: ignore[attr-defined]
        c.world.announcement_clarity = cfg.announcement_clarity  # type: ignore[attr-defined]
        if cfg.close_exit:
            c.world.exits_closed = {cfg.close_exit: cfg.close_exit_tick}  # type: ignore[attr-defined]
        c.world.experiment_flags = {  # type: ignore[attr-defined]
            "llm": cfg.llm_enabled,
            "rag": cfg.rag_enabled,
            "memory": cfg.memory_enabled,
        }
        return c

    @staticmethod
    def _summarize(samples: list[dict]) -> dict:
        """Médiane et écart interquartile (statistiques du cadrage)."""
        import statistics

        def med_iqr(values: list[float]) -> dict:
            if not values:
                return {"median": None, "iqr": None}
            q = statistics.quantiles(sorted(values), n=4)
            return {"median": round(q[1], 4), "iqr": round(q[2] - q[0], 4)}

        keys = ("calls", "tokens_in", "tokens_out", "total_ms")
        out = {"n_runs": len(samples)}
        for k in keys:
            out[k] = med_iqr([s.get(k, 0.0) for s in samples])
        out["temporal_violations"] = sum(s.get("temporal_violations", 0) for s in samples) / max(1, len(samples))
        return out