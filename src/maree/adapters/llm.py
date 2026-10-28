"""Passerelle LLM — point d'entrée unique (décision 7).

Tout appel de modèle passe par ici : décisions des agents, embeddings du
RAG, chroniqueur. Personne d'autre ne parle au serveur d'inférence.

Ce que la passerelle garantit :

    * une trace complète (prompt, graine, sortie brute, tokens, durée)
      sans laquelle le rejeu E3 est impossible ;
    * aucune exception ne remonte : un échec devient un `LLMResult`
      `ok=False`, et l'appelant replie sur les règles ;
    * la graine est transmise au serveur, donc deux runs identiques
      produisent les mêmes décisions.

Le client est le SDK officiel OpenAI, pointé sur llama.cpp (API
compatible). C'est un vrai client, pas une réimplémentation maison de
HTTP : il gère les retries, les timeouts et le streaming si besoin.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from openai import AsyncOpenAI

from maree.ports import ChatMessage, LLMResult


class LlamaCppLLM:
    def __init__(
        self,
        base_url: str = "http://llama-cpp:8080/v1",
        *,
        api_key: str = "sk-local",
        model: str = "gemma4-e2b",
        embed_model: str = "bge-m3",
        timeout: float = 120.0,
        max_retries: int = 1,
    ) -> None:
        self._client = AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout, max_retries=max_retries
        )
        self._model = model
        self._embed_model = embed_model
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        seed: int,
        model: str | None = None,
        max_tokens: int = 256,
        temperature: float = 0.3,
    ) -> LLMResult:
        prompt = "\n".join(f"[{m.role}] {m.content}" for m in messages)
        started = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=model or self._model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                max_tokens=max_tokens,
                temperature=temperature,
                seed=seed,
                # Gemma 4 : sans cela, ~460 tokens de raisonnement par décision.
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            text = (response.choices[0].message.content or "").strip()
            usage = response.usage
            self.calls += 1
            self.tokens_in += getattr(usage, "prompt_tokens", 0) or 0
            self.tokens_out += getattr(usage, "completion_tokens", 0) or 0
            return LLMResult(
                text=text,
                prompt=prompt,
                seed=seed,
                model=model or self._model,
                tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
                tokens_out=getattr(usage, "completion_tokens", 0) or 0,
                duration_s=time.perf_counter() - started,
                ok=True,
            )
        except Exception as exc:
            return LLMResult(
                text="",
                prompt=prompt,
                seed=seed,
                model=model or self._model,
                duration_s=time.perf_counter() - started,
                ok=False,
                error=f"{type(exc).__name__}: {exc}"[:300],
            )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(
            model=self._embed_model, input=list(texts)
        )
        return [item.embedding for item in response.data]

    async def close(self) -> None:
        await self._client.close()
