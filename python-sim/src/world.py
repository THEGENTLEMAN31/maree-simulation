"""Monde : état courant, vérité terrain, fumée, sorties, zones.

Le moteur de monde est DÉTERMINISTE (décision 3) : il ne dépend que des
variables d'entrée et du générateur seedé par run/agent. La vérité terrain
(extension de la fumée, état des sorties) est connue du moteur, jamais des
agents (C6, décision 8 : Godot ne calcule rien).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .config import WorldSpec


@dataclass
class ExitState:
    """État d'une sortie (vérité terrain)."""

    code: str
    capacity: int          # débit max (personnes / tick)
    blocked: bool = False
    smoke_exposed: bool = False   # atteinte par la fumée


@dataclass
class Zone:
    """Zone de l'esplanade (modèle en graphe pour le niveau 1)."""

    id: str
    label: str
    x: float
    y: float
    neighbors: list[str] = field(default_factory=list)


class World:
    """Port-Aubel, esplanade de la Fête des Lanternes (décision 11)."""

    def __init__(self, spec: WorldSpec, rng: random.Random) -> None:
        self.spec = spec
        self.rng = rng
        self.smoke_level = 0.0  # 0..1 étendue relative
        self.smoke_zones: set[str] = set()
        self._build_esplanade()

    def _build_esplanade(self) -> None:
        # 12 zones reliées (niveau 1), 3 sorties inégales.
        self.zones: dict[str, Zone] = {
            "scene": Zone("scene", "Scène", 0.0, 0.0, ["nord", "ouest"]),
            "nord": Zone("nord", "Partie nord", 0.5, 0.8, ["scene", "stand1", "passerelle"]),
            "ouest": Zone("ouest", "Partie ouest", -0.8, 0.2, ["scene", "stand2"]),
            "stand1": Zone("stand1", "Stand est", 0.85, 0.5, ["nord", "passerelle", "sud_est"]),
            "stand2": Zone("stand2", "Stand ouest", -0.85, -0.2, ["ouest", "sud_ouest"]),
            "passerelle": Zone("passerelle", "Passerelle", 0.55, 0.95, ["nord", "stand1", "sortie_b"]),
            "sud_est": Zone("sud_est", "Sud-est (fumée)", 0.7, -0.6, ["stand1", "sortie_a"]),
            "sud_ouest": Zone("sud_ouest", "Sud-ouest", -0.6, -0.7, ["stand2", "sortie_c"]),
            "sortie_a": Zone("sortie_a", "Sortie A (large)", 1.0, -0.9, ["sud_est"]),
            "sortie_b": Zone("sortie_b", "Sortie B (goulot)", 0.95, 1.0, ["passerelle"]),
            "sortie_c": Zone("sortie_c", "Sortie C (discrète)", -1.0, -0.9, ["sud_ouest"]),
        }
        # Déclaration explicite des sorties (vérifiées par le monde).
        self.exits: dict[str, ExitState] = {
            "A": ExitState(code="A", capacity=8),
            "B": ExitState(code="B", capacity=2),
            "C": ExitState(code="C", capacity=4),
        }
        self.zone_of_exit = {"sortie_a": "A", "sortie_b": "B", "sortie_c": "C"}

    # -- vérité terrain (moteur uniquement) --------------------------------

    def tick_world(self, tick: int) -> bool:
        """Fait évoluer la fumée (loi déterministe simple). Retourne True
        si la fumée a changé (un événement world.smoke_update est alors publié
        par l'orchestrateur)."""
        if tick < self.spec.smoke_tick:
            return False
        # La fumée s'étend de façon déterministe : +5 % à chaque pas de 6 ticks.
        if tick % self.spec.smoke_spread_interval == 0 and self.smoke_level < 1.0:
            self.smoke_level = max(0.0, min(1.0, self.smoke_level + 0.05))
            if self.smoke_level >= 0.4:
                self.smoke_zones.add("sud_est")
            if self.smoke_level >= 0.7:
                self.smoke_zones.add("stand1")
            if self.smoke_level >= 0.9:
                self.smoke_zones.add("passerelle")
            return True
        return False

    def ground_truth_safe_exit(self) -> str:
        """Sortie réellement sûre, connue du moteur seulement."""
        # B est un goulot ; A reste large ; C est discrète mais fonctionnelle.
        if not self.exits["A"].blocked and not self.exits["A"].smoke_exposed:
            return "A"
        return "C" if not self.exits["C"].blocked else "B"

    def zone_label(self, zone_id: str) -> str:
        return self.zones[zone_id].label