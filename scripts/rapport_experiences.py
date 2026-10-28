#!/usr/bin/env python3
"""Rapport d'expérimentation MARÉE v2 — depuis les runs, pas depuis la main.

Lit `runs/experiment_x*.json` (une ligne par run) et les journaux
`runs/<run_id>/events.jsonl` pour ce que les six indicateurs ne disent
pas :

    - qui sort en dernier (un agent LLM ou un agent à règles) — c'est ce
      qui dit si I4 mesure la cognition ou la baseline ;
    - quelles sorties les agents choisissent (par type d'agent) ;
    - combien d'annonces ont été réellement délivrées (un bras dont
      l'annonce tombe après la sortie ne mesure rien).

Usage :

    uv run python scripts/rapport_experiences.py
    uv run python scripts/rapport_experiences.py --out docs/resultats/rapport-v2.md

Aucune valeur n'est écrite à la main dans la sortie : tout vient des
fichiers. Si un protocole n'a pas tourné, il est signalé, pas inventé.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from scipy.stats import mannwhitneyu

PROTOCOLS = ("x1", "x2", "x3", "x4", "x5", "x6", "x7")

#: Nom d'indicateur du protocole -> (clé de ligne, libellé, définition).
INDICATORS: dict[str, tuple[str, str, str]] = {
    "I1_consensus": ("I1", "I1 consensus", "part des agents qui partagent la croyance majoritaire"),
    "I2_entropy": ("I2", "I2 entropie", "incertitude moyenne des croyances (0 = tous sûrs)"),
    "I3_evacuated": ("I3", "I3 évacués", "part des agents sortis"),
    "I4_seconds": ("I4", "I4 durée", "durée d'évacuation observée (s)"),
    "I5_max_density": ("I5", "I5 densité max", "densité locale max, noyau de 2 m (pers/m²)"),
    "I6_belief_gap": ("I6", "I6 écart", "part des agents croyant en une sortie fermée"),
    "llm_calls": ("llm_calls", "appels LLM", "tentatives d'appel"),
    "wall_s": ("wall_s", "temps mural", "durée réelle du run (s)"),
}


# ------------------------------------------------------------
# Lecture
# ------------------------------------------------------------
def load_rows(runs: Path) -> dict[str, list[dict[str, Any]]]:
    """Les lignes d'expérience, par protocole. Absent = absent."""
    out: dict[str, list[dict[str, Any]]] = {}
    for pid in PROTOCOLS:
        path = runs / f"experiment_{pid}.json"
        if path.exists():
            out[pid] = json.loads(path.read_text(encoding="utf-8"))
    return out


def journal(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def analyse_run(run_dir: Path) -> dict[str, Any]:
    """Ce que le journal dit et que les indicateurs ne disent pas."""
    kinds: dict[str, str] = {}
    last_evac: dict[str, int] = {}
    exits: dict[str, Counter[str]] = {"llm": Counter(), "rules": Counter()}
    triggers: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    for event in journal(run_dir):
        etype, data = event["type"], event["data"]
        if etype == "world.snapshot" and not kinds:
            kinds = {a["id"]: a.get("kind", "rules") for a in data["agents"]}
        elif etype == "agent.evacuated":
            last_evac[data["agent_id"]] = event["t_prod"]
        elif etype == "agent.decision":
            kind = data.get("kind", "rules")
            decisions[kind] += 1
            triggers[data.get("trigger") or "?"] += 1
            intention = data.get("intention") or {}
            if intention.get("kind") == "go_exit" and intention.get("target"):
                exits.setdefault(kind, Counter())[intention["target"]] += 1
    last_tick = max(last_evac.values()) if last_evac else None
    last_ids = [a for a, t in last_evac.items() if t == last_tick]
    return {
        "kinds": kinds,
        "last_tick": last_tick,
        "last_kind": kinds.get(last_ids[0]) if last_ids else None,
        "exits": exits,
        "triggers": triggers,
        "decisions": decisions,
        "announcements": triggers.get("annonce", 0),
    }


# ------------------------------------------------------------
# Statistiques
# ------------------------------------------------------------
def med_iqr(values: list[float]) -> tuple[float, float, float]:
    xs = sorted(values)
    if not xs:
        return 0.0, 0.0, 0.0
    median = statistics.median(xs)
    if len(xs) < 2:
        return median, median, median
    q1, _, q3 = statistics.quantiles(xs, n=4, method="inclusive")
    return median, q1, q3


def p_value(a: list[float], b: list[float]) -> float | None:
    """Mann-Whitney bilatéral. `auto` : exact sans ex æquo, sinon asymptotique."""
    if len(a) < 2 or len(b) < 2:
        return None
    return float(mannwhitneyu(a, b, alternative="two-sided", method="auto").pvalue)


def fmt(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}"


# ------------------------------------------------------------
# Rendu
# ------------------------------------------------------------
def render(rows: dict[str, list[dict[str, Any]]], runs: Path) -> str:
    lines: list[str] = []
    add = lines.append

    total = sum(len(r) for r in rows.values())
    llm_calls = sum(r["llm_calls"] for rs in rows.values() for r in rs)
    llm_ok = sum(r["llm_ok"] for rs in rows.values() for r in rs)
    add("# MARÉE — résultats X1–X7 (campagne v2)\n")
    add("Rapport généré par `scripts/rapport_experiences.py` à partir des")
    add("`runs/experiment_x*.json` et des journaux JSONL. Aucun chiffre n'est")
    add("écrit à la main.\n")
    add(f"- **{total} runs** mesurés, {len(rows)} protocoles.")
    add(f"- **{llm_ok} / {llm_calls}** appels LLM aboutis.")
    add("- Population de référence : 12 agents LLM + 48 à règles (X4 varie).")
    add("- Chaque bras : 5 graines (0–4). Médiane [Q1–Q3], test de")
    add("  Mann-Whitney bilatéral entre le premier bras et chacun des autres.")
    add("- **Censure** : un run qui atteint `max_ticks` avant que tout le")
    add("  monde soit sorti produit un I4 égal au plafond (720 s en scénario")
    add("  `demo`, 900 s en `e2e`). Ce n'est pas une durée d'évacuation :")
    add("  c'est un run interrompu. Dans ce cas, lire I3 (part sortie).")
    add("  La table « runs non terminés » donne le compte par bras.\n")

    add("## Ce que mesure chaque indicateur\n")
    add("| indicateur | définition |")
    add("|---|---|")
    for _, (_, label, definition) in INDICATORS.items():
        add(f"| {label} | {definition} |")
    add("")

    for pid in PROTOCOLS:
        spec_path = Path("configs/experiment") / f"{pid}.yaml"
        spec = _read_spec(spec_path)
        add(f"## {spec.get('id', pid.upper())} — {spec.get('hypothesis', '?')}\n")
        if not spec:
            add("_Protocole introuvable._\n")
            continue
        if pid not in rows:
            add(f"**Non exécuté** — aucun `experiment_{pid}.json`.\n")
            continue

        arms: list[str] = [a["name"] for a in spec.get("arms", [])]
        proto_rows = rows[pid]
        add(f"Indicateurs déclarés : {', '.join(spec.get('indicators', []))}\n")
        add("### Par bras\n")
        add("| bras | n | " + " | ".join(
            INDICATORS.get(i, (i, i, ""))[1] for i in spec.get("indicators", [])
        ) + " |")
        add("|---" * (2 + len(spec.get("indicators", []))) + "|")
        for arm in arms:
            arm_rows = [r for r in proto_rows if r["arm"] == arm]
            if not arm_rows:
                add(f"| {arm} | 0 | " + " | ".join("—" for _ in spec.get("indicators", [])) + " |")
                continue
            cells = []
            for name in spec.get("indicators", []):
                key = INDICATORS.get(name, (name, name, ""))[0]
                med, q1, q3 = med_iqr([float(r[key]) for r in arm_rows])
                cells.append(f"{fmt(med)} [{fmt(q1)}–{fmt(q3)}]")
            add(f"| {arm} | {len(arm_rows)} | " + " | ".join(cells) + " |")
        add("")

        # Censure : un run qui n'évacue pas tout le monde fausse I4.
        add("### Runs non terminés (censure)")
        add("")
        add("| bras | runs non terminés | I3 médian | I4 des runs terminés |")
        add("|---|---|---|---|")
        for arm in arms:
            arm_rows = [r for r in proto_rows if r["arm"] == arm]
            unfinished = [r for r in arm_rows if float(r["I3"]) < 0.999]
            done = [float(r["I4"]) for r in arm_rows if float(r["I3"]) >= 0.999]
            med_done = fmt(statistics.median(done)) if done else "—"
            add(
                f"| {arm} | {len(unfinished)}/{len(arm_rows)} | "
                f"{fmt(statistics.median([float(r['I3']) for r in arm_rows]))} | {med_done} |"
            )
        add("")

        # Tests : premier bras contre les autres, sur chaque indicateur.
        if len(arms) >= 2 and proto_rows:
            add("### Tests (Mann-Whitney, premier bras contre les autres)\n")
            add("| indicateur | comparaison | p |")
            add("|---|---|---|")
            ref = arms[0]
            for other in arms[1:]:
                for name in spec.get("indicators", []):
                    key = INDICATORS.get(name, (name, name, ""))[0]
                    a = [float(r[key]) for r in proto_rows if r["arm"] == ref]
                    b = [float(r[key]) for r in proto_rows if r["arm"] == other]
                    p = p_value(a, b)
                    if p is None:
                        cell = "—"
                    elif math.isnan(p):
                        cell = "constante"
                    else:
                        cell = f"{p:.4f}"
                    add(f"| {name} | {ref} vs {other} | {cell} |")
            add("")

        # Qui sort en dernier : I4 mesure-t-il la cognition ?
        add("### Qui sort en dernier (I4)\n")
        add("| bras | dernier sorti (ticks) | type du dernier | runs où c'est un LLM |")
        add("|---|---|---|---|")
        for arm in arms:
            arm_rows = [r for r in proto_rows if r["arm"] == arm]
            ticks: list[str] = []
            kinds: list[str] = []
            for r in arm_rows:
                info = analyse_run(runs / r["run_id"])
                ticks.append(str(info["last_tick"]) if info["last_tick"] is not None else "—")
                kinds.append(info["last_kind"] or "—")
            n_llm = sum(1 for k in kinds if k == "llm")
            add(f"| {arm} | {', '.join(ticks)} | {', '.join(kinds)} | {n_llm}/{len(arm_rows)} |")
        add("")

        # Annonces réellement délivrées : un bras sans annonce ne mesure rien.
        if pid == "x1":
            add("### Annonces délivrées\n")
            add("| bras | runs avec au moins une décision déclenchée par l'annonce |")
            add("|---|---|")
            for arm in arms:
                arm_rows = [r for r in proto_rows if r["arm"] == arm]
                delivered = sum(
                    1 for r in arm_rows if analyse_run(runs / r["run_id"])["announcements"] > 0
                )
                add(f"| {arm} | {delivered}/{len(arm_rows)} |")
            add("")

        # Choix de sortie : la mesure des protocoles sur la croyance.
        add("### Sorties choisies (décisions `go_exit`)\n")
        add("| bras | agents LLM | agents à règles |")
        add("|---|---|---|")
        for arm in arms:
            llm: Counter[str] = Counter()
            rules: Counter[str] = Counter()
            for r in proto_rows:
                if r["arm"] != arm:
                    continue
                info = analyse_run(runs / r["run_id"])
                llm.update(info["exits"].get("llm", Counter()))
                rules.update(info["exits"].get("rules", Counter()))
            add(f"| {arm} | {_fmt_counter(llm)} | {_fmt_counter(rules)} |")
        add("")

    return "\n".join(lines)


def _read_spec(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    from omegaconf import OmegaConf

    cfg = OmegaConf.to_container(OmegaConf.load(path), resolve=True)
    return dict(cfg.get("experiment", {}))  # type: ignore[arg-type]


def _fmt_counter(counter: Counter[str]) -> str:
    if not counter:
        return "—"
    return ", ".join(f"{k} {v}" for k, v in sorted(counter.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", default="runs", help="dossier des runs")
    parser.add_argument("--out", default=None, help="fichier markdown de sortie")
    args = parser.parse_args()

    runs = Path(args.runs)
    rows = load_rows(runs)
    text = render(rows, runs)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"{len(text.splitlines())} lignes -> {out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
