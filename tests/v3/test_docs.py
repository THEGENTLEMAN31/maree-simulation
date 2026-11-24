"""La documentation ne doit pas mentir sur les chemins.

L'audit de reprise du 2026-11-24 a trouvé des renvois périmés (un JSON de
campagne écrasé, un `make index` inexistant). Ces défauts ne cassent aucun
test de code : ils cassent la reprise. On les attrape ici, mécaniquement :

- tout chemin `runs/…`, `docs/…`, `scripts/…`, `src/…` cité dans les documents
  d'entrée existe ;
- toute cible `make …` citée existe dans le Makefile ;
- les documents d'entrée existent et ne sont pas vides.

Rien ici ne juge la prose : seulement les promesses vérifiables.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINTS = (
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "docs/v3/HANDOFF.md",
    ROOT / "docs/v3/rapport-v3.md",
    ROOT / "docs/v3/preregistrements.md",
    ROOT / "docs/v3/plan-autonomie.md",
)
PATH_RE = re.compile(r"`((?:runs|docs|scripts|src|tests)/[A-Za-z0-9_./*{}-]+)`")
MAKE_RE = re.compile(r"`make ([a-z][a-z0-9-]*)`")


def _texts() -> list[tuple[Path, str]]:
    return [(p, p.read_text(encoding="utf-8")) for p in ENTRY_POINTS]


def test_les_documents_d_entree_existent_et_ne_sont_pas_vides() -> None:
    for path in ENTRY_POINTS:
        assert path.exists(), f"document d'entrée absent : {path}"
        assert len(path.read_text(encoding="utf-8")) > 500, f"document vide : {path}"


def test_les_chemins_cites_existent() -> None:
    missing: list[str] = []
    for path, text in _texts():
        for cited in PATH_RE.findall(text):
            if any(ch in cited for ch in "*{"):
                continue  # motif, pas un chemin
            if cited.endswith("/"):
                continue
            target = ROOT / cited
            if not target.exists():
                missing.append(f"{path.name} → {cited}")
    assert not missing, "chemins cités absents du dépôt :\n" + "\n".join(sorted(set(missing)))


def test_les_cibles_make_citees_existent() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([a-z][a-z0-9-]*):", makefile, flags=re.MULTILINE))
    missing: list[str] = []
    for path, text in _texts():
        for cited in MAKE_RE.findall(text):
            if cited not in targets:
                missing.append(f"{path.name} → make {cited}")
    assert not missing, "cibles make citées mais absentes :\n" + "\n".join(sorted(set(missing)))


#: La métrique principale du rapport.
METRIC = "targeted_believed_blocked"
#: Bras dont la campagne P1.1 a été écrasée avant fusion (note † du rapport).
GAP_ARMS = frozenset({"hybride", "llm_grand"})
NOTE = "† `hybride` et `llm_grand` : artefact per-run perdu"


def test_la_campagne_publiee_est_complete_ou_son_trou_est_ecrit() -> None:
    """Un chiffre du rapport a soit son run, soit une note qui dit pourquoi.

    L'audit du 2026-11-24 a trouvé pire qu'un chiffre faux : un chiffre juste
    dont l'artefact avait été écrasé, présenté comme régénérable. On ne peut
    pas exiger que la campagne soit complète (elle coûte 3 h de GPU), mais on
    peut exiger que le trou soit **nommé**. Si un jour `make v3-crowd-10`
    remplit les deux bras, ce test échoue tant que la note n'est pas retirée.
    """
    import json

    path = ROOT / "runs/v3/campaign_crowd_10seeds.json"
    assert path.exists(), "l'artefact publié a disparu"
    data = json.loads(path.read_text(encoding="utf-8"))
    runs = data["runs"]
    assert len(runs) == 80, f"{len(runs)} runs au lieu de 80"
    keys = {(run["arm"], run["scenario"], run["seed"]) for run in runs}
    assert len(keys) == 80, "clés (bras, scénario, graine) dupliquées"
    assert {arm for arm, _, _ in keys} == {
        "regles", "hybride", "llm_grand", "decision_head"
    }
    assert {seed for _, _, seed in keys} == set(range(1, 11))
    assert {sc for _, sc, _ in keys} == {"split", "contradiction"}
    assert all(run["decisions"] > 0 for run in runs), "un run sans décision"

    missing = {run["arm"] for run in runs if run.get(METRIC) is None}
    assert missing <= GAP_ARMS, (
        "ces bras n'ont pas la métrique principale sans figurer dans les trous "
        f"connus : {sorted(missing - GAP_ARMS)}"
    )
    report = (ROOT / "docs/v3/rapport-v3.md").read_text(encoding="utf-8")
    assert (NOTE in report) == bool(missing), (
        "la note † du rapport et l'état de l'artefact ne concordent pas : "
        f"trous={sorted(missing)}, note={'présente' if NOTE in report else 'absente'}"
    )
