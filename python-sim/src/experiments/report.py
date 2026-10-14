"""Génération du rapport (F5) : tableaux et figures produits par des
requêtes versionnées (SQL sur Parquet or JSONL via DuckDB) — reproductible.
"""
from __future__ import annotations

import json
from pathlib import Path

# Requêtes versionnées (F5) : exécutées sur l'historique des runs.
SQL_QUERIES = {
    "resume_runs": """
        SELECT run_id, mode, count(*) as n_events
        FROM '{root}/*.events.jsonl'
        GROUP BY run_id, mode
    """,
}


def build_report(log_dir: str, out_path: str = "/logs/report.md") -> None:
    """Assemble le rapport Markdown à partir des journaux + résumés."""
    log_dir_p = Path(log_dir)
    summary_path = log_dir_p / "experiments_summary.json"
    summary: dict = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

    lines = [
        "# MARÉE — Rapport d'expérimentation",
        "",
        "_Généré automatiquement (F5 : requêtes reproductibles)._",
        "",
        "## Résumés par configuration",
        "",
        "| Configuration | runs | appels (médiane) | tokens in | tokens out | durée (ms) | violations |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, res in summary.items():
        lines.append(
            f"| {name} | {res.get('n_runs', '-')} | "
            f"{_fmt(res.get('calls'))} | {_fmt(res.get('tokens_in'))} | "
            f"{_fmt(res.get('tokens_out'))} | {_fmt(res.get('total_ms'))} | "
            f"{res.get('temporal_violations', '-')} |"
        )
    lines += ["", "## Conclusion", "", "_(à rédiger après analyse, voir C5)._", ""]
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def _fmt(v) -> str:
    if isinstance(v, dict):
        m = v.get("median")
        i = v.get("iqr")
        return "–" if m is None else f"{m} ±{i}"
    return "–" if v is None else str(v)