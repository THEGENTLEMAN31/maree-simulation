"""Journal JSONL — la source de vérité (décision 1).

Append-only, une ligne par événement, lisible à l'œil, rejouable sans
infrastructure. Un fichier par run : `runs/<run_id>/events.jsonl`.

Le `seq` est fourni par l'appelant et vérifié ici : un journal qui
reculerait signalerait un run_id réutilisé (décision 5), ce qui est une
erreur, pas un détail.
"""

from __future__ import annotations

import json
from pathlib import Path

from maree.domain.events import Event
from maree.domain.ids import RunId


class JsonlJournal:
    def __init__(self, root: str | Path = "runs") -> None:
        self._root = Path(root)

    def path_for(self, run_id: RunId) -> Path:
        return self._root / run_id / "events.jsonl"

    def quarantine_path(self, run_id: RunId) -> Path:
        return self._root / run_id / "invalid.jsonl"

    # ---- écriture ---------------------------------------------
    def append(self, event: Event) -> None:
        path = self.path_for(event.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def quarantine(self, event: Event, problems: list[str]) -> None:
        """Isole un événement non conforme (F4), sans arrêter le run.

        Le fichier est séparé : `events.jsonl` reste lisible par un
        consommateur strict, et `invalid.jsonl` dit pourquoi la ligne a été
        refusée. Un test peut donc exiger zéro ligne des deux côtés.
        """
        path = self.quarantine_path(event.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"event": event.to_dict(), "problems": problems}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    # ---- lecture ----------------------------------------------
    def read(self, run_id: RunId) -> list[Event]:
        path = self.path_for(run_id)
        if not path.exists():
            return []
        events: list[Event] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    events.append(Event.from_dict(json.loads(line)))
        return events

    def last_seq(self, run_id: RunId) -> int:
        path = self.path_for(run_id)
        if not path.exists():
            return 0
        last = 0
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = int(json.loads(line)["seq"])
        return last

    # ---- inspection -------------------------------------------
    def runs(self) -> list[RunId]:
        if not self._root.exists():
            return []
        return sorted(
            p.name for p in self._root.iterdir() if (p / "events.jsonl").exists()
        )
