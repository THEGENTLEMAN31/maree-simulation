"""Passerelle LLM unique (décision 7 ; exigences A4, E4, O7).

Tous les appels LLM passent par cette passerelle :
- quotas (respect du budget d'appels) ;
- retries et timeout ;
- repli sur règle en cas d'échec (A4) ;
- journal de coût (appels, tokens, latence) pour E4 ;
- mode `dry_run` : aucun appel réseau (tests, replay sans LLM).
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field

import httpx

from .config import ProfileSpec


@dataclass
class LLMCallResult:
    text: str
    call_id: int
    model: str
    duration_ms: int
    tokens_in: int = 0
    tokens_out: int = 0
    ok: bool = True
    error: str | None = None


@dataclass
class CostLog:
    """Journal de coût par run (E4, O7) — rempli par la passerelle."""

    calls: list[dict] = field(default_factory=list)

    def add(self, **entry) -> None:
        self.calls.append(entry | {"ts": time.time()})

    def summary(self) -> dict:
        n = len(self.calls)
        tokens_in = sum(c.get("tokens_in", 0) for c in self.calls)
        tokens_out = sum(c.get("tokens_out", 0) for c in self.calls)
        dur_ms = sum(c.get("duration_ms", 0) for c in self.calls)
        return {
            "calls": n,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "total_ms": dur_ms,
            "avg_ms": dur_ms / max(1, n),
        }


class LLMGateway:
    """Client OpenAI-compatible vers llama.cpp (router multi-modèles)."""

    MAX_TOKENS = 512

    def __init__(
        self,
        base_url: str,
        profile_spec: ProfileSpec | None = None,
        *,
        timeout_sec: float = 60.0,
        max_retries: int = 2,
        dry_run: bool = False,
        cost_log: CostLog | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.dry_run = dry_run
        self.cost_log = cost_log or CostLog()
        self._client = httpx.AsyncClient(timeout=timeout_sec)
        self._call_counter = 0
        self.profile_spec = profile_spec

    async def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> LLMCallResult:
        """Appel chat completions avec retries et journal de coût."""
        self._call_counter += 1
        call_id = self._call_counter

        if self.dry_run:
            # Mode de repli : aucune boîte noire, réponse déterministe vide.
            await asyncio.sleep(0.001)
            self.cost_log.add(
                call_id=call_id,
                model=model,
                duration_ms=1,
                tokens_in=0,
                tokens_out=0,
                dry_run=True,
            )
            return LLMCallResult(text="{}", call_id=call_id, model=model, duration_ms=1)

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or self.MAX_TOKENS,
            "stream": False,
        }
        last_err: Exception | None = None
        t0 = time.time()
        for attempt in range(1 + self.max_retries):
            try:
                resp = await self._client.post(
                    f"{self.base_url}/chat/completions", json=payload
                )
                resp.raise_for_status()
                data = resp.json()
                message = data["choices"][0]["message"]
                # Gemma 4 (mode thinking) et certains modèles renvoient le
                # raisonnement dans `reasoning` et le contenu dans `content`.
                # On extrait le contenu utilisable = content, sinon rien.
                content = message.get("content") or ""
                reasoning = message.get("reasoning") or ""
                usage = data.get("usage", {})
                result = LLMCallResult(
                    text=content,
                    call_id=call_id,
                    model=model,
                    duration_ms=int((time.time() - t0) * 1000),
                    tokens_in=usage.get("prompt_tokens", 0),
                    tokens_out=usage.get("completion_tokens", 0),
                )
                # Traçabilité du raisonnement pour l'inspection (D2).
                if reasoning:
                    setattr(result, "reasoning", reasoning)
                    # Gemma 4 (mode thinking) peut placer la réponse complète
                    # dans `reasoning` avec `content` vide. On garde le contenu
                    # utile : content si non-vide, sinon le JSON trouvé (ou le
                    # bloc de fin) dans reasoning.
                    if not content.strip():
                        result.text = self._extract_useful(reasoning)
                self.cost_log.add(
                    call_id=call_id,
                    model=model,
                    duration_ms=result.duration_ms,
                    tokens_in=result.tokens_in,
                    tokens_out=result.tokens_out,
                    ok=True,
                )
                return result
            except (httpx.HTTPError, KeyError, ValueError) as e:
                last_err = e
                await asyncio.sleep(0.5 * attempt)
        self.cost_log.add(
            call_id=call_id,
            model=model,
            duration_ms=int((time.time() - t0) * 1000),
            tokens_in=0,
            tokens_out=0,
            ok=False,
            error=str(last_err),
        )
        return LLMCallResult(
            text="",
            call_id=call_id,
            model=model,
            duration_ms=int((time.time() - t0) * 1000),
            ok=False,
            error=str(last_err),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _extract_useful(reasoning: str) -> str:
        """Extrait le contenu utile d'un raisonnement Gemma 4.

        Le pattern typique du mode thinking : un bloc de raisonnement, puis
        la réponse finale. On prend le dernier bloc JSON équilibré (ou tout
        le dernier bloc si aucun JSON n'est trouvé).
        """
        import re

        # 1. dernier objet JSON complet (équilibré en accolades)
        for m in re.finditer(r"\{", reasoning):
            i = m.start()
            depth = 0
            string = False
            j = i
            while j < len(reasoning):
                ch = reasoning[j]
                if ch == '"' and (j == 0 or reasoning[j - 1] != "\\"):
                    string = not string
                elif not string and ch in "{}":
                    depth += 1 if ch == "{" else -1
                    if depth == 0:
                        return reasoning[i : j + 1]
                j += 1
        # 2. pas de JSON : on renvoie la dernière phrase éventuelle de réponse
        lines = [l for l in reasoning.splitlines() if l.strip()]
        return lines[-1] if lines else reasoning

    @staticmethod
    def parse_json_robust(text: str) -> dict | None:
        """Parse la réponse LLM (JSON) en tolérant les artefacts
        (fences, texte autour). Dérive comptée dans A4 si None."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines:
                lines = lines[1:]
            cleaned = "\n".join(lines).strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None