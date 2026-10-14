"""Horloge simulée et ordonnanceur (décisions 2, 10 ; exigences C3, C4, C5, C6).

- L'horloge simulée compte des ticks entiers. Un tick vaut tick_duration_ms.
- Chaque événement porte t_prod (tick de production) et t_trait (tick de
  traitement) ; l'ordonnanceur est l'unique endroit qui les fixe.
- Deux modes : synchrone (tous les agents agissent au même pas) et asynchrone
  (chaque agent agit selon son propre rythme, latence du modèle comprise).
- La perception d'un agent est « figée » à l'instant de sa décision : il ne
  voit jamais d'information produite après ce tick (C6).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class AgentSchedule:
    """État d'ordonnancement d'un agent en mode asynchrone."""

    agent_id: str
    think_interval_ticks: int  # rythme propre de l'agent
    next_think_tick: int = 0
    processing_delay_ticks: int = 0  # latence de traitement (LLM/règle)

    def should_think(self, now: int) -> bool:
        return now >= self.next_think_tick


class SimClock:
    """Horloge simulée à ticks entiers ; seule source du temps logique."""

    def __init__(self, tick_duration_ms: int = 1000) -> None:
        self.tick_duration_ms = tick_duration_ms
        self.now = 0

    def advance(self, n: int = 1) -> int:
        self.now += n
        return self.now

    def to_simtime_iso(self, tick: int) -> str:
        """Convertit un tick en représentation 'J1 07:00' (affichage)."""
        minutes = tick * self.tick_duration_ms // 60000
        day = minutes // (24 * 60) + 1
        hh = (minutes % (24 * 60)) // 60
        mm = minutes % 60
        return f"J{day} {hh:02d}:{mm:02d}"


class Scheduler:
    """Ordonnanceur synchrone ou asynchrone (décision 10).

    Mode synchrone : tous les agents LLM agissent à chaque tick de décision.
    Mode asynchrone : chaque agent agit à son propre rythme
    (think_interval_ticks) et subit un délai de traitement ; l'écart entre
    t_prod et t_trait est alors réel et mesurable (C7).
    """

    def __init__(
        self,
        mode: str,
        clock: SimClock,
        rng: random.Random,
        *,
        default_think_interval: int = 20,
    ) -> None:
        if mode not in {"sync", "async"}:
            raise ValueError(f"mode d'exécution inconnu : {mode!r}")
        self.mode = mode
        self.clock = clock
        self.rng = rng
        self.default_think_interval = default_think_interval
        self.agents: dict[str, AgentSchedule] = {}

    def register(self, agent_id: str, *, think_interval: int | None = None) -> None:
        interval = think_interval or self.default_think_interval
        # perturbation déterministe du rythme (même seed → même profil)
        jitter = self.rng.randint(0, max(1, interval // 2))
        self.agents[agent_id] = AgentSchedule(
            agent_id=agent_id, think_interval_ticks=interval + jitter
        )

    def due_agents(self, now: int) -> list[AgentSchedule]:
        """Agents dont c'est le tour de penser au tick `now`."""
        if self.mode == "sync":
            return list(self.agents.values())
        return [a for a in self.agents.values() if a.should_think(now)]

    def schedule_next(self, schedule: AgentSchedule, *, now: int) -> None:
        """Reprogramme un agent après son tour (mode asynchrone)."""
        if self.mode == "async":
            schedule.next_think_tick = now + schedule.think_interval_ticks

    def process(self, schedule: AgentSchedule, *, now: int) -> int:
        """Calcule le t_trait effectif d'une décision pour cet agent.

        - synchrone : traitement au même tick (latence 0 simulée) ;
        - asynchrone : la latence réelle du modèle (mesurée par la passerelle
          LLM) est convertie en ticks et s'ajoute au tick courant.
        """
        if self.mode == "sync":
            return now
        return now + schedule.processing_delay_ticks