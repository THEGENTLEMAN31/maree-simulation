"""verify.worlds — un **échantillon de mondes**, pas un monde unique.

Le protocole pré-enregistré disait « une graine = un monde » : la variance
géométrique doit être échantillonnée, sinon un goulot calibré sur une salle ne
dit rien des autres. `scenario_crowd` fournit un monde fixe (celui de la
calibration) ; ce module en tire une **famille** de salles de même
distribution, et vérifie que chacune produit encore un goulot mesurable.

La distribution est étroite **exprès** : on veut la même situation sociale
(deux issues, une petite salle, 60 agents), pas cinq bâtiments différents.
Changer la taille de la salle change la densité ; changer le nombre d'issues
changerait la question.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from maree.v3.world.generate import ExitSpec, hall_config
from maree.v3.world.worldspec import WorldSpec, from_dict

#: bornes de la famille (m) — autour de `crowd_hall` (22 × 16, issues 1,2 m).
WIDTH_RANGE = (20.0, 24.0)
HEIGHT_RANGE = (14.0, 18.0)
EXIT_WIDTH_RANGE = (1.1, 1.3)
#: position des issues, en fraction de la largeur (coin haut-gauche / bas-droite).
POS_A = (0.22, 0.34)
POS_B = (0.66, 0.78)


@dataclass(frozen=True, slots=True)
class CrowdWorld:
    """Les paramètres tirés, journalisables et reproductibles."""

    seed: int
    width: float
    height: float
    exit_width: float
    center_a: float
    center_b: float

    @property
    def area(self) -> float:
        return self.width * self.height

    def as_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "width": round(self.width, 2),
            "height": round(self.height, 2),
            "area": round(self.area, 1),
            "exit_width": round(self.exit_width, 2),
            "center_a": round(self.center_a, 2),
            "center_b": round(self.center_b, 2),
        }


def draw(seed: int) -> CrowdWorld:
    """Tire un monde de la famille (déterministe à graine égale)."""
    rng = np.random.default_rng(seed)
    width = float(rng.uniform(*WIDTH_RANGE))
    height = float(rng.uniform(*HEIGHT_RANGE))
    exit_width = float(rng.uniform(*EXIT_WIDTH_RANGE))
    center_a = float(rng.uniform(*POS_A) * width)
    center_b = float(rng.uniform(*POS_B) * width)
    return CrowdWorld(seed, width, height, exit_width, center_a, center_b)


def build(spec: CrowdWorld) -> WorldSpec:
    """Le WorldSpec correspondant (validé par `Simulation.build`)."""
    return from_dict(
        hall_config(
            world_id=f"crowd_w{spec.seed}",
            width=spec.width,
            height=spec.height,
            exits=(
                ExitSpec("A", "top", spec.center_a, spec.exit_width),
                ExitSpec("B", "bottom", spec.center_b, spec.exit_width),
            ),
        )
    )


__all__ = [
    "EXIT_WIDTH_RANGE",
    "HEIGHT_RANGE",
    "POS_A",
    "POS_B",
    "WIDTH_RANGE",
    "CrowdWorld",
    "build",
    "draw",
]
