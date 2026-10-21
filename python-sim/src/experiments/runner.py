"""Protocole expérimental X1–X7 (E2) et registre d'hypothèses (C5, décision 13).

Exigences E2 : chaque conclusion repose sur ≥ 5 runs par configuration,
sur ≥ 2 configurations ; la dispersion est présentée (médiane + IQR).

Chaque paire de configurations doit différer par **un seul levier** réellement
câblé dans l'orchestrateur (`_apply_experiment_levers`, `_seed_pre_exchanges`,
`_run_agent_turns`). Une paire identique ne mesure rien : c'est vérifié par
`validate_experiments()` et par le test `test_experiments_paires_distinctes`.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
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
        "indicateurs": ["I2", "I3"],
    },
    {
        "id": "H2",
        "enonce": "La fermeture soudaine de la sortie A piège plus de monde "
        "quand la foule suit un meneur que quand chacun décide seul.",
        "date": "2026-10-13",
        "experiment": "X2",
        "indicateurs": ["I3", "I4"],
    },
    {
        "id": "H3",
        "enonce": "En mode asynchrone, la répartition entre sorties diffère du "
        "mode synchrone car les agents rapides atteignent les sorties en premier.",
        "date": "2026-10-13",
        "experiment": "X3",
        "indicateurs": ["I1", "I3"],
    },
    {
        "id": "H4",
        "enonce": "LLM ≠ règles sur l'écart croyance/réalité, mais ≈ sur le "
        "temps d'évacuation. Résultat contraire recevable s'il est démontré (E1).",
        "date": "2026-10-13",
        "experiment": "X4",
        "indicateurs": ["I1", "I2", "I3", "I4"],
    },
    {
        "id": "H5",
        "enonce": "Un agent ayant reçu un échange préalable choisit plus souvent "
        "la sortie recommandée que le même agent sans échange (A1).",
        "date": "2026-10-13",
        "experiment": "X5",
        "indicateurs": ["sortie choisie", "justification citant l'échange"],
    },
    {
        "id": "H6",
        "enonce": "Deux profils placés dans la même situation décident "
        "différemment ; échanger les profils échange les décisions (A3).",
        "date": "2026-10-13",
        "experiment": "X6",
        "indicateurs": ["décision des agents échangés"],
    },
    {
        "id": "H7",
        "enonce": "Désactiver le RAG augmente l'écart croyance/réalité (F1).",
        "date": "2026-10-13",
        "experiment": "X7",
        "indicateurs": ["I2", "part des décisions citant un passage"],
    },
]


@dataclass
class ExperimentConfig:
    """Une configuration de run expérimental (variante du scénario)."""

    name: str
    mode: str = "sync"
    max_ticks: int = 80
    llm_enabled: bool = True
    rag_enabled: bool = True
    memory_enabled: bool = True
    leaders: bool = True
    communication: bool = True
    swap_profiles: list[str] | None = None
    announcement_tick: int | None = None
    announcement_clarity: str = "clear"  # clear | ambiguous
    close_exit: str | None = None
    close_exit_tick: int | None = None
    seed: int = 42

    def flags(self) -> dict:
        """Leviers transmis à l'orchestrateur (world.experiment_flags)."""
        f: dict = {
            "llm": self.llm_enabled,
            "rag": self.rag_enabled,
            "memory": self.memory_enabled,
            "leaders": self.leaders,
            "communication": self.communication,
        }
        if self.swap_profiles:
            f["swap_profiles"] = list(self.swap_profiles)
        return f


# Agents suivis pour X6 (profils échangés). Ce sont des agents LLM existants
# dans la population de `config/simulation.yaml`.
_X6_PAIR = ["securite_01", "visiteur_01"]

EXPERIMENTS: dict[str, list[ExperimentConfig]] = {
    # X1 — clarté et moment de l'annonce (confondus volontairement, cf. cadrage)
    "X1": [
        ExperimentConfig(
            name="X1_clear_early", announcement_tick=5, announcement_clarity="clear"
        ),
        ExperimentConfig(
            name="X1_ambig_late", announcement_tick=40, announcement_clarity="ambiguous"
        ),
    ],
    # X2 — sortie A fermée, avec meneurs vs sans meneur (I4 doit chuter)
    "X2": [
        ExperimentConfig(
            name="X2_leaders",
            close_exit="A",
            close_exit_tick=15,
            leaders=True,
        ),
        ExperimentConfig(
            name="X2_noleaders",
            close_exit="A",
            close_exit_tick=15,
            leaders=False,
        ),
    ],
    # X3 — synchrone vs asynchrone
    "X3": [
        ExperimentConfig(name="X3_sync", mode="sync"),
        ExperimentConfig(name="X3_async", mode="async"),
    ],
    # X4 — LLM vs baseline à règles
    "X4": [
        ExperimentConfig(name="X4_llm", llm_enabled=True),
        ExperimentConfig(name="X4_rules", llm_enabled=False),
    ],
    # X5 — mémoire des échanges préalables (A1)
    "X5": [
        ExperimentConfig(name="X5_with_mem", memory_enabled=True),
        ExperimentConfig(name="X5_without_mem", memory_enabled=False),
    ],
    # X6 — profils échangés entre deux agents (A3)
    "X6": [
        ExperimentConfig(name="X6_profiles_origin"),
        ExperimentConfig(name="X6_profiles_swapped", swap_profiles=_X6_PAIR),
    ],
    # X7 — RAG activé vs désactivé (F1)
    "X7": [
        ExperimentConfig(name="X7_rag_on", rag_enabled=True),
        ExperimentConfig(name="X7_rag_off", rag_enabled=False),
    ],
}


def validate_experiments() -> list[str]:
    """Vérifie que chaque paire diffère par au moins un levier réel.

    Retourne la liste des problèmes (vide = protocole sain). C'est la garantie
    qu'aucune expérience ne mesure « deux fois la même chose ».
    """
    problems: list[str] = []
    for exp_id, configs in EXPERIMENTS.items():
        if len(configs) < 2:
            problems.append(f"{exp_id}: moins de 2 configurations")
            continue
        a, b = configs[0], configs[1]
        signature = (
            a.mode, a.llm_enabled, a.rag_enabled, a.memory_enabled, a.leaders,
            a.communication, tuple(a.swap_profiles or ()),
            a.announcement_tick, a.announcement_clarity,
            a.close_exit, a.close_exit_tick,
        )
        signature_b = (
            b.mode, b.llm_enabled, b.rag_enabled, b.memory_enabled, b.leaders,
            b.communication, tuple(b.swap_profiles or ()),
            b.announcement_tick, b.announcement_clarity,
            b.close_exit, b.close_exit_tick,
        )
        if signature == signature_b:
            problems.append(f"{exp_id}: configurations identiques ({a.name}/{b.name})")
    return problems


class ExperimentRunner:
    """Exécute X1–X7 : pour chaque config, `n_runs` runs (E2)."""

    def __init__(
        self,
        config_path: str,
        *,
        dry_run: bool = False,
        n_runs: int = 5,
        base_dir: str = "/logs",
        only: list[str] | None = None,
        corpus_path: str | None = None,
        llm_base_url: str | None = None,
        kafka_memory: bool | None = None,
    ) -> None:
        self.base_config = load_config(config_path)
        self.dry_run = dry_run
        self.n_runs = n_runs
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.only = only
        self.corpus_path = corpus_path
        self.llm_base_url = llm_base_url
        self.kafka_memory = kafka_memory

    def run_all(self) -> None:
        problems = validate_experiments()
        if problems:
            raise ValueError("protocole invalide : " + "; ".join(problems))

        results: dict = {}
        for exp_id, configs in EXPERIMENTS.items():
            if self.only and exp_id not in self.only:
                continue
            for cfg in configs:
                key = cfg.name
                print(f"[{exp_id}] {cfg.name} — {self.n_runs} runs…", flush=True)
                results[key] = self._run_experiment(exp_id, cfg, self.n_runs)
                print(f"    → {results[key]['n_runs']} runs terminés", flush=True)
        out = self.base_dir / "experiments_summary.json"
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"protocole terminé → {out}")

    def _run_experiment(self, exp_id: str, cfg: ExperimentConfig, n: int) -> dict:
        """Lance n runs d'une config ; retourne médiane + IQR des I1..I5."""
        from ..orchestrator import Orchestrator

        samples = []
        for run_i in range(n):
            seed = cfg.seed + run_i * 1000 + (7 if cfg.name.endswith("B") else 3)
            sim_cfg = self._to_sim_config(exp_id, cfg, run_i, seed)
            kwargs: dict = {"dry_run": self.dry_run}
            if self.corpus_path:
                kwargs["corpus_path"] = self.corpus_path
            if self.llm_base_url:
                kwargs["llm_base_url"] = self.llm_base_url
            if self.kafka_memory is not None:
                kwargs["kafka_memory"] = self.kafka_memory
            orch = Orchestrator(sim_cfg, **kwargs)
            summary = asyncio.run(orch.run(max_ticks=cfg.max_ticks))
            samples.append(summary)
        return self._summarize(samples)

    def _to_sim_config(
        self, exp_id: str, cfg: ExperimentConfig, run_i: int, seed: int
    ) -> SimulationConfig:
        c = self.base_config.model_copy(deep=True)
        c.run_id = f"{exp_id}_{cfg.name}_r{run_i}"
        c.mode = cfg.mode  # type: ignore[assignment]
        c.seed = seed
        c.max_ticks = cfg.max_ticks
        c.log_dir = str(self.base_dir)
        # Les variantes sont transportées par des champs stables du monde
        # (décision 11 : tout paramètre vient de la configuration).
        c.world.announcement_tick = cfg.announcement_tick
        c.world.announcement_clarity = cfg.announcement_clarity  # type: ignore[assignment]
        c.world.exits_closed = (
            {cfg.close_exit: cfg.close_exit_tick} if cfg.close_exit else {}
        )
        c.world.experiment_flags = cfg.flags()
        return c

    @staticmethod
    def _summarize(samples: list[dict]) -> dict:
        """Médiane, IQR et valeurs brutes (E2 : dispersion + Mann-Whitney)."""
        import statistics

        def med_iqr(values: list[float]) -> dict:
            vals = sorted(values)
            if not vals:
                return {"median": None, "iqr": None, "min": None, "max": None}
            if len(vals) < 4:
                return {
                    "median": round(statistics.median(vals), 4),
                    "iqr": round(max(vals) - min(vals), 4),
                    "min": round(min(vals), 4),
                    "max": round(max(vals), 4),
                }
            q = statistics.quantiles(vals, n=4)
            return {
                "median": round(statistics.median(vals), 4),
                "iqr": round(q[2] - q[0], 4),
                "min": round(vals[0], 4),
                "max": round(vals[-1], 4),
            }

        keys = (
            "I1_median",
            "I1_final",
            "I2_median",
            "I2_final",
            "I3_evacuated_ratio",
            "I4_median",
            "I4_final",
            "rag_citation_rate",
            "calls",
            "tokens_in",
            "tokens_out",
            "total_ms",
            "llm_drifts",
        )
        out: dict = {"n_runs": len(samples)}
        for k in keys:
            out[k] = med_iqr([float(s.get(k, 0) or 0) for s in samples])

        # I3 : distribution des sorties, agrégée sur les runs.
        exits: dict[str, int] = {}
        for s in samples:
            for code, count in (s.get("exit_distribution") or {}).items():
                exits[code] = exits.get(code, 0) + count
        out["exit_distribution"] = exits

        # I5 : doit être nul ; on rapporte le total, pas une moyenne trompeuse.
        out["temporal_violations"] = sum(s.get("temporal_violations", 0) for s in samples)
        out["rag_degraded"] = any(s.get("rag_degraded", False) for s in samples)

        # Valeurs brutes conservées pour les tests non paramétriques (F5).
        out["samples"] = [
            {
                "run_id": s.get("run_id"),
                "I1": s.get("I1_median"),
                "I2": s.get("I2_median"),
                "I3": s.get("I3_evacuated_ratio"),
                "I4": s.get("I4_median"),
                "rag_citation_rate": s.get("rag_citation_rate"),
                "exit_distribution": s.get("exit_distribution"),
                "agent_last_exits": s.get("agent_last_exits"),
            }
            for s in samples
        ]
        return out
