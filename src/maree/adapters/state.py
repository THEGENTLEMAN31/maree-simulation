"""Où vit l'**état courant** du monde (F3).

F3 demande de distinguer quatre stockages et de justifier chacun par ses
besoins d'accès. Les trois autres existent déjà :

    flux d'événements   `runs/<id>/events.jsonl` (JSONL append-only)
    historique des runs `runs/<id>/` + `runs/experiment_*.json`
    base de connaissances `world_corpus/*.jsonl` + `data/rag/`

L'**état courant** n'avait pas de domicile : il vivait en RAM pendant le
run, et après coup il fallait rescanner tout le journal pour retrouver le
dernier `world.snapshot` — 6 Mo dans `c4_sync_01`, dont 89 % sont des
instantanés. Un client qui demande « où est tout le monde maintenant ? »
n'a pas besoin de l'histoire, il a besoin de la dernière valeur.

D'où ce magasin, volontairement bête :

    écriture   atomique (`tmp` + `os.replace`), à chaque instantané ;
    lecture    le dernier état complet, en un seul fichier ;
    rétention  **la dernière valeur seulement** — l'histoire est déjà
               dans le journal, la dupliquer serait un second mensonge
               possible.

Ce n'est pas une base de données et ce n'est pas censé en devenir une :
si l'on veut interroger le passé, c'est le journal (et `maree query`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from maree.domain.ids import RunId


class JsonStateStore:
    """Le dernier état du monde, un fichier par run, remplacé à chaque fois."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def path_for(self, run_id: RunId) -> Path:
        return self._root / run_id / "state.json"

    def save(self, run_id: RunId, snapshot: dict[str, Any]) -> None:
        """Remplace l'état. Atomique, pour qu'aucun lecteur ne lise un demi-fichier.

        Un client peut lire pendant que le run écrit : sans `os.replace`,
        il verrait un JSON tronqué et conclurait à une corruption.
        """
        path = self.path_for(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(snapshot, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, path)

    def load(self, run_id: RunId) -> dict[str, Any] | None:
        """Le dernier état connu, ou `None` si le run n'en a jamais produit."""
        path = self.path_for(run_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Un état illisible n'est pas une raison de tuer un client :
            # le journal reste la source de vérité, on le dit en renvoyant
            # `None` plutôt qu'en levant au milieu d'une diffusion.
            return None

    def runs(self) -> list[str]:
        """Les runs qui ont un état, du plus ancien au plus récent.

        Trié par **date de modification**, pas par nom : les identifiants
        contiennent une graine et un hachage, donc l'ordre alphabétique ne
        dit rien. « Le dernier run » doit être le dernier écrit, sinon
        `maree state` sans argument affiche un run au hasard — constaté en
        comparant deux fois de suite.
        """
        if not self._root.exists():
            return []
        entries = [e for e in self._root.glob("*/state.json") if e.is_file()]
        return [e.parent.name for e in sorted(entries, key=lambda e: e.stat().st_mtime)]
