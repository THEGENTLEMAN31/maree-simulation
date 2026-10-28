"""Les trois horloges de MARÉE.

C'est la décision d'architecture la plus importante de la v2, et celle
qui manquait à la v1.

    physique   0,05 s   JuPedSim : positions, contacts, files d'attente
    cognition 10,00 s   LangGraph + LLM : décision, RAG, mémoire
    rendu      0,10 s   Godot : interpolation entre deux instantanés

Conséquence : le mouvement est fluide, mais un agent ne « réfléchit »
que toutes les 10 secondes simulées. C'est ce qui rend une foule de
60 agents tenable sur 4 Go de VRAM.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Clocks:
    """Cadences du monde. Toutes les valeurs viennent du YAML (décision 11)."""

    physics_dt: float = 0.05
    cognition_s: float = 10.0
    render_hz: float = 10.0

    @property
    def steps_per_tick(self) -> int:
        """Nombre de pas physiques entre deux décisions."""
        return max(1, round(self.cognition_s / self.physics_dt))

    @property
    def render_s(self) -> float:
        return 1.0 / self.render_hz

    def tick_to_seconds(self, tick: int) -> float:
        return tick * self.cognition_s

    def seconds_to_tick(self, seconds: float) -> int:
        return int(seconds // self.cognition_s)


@dataclass(frozen=True, slots=True)
class SimClock:
    """Horloge logique. Jamais l'horloge système (décision 3)."""

    tick: int = 0
    clocks: Clocks = field(default_factory=Clocks)

    def advance(self) -> SimClock:
        return SimClock(tick=self.tick + 1, clocks=self.clocks)

    @property
    def seconds(self) -> float:
        return self.clocks.tick_to_seconds(self.tick)

    def fmt(self) -> str:
        """« 7:30 » — lisible par un humain, pour le HUD."""
        total = int(self.seconds)
        return f"{total // 60}:{total % 60:02d}"
