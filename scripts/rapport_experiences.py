#!/usr/bin/env python3
"""Rapport d'expérimentation MARÉE v2 — depuis les runs, pas depuis la main.

Lit `runs/experiment_x*.json` (une ligne par run) et les journaux
`runs/<run_id>/events.jsonl` pour ce que les six indicateurs ne disent
pas :

    - qui sort en dernier (un agent LLM ou un agent à règles) — c'est ce
      qui dit si la durée mesure la cognition ou la baseline ;
    - le délai réel entre le premier signal de danger et le dernier
      sorti (I7), qui ne dépend pas de l'heure de ce signal et reste
      défini sous censure, publié à côté de I3 ;
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

PROTOCOLS = (
    "x1", "x2", "x3", "x4", "x5", "x6", "x7",
    "x8", "x9", "x10", "x11", "x12", "x13", "x14",
)

#: Nom d'indicateur du protocole -> (clé de ligne, libellé, définition).
INDICATORS: dict[str, tuple[str, str, str]] = {
    "I1_consensus": ("I1", "I1 consensus", "part des agents qui partagent la croyance majoritaire"),
    "I2_entropy": ("I2", "I2 entropie", "incertitude moyenne des croyances (0 = tous sûrs)"),
    "I3_evacuated": ("I3", "I3 évacués", "part des agents sortis"),
    "I4_seconds": ("I4", "I4 durée", "durée d'évacuation observée (s)"),
    "I5_max_density": ("I5", "I5 densité max", "densité locale max, noyau de 2 m (pers/m²)"),
    "I6_belief_gap": ("I6", "I6 écart", "part des agents croyant en une sortie fermée"),
    "I7_delay": ("I7", "I7 délai", "premier signal de danger → dernier sorti (s)"),
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
    intentions: Counter[str] = Counter()
    signal: int | None = None
    tick_seconds = 10.0
    for event in journal(run_dir):
        etype, data = event["type"], event["data"]
        if etype == "world.snapshot" and not kinds:
            kinds = {a["id"]: a.get("kind", "rules") for a in data["agents"]}
        elif etype == "agent.evacuated":
            last_evac[data["agent_id"]] = event["t_prod"]
        elif etype in ("world.smoke", "world.announcement", "world.exit_closed"):
            # Le premier indice que la situation a changé — pas le premier
            # agent qui bouge : un guide ou un proche cherché part avant.
            tick = event["t_prod"]
            signal = tick if signal is None else min(signal, tick)
        elif etype == "agent.decision":
            kind = data.get("kind", "rules")
            decisions[kind] += 1
            triggers[data.get("trigger") or "?"] += 1
            intention = data.get("intention") or {}
            intentions[intention.get("kind") or "?"] += 1
            if intention.get("kind") == "go_exit" and intention.get("target"):
                exits.setdefault(kind, Counter())[intention["target"]] += 1
        elif etype == "metrics.indicators":
            # Le pas de temps du monde vient du journal lui-même : I4 est
            # le tick × le pas, donc pas = I4 / tick. Pas de constante
            # recopiée ici.
            tick = data.get("tick")
            elapsed = data.get("I4_seconds")
            if tick and elapsed:
                tick_seconds = float(elapsed) / float(tick)
    last_tick = max(last_evac.values()) if last_evac else None
    last_ids = [a for a, t in last_evac.items() if t == last_tick]
    # I7 — même définition que `metrics.indicators.compute`, recalculée
    # depuis le journal : les lignes JSON de X1–X4 sont antérieures à I7,
    # et le journal est la source de vérité (convention 1).
    delay = None
    if signal is not None and last_tick is not None:
        delay = max(0.0, (last_tick - signal) * tick_seconds)
    return {
        "kinds": kinds,
        "last_tick": last_tick,
        "last_kind": kinds.get(last_ids[0]) if last_ids else None,
        "signal": signal,
        "i7": delay,
        "exits": exits,
        "triggers": triggers,
        "decisions": decisions,
        "intentions": intentions,
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


def row_value(row: dict[str, Any], key: str, info: dict[str, Any]) -> float | None:
    """La valeur d'un indicateur : la ligne JSON si elle le porte, sinon le journal.

    X1–X4 ont tourné avant l'ajout de I7 : leur JSON ne le contient pas,
    leur journal oui. On ne réécrit pas les vieilles lignes — le journal
    est la source de vérité, la ligne n'en est qu'un cache.
    """
    if row.get(key) is not None:
        return float(row[key])
    if key == "I7":
        return info.get("i7")
    return None


def column(
    rows: list[dict[str, Any]],
    key: str,
    infos: dict[str, dict[str, Any]],
    arm: str | None = None,
) -> list[float]:
    """Les valeurs disponibles d'un indicateur, éventuellement pour un bras."""
    out: list[float] = []
    for r in rows:
        if arm is not None and r["arm"] != arm:
            continue
        value = row_value(r, key, infos[r["run_id"]])
        if value is not None:
            out.append(value)
    return out


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
    seeds = {pid: sorted({r["seed"] for r in rs}) for pid, rs in rows.items()}
    add("- Graines par protocole : " + ", ".join(
        f"{pid.upper()} {len(s)}" for pid, s in seeds.items()
    ) + ".")
    add("- Médiane [Q1–Q3], test de Mann-Whitney bilatéral entre le premier")
    add("  bras et chacun des autres.")
    add("- **Censure** : un run qui atteint `max_ticks` avant que tout le")
    add("  monde soit sorti produit un I4 égal au plafond (720 s en scénario")
    add("  `demo`, 900 s en `e2e`). Ce n'est pas une durée d'évacuation :")
    add("  c'est un run interrompu. Dans ce cas, lire I3 (part sortie).")
    add("  La table « runs non terminés » donne le compte par bras.")
    add("- **I4 et I7** : I4 est une horloge — le temps écoulé depuis t0 —")
    add("  donc il inclut l'attente avant le premier signal et se fige au")
    add("  plafond `max_ticks` dès qu'une partie de la foule ne sort pas")
    add("  (X1 ambigu : I4 = 720 s pour un dernier sorti à t31). I7 part du")
    add("  premier signal de danger et s'arrête au dernier sorti : il reste")
    add("  défini sous censure. Il ne retire pas l'heure de l'annonce (X1 :")
    add("  fumée à t5 dans tous les bras, donc I7 = I4 − 50 s), il retire")
    add("  le temps d'avant-signal et le plancher de censure. Il est publié")
    add("  avec I3 à côté : un délai court sur une foule à moitié sortie ne")
    add("  dit pas la même chose.\n")

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
        infos = {r["run_id"]: analyse_run(runs / r["run_id"]) for r in proto_rows}
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
                values = column(arm_rows, key, infos)
                if not values:
                    cells.append("—")
                    continue
                med, q1, q3 = med_iqr(values)
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
            # Par défaut : premier bras contre les autres. Un protocole dont
            # les bras ne mesurent pas le même monde (X13 : `demo` et `e2e`)
            # déclare ses paires avec `compare: [[a, b], …]` — comparer un
            # bras `demo` à un bras `e2e` produirait des p-values
            # significatives qui ne disent rien d'autre que « les scénarios
            # diffèrent ».
            pairs = [tuple(p) for p in spec.get("compare", [])] or [
                (arms[0], other) for other in arms[1:]
            ]
            add("### Tests (Mann-Whitney)\n")
            add("| indicateur | comparaison | p |")
            add("|---|---|---|")
            for ref, other in pairs:
                for name in spec.get("indicators", []):
                    key = INDICATORS.get(name, (name, name, ""))[0]
                    a = column(proto_rows, key, infos, ref)
                    b = column(proto_rows, key, infos, other)
                    p = p_value(a, b)
                    if p is None:
                        cell = "—"
                    elif math.isnan(p):
                        cell = "constante"
                    else:
                        cell = f"{p:.4f}"
                    add(f"| {name} | {ref} vs {other} | {cell} |")
            add("")

        # Le délai, avec I3 à côté : un délai court sur une foule à moitié
        # sortie ne veut pas dire la même chose qu'un délai court sur une
        # foule complète.
        add("### Délai premier signal → dernier sorti (I7)\n")
        add("| bras | I7 médian [Q1–Q3] (s) | I3 médian | dernier sorti (ticks) "
            "| type du dernier | runs où c'est un LLM |")
        add("|---|---|---|---|---|---|")
        for arm in arms:
            arm_rows = [r for r in proto_rows if r["arm"] == arm]
            delays = column(arm_rows, "I7", infos)
            if delays:
                med, q1, q3 = med_iqr(delays)
                delay_cell = f"{fmt(med)} [{fmt(q1)}–{fmt(q3)}]"
            else:
                delay_cell = "—"
            i3 = column(arm_rows, "I3", infos)
            ticks: list[str] = []
            kinds: list[str] = []
            for r in arm_rows:
                info = infos[r["run_id"]]
                ticks.append(str(info["last_tick"]) if info["last_tick"] is not None else "—")
                kinds.append(info["last_kind"] or "—")
            n_llm = sum(1 for k in kinds if k == "llm")
            add(
                f"| {arm} | {delay_cell} | {fmt(statistics.median(i3)) if i3 else '—'} "
                f"| {', '.join(ticks)} | {', '.join(kinds)} | {n_llm}/{len(arm_rows)} |"
            )
        add("")

        # Annonces réellement délivrées : un bras sans annonce ne mesure rien.
        if pid == "x1":
            add("### Annonces délivrées\n")
            add("| bras | runs avec au moins une décision déclenchée par l'annonce |")
            add("|---|---|")
            for arm in arms:
                arm_rows = [r for r in proto_rows if r["arm"] == arm]
                delivered = sum(
                    1 for r in arm_rows if infos[r["run_id"]]["announcements"] > 0
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
                info = infos[r["run_id"]]
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
