"""adapters.chat_stub — un fournisseur de chatbot *stub* pour les tests.

Il démontre l'interchangeabilité des providers (deux fournisseurs opposables
dans un run) sans réseau ni GPU. ``mapper`` décide de la réponse à partir
de la requête ; par défaut il renvoie l'action ``chercher`` (gabarit).
"""

from __future__ import annotations

from collections.abc import Callable

from maree.v3.core.ports import ChatModelPort, LLMRequest, LLMResponse

_DEFAULT = '{"action": "chercher", "cible": null, "confiance": 0.5}'


class StubChat(ChatModelPort):
    """Répond sans LLM : utile aux tests et à l'ablation du tier LLM."""

    def __init__(self, mapper: Callable[[LLMRequest], str] | None = None) -> None:
        self._mapper = mapper or (lambda _req: _DEFAULT)

    def complete(self, request: LLMRequest) -> LLMResponse:
        text = self._mapper(request)
        return LLMResponse(
            text=text,
            provider=request.provider or "stub",
            model=request.model or "stub",
            prompt_tokens=sum(8 + len(m.content) // 4 for m in request.messages),
            completion_tokens=max(1, len(text) // 4),
            seed=request.seed,
            ok=True,
        )


__all__ = ["StubChat"]