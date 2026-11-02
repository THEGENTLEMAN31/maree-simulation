"""Le script d'énergie doit dater les runs, quel que soit leur nom.

Un nom de run sans heure faisait mesurer **zéro** run : le script sortait
un tableau vide, sans erreur. C'est le genre de silence que le projet
refuse ; ces deux tests le gardent.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _module():
    spec = importlib.util.spec_from_file_location(
        "energie", ROOT / "scripts" / "energie.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(directory: Path, ended: float) -> None:
    directory.mkdir(parents=True)
    event = {"type": "run.ended", "t_real": ended}
    (directory / "events.jsonl").write_text(
        json.dumps(event) + "\n", encoding="utf-8"
    )


def test_run_sans_heure_se_date_par_le_mtime(tmp_path: Path) -> None:
    energie = _module()
    run = tmp_path / "run_x12_deux_tiers_s0_1a2b"
    _run(run, 12.5)

    window = energie.run_window(run)

    assert window is not None
    start, end = window
    assert end == (run / "events.jsonl").stat().st_mtime
    assert end - start == 12.5


def test_run_horodate_se_date_par_son_nom(tmp_path: Path) -> None:
    energie = _module()
    run = tmp_path / "run_20261029-101500_abcd"
    _run(run, 3.0)

    window = energie.run_window(run)

    assert window is not None
    start, end = window
    expected = datetime.strptime(
        "run_20261029-101500", "run_%Y%m%d-%H%M%S"
    ).timestamp()
    assert start == expected
    assert end == expected + 3.0


def test_run_sans_journal_est_ignore(tmp_path: Path) -> None:
    energie = _module()
    run = tmp_path / "run_x1_clair_tot_s0_0000"
    run.mkdir()
    assert energie.run_window(run) is None
