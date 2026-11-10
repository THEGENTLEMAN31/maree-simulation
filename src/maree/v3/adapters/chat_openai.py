"""adapters.chat_openai — fournisseur OpenAI-compatible (llama.cpp natif).

L'API locale du projet (llama.cpp sur le port 8081) parle le dialecte
OpenAI ``/v1/chat/completions``. Cet adaptateur la consomme via le SDK
``openai`` — pas de client HTTP artisanal.

Pour tester sans réseau, on peut injecter un ``client`` factice dont
``chat.completions.create`` renvoie un objet simulant la réponse.
"""

from __future__ import annotations

from typing import Any

from maree.v3.core.ports import ChatModelPort, LLMRequest, LLMResponse


class OpenAICompatibleChat(ChatModelPort):
    """Parle à n'importe quel `chat/completions` OpenAI-compatible."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "sk-local",
        timeout_s: float = 60.0,
        client: Any | None = None,
    ) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._client = client

    def _ensure_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self._base_url,
                api_key=self._api_key,
                timeout=self._timeout_s,
                max_retries=0,
            )
        return self._client

    def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.seed is not None:
            kwargs["seed"] = request.seed
        try:
            resp = client.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
            usage = resp.usage
            return LLMResponse(
                text=text,
                provider=request.provider,
                model=request.model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                seed=request.seed,
                ok=True,
            )
        except Exception:
            return LLMResponse(
                text="",
                provider=request.provider,
                model=request.model,
                prompt_tokens=0,
                completion_tokens=0,
                seed=request.seed,
                ok=False,
            )


__all__ = ["OpenAICompatibleChat"]