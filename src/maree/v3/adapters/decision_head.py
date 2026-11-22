"""adapters.decision_head — un modèle de décision « System 1 » (Jev-style).

Un LLM de décision ne génère pas de texte : on lui donne un **état** et un
ensemble **fermé** de critères, il rend une probabilité par critère en un
passage. C'est exactement ce qu'il faut pour un agent qui doit choisir entre
« rester » et « sortir par A / B » : pas de JSON fragile à parser, pas de
gabarit recopié, une distribution qu'on peut journaliser et comparer.

Le contrat HTTP (llama.cpp ≥ 2026-10-02, endpoint `/v1/systemone`) :

```json
POST {"state": "...", "questions": {"action": {
        "type": "choice", "instructions": "...",
        "criteria": {"RESTER": "rester sur place", "SORTIR A": "..."}}}}
→    {"answers": {"action": {"choice": "RESTER",
        "probabilities": {"RESTER": 0.5, "SORTIR A": 0.29, ...},
        "confidence": 0.24}}, "usage": {"input_tokens": 73}}
```

Le champ utile est `probabilities` : il rend la décision **auditable** (on sait
à quel point le modèle hésitait) et comparable d'un modèle à l'autre.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HeadAnswer:
    """La réponse d'un modèle de décision : choix, distribution, coût."""

    choice: str
    probabilities: dict[str, float]
    confidence: float
    input_tokens: int
    ok: bool
    error: str | None = None

    def margin(self) -> float:
        """Écart entre le premier et le deuxième choix (0 = indécis)."""
        ranked = sorted(self.probabilities.values(), reverse=True)
        if len(ranked) < 2:
            return 1.0
        return ranked[0] - ranked[1]


class SystemOneHead:
    """Client minimal de `/v1/systemone` (un seul POST, pas de streaming)."""

    def __init__(self, url: str, model: str, timeout: float = 60.0) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def choose(
        self,
        state: str,
        instructions: str,
        criteria: dict[str, str],
    ) -> HeadAnswer:
        body = {
            "model": self.model,
            "state": state,
            "questions": {
                "action": {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": criteria,
                }
            },
        }
        request = urllib.request.Request(
            f"{self.url}/v1/systemone",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200].decode(errors="replace")
            return HeadAnswer("", {}, 0.0, 0, ok=False, error=f"http {exc.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            return HeadAnswer("", {}, 0.0, 0, ok=False, error=str(exc))

        try:
            answer = payload["answers"]["action"]
            probabilities = {
                str(k): float(v) for k, v in answer.get("probabilities", {}).items()
            }
            choice = str(answer["choice"])
        except (KeyError, TypeError, ValueError) as exc:
            return HeadAnswer("", {}, 0.0, 0, ok=False, error=f"réponse illisible : {exc}")
        usage = payload.get("usage", {})
        return HeadAnswer(
            choice=choice,
            probabilities=probabilities,
            confidence=float(answer.get("confidence", 0.0)),
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            ok=True,
        )


__all__ = ["HeadAnswer", "SystemOneHead"]
