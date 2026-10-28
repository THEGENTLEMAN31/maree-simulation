"""Mémoire indépendante, cloisonnée, dérivée du journal.

Trois mémoires par agent :

    épisodique   ce qu'il a vu, entendu, dit, décidé
    sémantique   sa table de croyances (sortie → confiance, source)
    sociale      sa confiance envers les autres agents

GARANTIE CENTRALE — le cloisonnement est vérifié, pas espéré :

    recall("A19", …) ne peut jamais retourner un épisode d'un autre agent.
    Une fuite de connaissance invaliderait l'expérience (un visiteur ne
    doit pas savoir ce qu'un habitué sait).

Trois niveaux d'accès :

    agent       sa mémoire uniquement
    narrator    lecture de tout, écriture nulle part chez les agents
    analyst     lecture de tout, hors ligne (expériences, rapport)

La mémoire est une *projection* : elle se reconstruit depuis le journal,
donc le rejeu reste exact (décision 1).
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from maree.domain.beliefs import BeliefTable
from maree.domain.ids import AgentId, Tick
from maree.ports import Episode

_WORD = re.compile(r"[a-zàâçéèêëîïôûùüÿñæœ0-9]+", re.IGNORECASE)

#: Au-delà, les épisodes les plus anciens sont résumés.
DEFAULT_WINDOW = 12


def _terms(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if len(w) > 2}


@dataclass(slots=True)
class _AgentMemory:
    episodes: list[Episode]
    beliefs: BeliefTable
    trust: dict[AgentId, float]


class EventSourcedMemory:
    """Implémentation en mémoire, alimentée par les événements du run."""

    def __init__(self, n_exits: int = 3, window: int = DEFAULT_WINDOW) -> None:
        self._n_exits = n_exits
        self._window = window
        self._mem: dict[AgentId, _AgentMemory] = {}

    # ---- interne ----------------------------------------------
    def _ensure(self, agent_id: AgentId) -> _AgentMemory:
        if agent_id not in self._mem:
            self._mem[agent_id] = _AgentMemory(
                episodes=[], beliefs=BeliefTable(), trust={}
            )
        return self._mem[agent_id]

    # ---- MemoryPort -------------------------------------------
    def remember(self, agent_id: AgentId, episode: Episode) -> None:
        self._ensure(agent_id).episodes.append(episode)

    def recall(
        self, agent_id: AgentId, query: str = "", k: int = 5, tick: Tick = 0
    ) -> list[Episode]:
        """Rappel borné : récence + saillance + pertinence lexicale.

        Déterministe : aucun tirage aléatoire, l'ordre est total.
        """
        memory = self._ensure(agent_id)
        wanted = _terms(query)
        now = tick or max((e.tick for e in memory.episodes), default=0)

        def score(e: Episode) -> tuple[float, int, int]:
            age = max(0, now - e.tick)
            recency = 1.0 / (1.0 + age / 20.0)
            relevance = len(wanted & _terms(e.content)) / (len(wanted) or 1)
            return (0.5 * recency + 0.3 * relevance + 0.2 * e.salience, e.tick, -len(e.content))

        ranked = sorted(memory.episodes, key=score, reverse=True)
        return ranked[:k]

    def beliefs(self, agent_id: AgentId) -> BeliefTable:
        return self._ensure(agent_id).beliefs

    def trust(self, agent_id: AgentId) -> dict[AgentId, float]:
        return dict(self._ensure(agent_id).trust)

    def consolidate(self, agent_id: AgentId, tick: Tick) -> None:
        """Compresse les souvenirs anciens en un résumé déterministe.

        Pas d'appel LLM ici : la consolidation doit être rejouable à
        l'identique. Le résumé est un gabarit, pas une génération.
        """
        memory = self._ensure(agent_id)
        if len(memory.episodes) <= self._window:
            return
        old = memory.episodes[: -self._window]
        recent = memory.episodes[-self._window :]
        kinds = defaultdict(int)
        for e in old:
            kinds[e.kind] += 1
        parts = ", ".join(f"{n} {k}" for k, n in sorted(kinds.items()))
        summary = Episode(
            tick=tick,
            kind="resume",
            content=f"plus tôt : {parts}",
            source="consolidation",
            salience=0.4,
        )
        memory.episodes = [summary, *recent]

    # ---- accès élargi (narrateur, analyste) -------------------
    def read_all(self, principal: str) -> dict[AgentId, _AgentMemory]:
        """Lecture globale réservée au narrateur et à l'analyste.

        Un agent qui tenterait cet appel lève : la règle est explicite.
        """
        if principal not in {"narrator", "analyst"}:
            raise PermissionError(
                f"accès global refusé à {principal!r} : réservé au narrateur et à l'analyste"
            )
        return dict(self._mem)

    def all_beliefs(self, principal: str) -> dict[AgentId, BeliefTable]:
        return {aid: m.beliefs for aid, m in self.read_all(principal).items()}

    # ---- introspection ----------------------------------------
    @property
    def n_exits(self) -> int:
        return self._n_exits

    def size(self, agent_id: AgentId) -> int:
        return len(self._ensure(agent_id).episodes)


class NullMemory:
    """Mémoire inerte — le bras « sans mémoire » de X5.

    Elle ne rappelle rien, mais elle respecte le contrat : le moteur ne
    sait pas quel bras il exécute. C'est ce qui rend la comparaison
    honnête — on ne compare pas deux architectures, on compare deux
    valeurs d'un même paramètre.
    """

    def __init__(self, n_exits: int = 3) -> None:
        self._n_exits = n_exits

    def remember(self, agent_id: AgentId, episode: Episode) -> None:
        return None

    def recall(
        self, agent_id: AgentId, query: str = "", k: int = 5, tick: Tick = 0
    ) -> list[Episode]:
        return []

    def beliefs(self, agent_id: AgentId) -> BeliefTable:
        return BeliefTable()

    def trust(self, agent_id: AgentId) -> dict[AgentId, float]:
        return {}

    def consolidate(self, agent_id: AgentId, tick: Tick) -> None:
        return None

    def read_all(self, principal: str) -> dict[AgentId, _AgentMemory]:
        if principal not in {"narrator", "analyst"}:
            raise PermissionError(
                f"accès global refusé à {principal!r} : réservé au narrateur et à l'analyste"
            )
        return {}

    def all_beliefs(self, principal: str) -> dict[AgentId, BeliefTable]:
        return {}

    @property
    def n_exits(self) -> int:
        return self._n_exits

    def size(self, agent_id: AgentId) -> int:
        return 0
