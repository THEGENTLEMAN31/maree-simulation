"""Adaptateur JuPedSim : les cas qui plantent.

Ces tests touchent le vrai moteur (pas le faux de `test_simulation.py`).
Ils sont lents à la marge (quelques centaines de pas) mais ils attrapent
exactement les erreurs que le moteur lève et qu'un faux ne lève jamais.
"""

from __future__ import annotations

from maree.adapters.physics.jupedsim_physics import JuPedSimPhysics
from maree.domain.geometry import Plan
from maree.ports import Destination


def _avance(physics: JuPedSimPhysics, pas: int) -> None:
    for _ in range(pas):
        physics.step()


def test_fermer_une_issue_apres_des_sorties_ne_plante_pas(plan: Plan) -> None:
    """Régression : `switch_agent_journey` sur un agent déjà sorti.

    JuPedSim retire les agents qui franchissent une issue. Fermer A
    ensuite les parcourait tous et levait
    « RuntimeError: Trying to access unknown Agent N ».
    """
    physics = JuPedSimPhysics(plan, seed=0)
    # A01 part vers A et sort vite ; A02 reste au fond, loin de A.
    physics.add_agent("A01", (29.0, 33.0), Destination.to_exit("A"))
    physics.add_agent("A02", (10.0, 10.0), Destination.to_point((10.0, 10.0)))

    _avance(physics, 400)
    assert "A01" in physics.evacuated()

    physics.close_exit("A")  # ne doit pas lever

    # A02, toujours présent, peut être redirigé vers une autre issue.
    physics.set_destination("A02", Destination.to_exit("B"))
    _avance(physics, 10)


def test_rediriger_un_agent_sorti_ne_fait_rien(plan: Plan) -> None:
    physics = JuPedSimPhysics(plan, seed=0)
    physics.add_agent("A01", (29.0, 33.0), Destination.to_exit("A"))
    _avance(physics, 400)
    assert "A01" in physics.evacuated()

    physics.set_destination("A01", Destination.to_exit("B"))
    _avance(physics, 5)
