"""Le Chroniqueur — un narrateur omniscient et stérile.

Il lit tout, il n'écrit rien chez les agents.

    lit      world.events, croyances de tous, densités, indicateurs
    écrit    narrative.generated, et rien d'autre
    jamais   aucun agent ne s'abonne à sa sortie

Sans cette règle d'isolation, le narrateur deviendrait un oracle : les
agents apprendraient par lui, et l'expérience ne mesurerait plus la
construction d'une croyance partagée, mais la diffusion d'une vérité
officielle. C'est la différence entre un monde vivant et un jeu télévisé.

Garde-fou anti-hallucination : le texte est validé contre le digest. Un
narrateur qui invente un chiffre ou une sortie ruine la démonstration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from maree.narrative.digest import WorldDigest
from maree.ports import ChatMessage, LLMPort

SYSTEM = (
    "Tu es le chroniqueur de la Fête des Lanternes de Port-Aubel. Tu décris "
    "ce qui se passe, au présent, en deux phrases au maximum, en français. "
    "Tu ne dis QUE ce que le résumé contient. Tu n'inventes ni personne, ni "
    "chiffre, ni sortie. Tu écris les nombres en chiffres. Ton neutre, sans "
    "jugement, sans conseil."
)

#: Gabarit de repli si le modèle échoue ou invente.
FALLBACK = "À {sim_time}, {evacuated} personnes sur {total} ont quitté l'esplanade."

_EXIT_MENTION = re.compile(r"sortie\s+([A-Z])", re.IGNORECASE)
_NUMBER = re.compile(r"\b(\d+(?:[.,]\d+)?)\b")


@dataclass(frozen=True, slots=True)
class Narrative:
    text: str
    tick: int
    digest_hash: str
    valid: bool
    problems: tuple[str, ...] = ()
    llm: dict[str, object] = field(default_factory=dict)


def validate(text: str, digest: WorldDigest) -> tuple[bool, tuple[str, ...]]:
    """Vérifie que le texte ne raconte rien qui ne soit dans le digest."""
    problems: list[str] = []
    known_exits = set(digest.open_exits) | set(digest.closed_exits)
    for letter in _EXIT_MENTION.findall(text):
        if letter.upper() not in known_exits:
            problems.append(f"sortie inconnue citée : {letter.upper()}")
    allowed = digest.allowed_numbers()
    allowed_values = {float(v.replace(",", ".")) for v in allowed}
    for raw in _NUMBER.findall(text):
        normalised = raw.replace(",", ".")
        try:
            value = float(normalised)
        except ValueError:
            continue
        if value in allowed_values:
            continue
        # Les heures « 7:30 » produisent 7 et 30 : on tolère les minutes.
        if value in {0.0, 30.0, 60.0}:
            continue
        problems.append(f"nombre absent du digest : {raw}")
    return (not problems, tuple(problems))


class Chroniqueur:
    def __init__(
        self,
        llm: LLMPort,
        *,
        every_ticks: int = 5,
        max_tokens: int = 160,
        model: str = "gemma4-e2b",
        seed_base: int = 0,
    ) -> None:
        self._llm = llm
        self._every = every_ticks
        self._max_tokens = max_tokens
        self._model = model
        self._seed_base = seed_base

    def due(self, tick: int) -> bool:
        return tick % self._every == 0

    async def narrate(self, digest: WorldDigest) -> Narrative:
        prompt = digest.to_prompt()
        result = await self._llm.chat(
            [ChatMessage("system", SYSTEM), ChatMessage("user", prompt)],
            seed=self._seed_base + digest.tick,
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=0.4,
        )
        text = (result.text or "").strip()
        ok, problems = validate(text, digest)
        if not ok or not text:
            text = FALLBACK.format(
                sim_time=digest.sim_time,
                evacuated=digest.evacuated,
                total=digest.total,
            )
        return Narrative(
            text=text,
            tick=digest.tick,
            digest_hash=digest.digest_hash(),
            valid=ok and bool(result.text),
            problems=problems,
            llm={
                "prompt": result.prompt,
                "seed": result.seed,
                "model": result.model,
                "raw_output": result.text,
                "duration_s": round(result.duration_s, 3),
                "ok": result.ok,
            },
        )
