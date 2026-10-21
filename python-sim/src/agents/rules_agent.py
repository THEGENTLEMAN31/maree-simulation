"""Agent à règles (baseline E1 + population de fond A6).

Baseline : force sociale (Helbing, simplifiée) plus choix de sortie par
proximité et visibilité, mêmes scénarios et mêmes graines que la version LLM.

L'agent expose le MÊME contrat `decide(perception) -> intention` (décision 6),
ce qui rend la comparaison LLM / règles valide (E1).
"""
from __future__ import annotations

import random

from .base import Agent, Intention, Perception

# Pondération de la force sociale (modèle Helbing simplifié).
W_DESIRED = 1.0      # aller vers sa sortie cible
W_REPULSION = 0.4    # éviter les zones de fumée
W_FOLLOW = 0.6       # suivre le voisin (I4 : suivi de meneur)

# Définition du graphe (republiée ici pour que la baseline reste autonome).
ZONES: dict[str, list[str]] = {
    "scene": ["nord", "ouest"],
    "nord": ["scene", "stand1", "passerelle"],
    "ouest": ["scene", "stand2"],
    "stand1": ["nord", "passerelle", "sud_est"],
    "stand2": ["ouest", "sud_ouest"],
    "passerelle": ["nord", "stand1", "sortie_b"],
    "sud_est": ["stand1", "sortie_a"],
    "sud_ouest": ["stand2", "sortie_c"],
    "sortie_a": ["sud_est"],
    "sortie_b": ["passerelle"],
    "sortie_c": ["sud_ouest"],
}
EXIT_OF_ZONE = {"sortie_a": "A", "sortie_b": "B", "sortie_c": "C"}


def _shortest_path(start: str, goal: str) -> list[str]:
    """BFS simple (déterministe) sur le graphe des zones."""
    from collections import deque

    queue: deque[list[str]] = deque([[start]])
    visited = {start}
    while queue:
        path = queue.popleft()
        node = path[-1]
        if node == goal:
            return path
        for nxt in ZONES.get(node, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append(path + [nxt])
    return [start]


class RulesAgent(Agent):
    """Agent déterministe : poids sur les sorties selon distance, fumée,
    visibilité et suivi du voisin."""

    def __init__(self, agent_id: str, profile_name: str, rng: random.Random) -> None:
        super().__init__(agent_id, profile_name)
        self.rng = rng
        # Hétérogénéité déterministe (décision 3) : sans préférences variées,
        # tout le monde part vers A et aucun effet de meneur n'est mesurable.
        self.exit_pref: str | None = rng.choice(["A", "A", "B", "B", "C"])
        self.zone = "scene"
        self.evacuated = False
        # Levier expérimental X2 « avec meneurs vs sans meneur » : à zéro, la
        # foule cesse de suivre le voisin (I4 chute, I3 change).
        self.follow_weight: float = W_FOLLOW

    async def decide(self, perception: Perception) -> Intention:
        zone = perception.zone
        preferred_exit = self._choose_exit(perception)
        if preferred_exit is None:
            return Intention(action="stay", target_zone=zone)

        goal_zone = f"sortie_{preferred_exit.lower()}"
        path = _shortest_path(zone, goal_zone)
        next_zone = path[1] if len(path) > 1 else goal_zone
        if next_zone.startswith("sortie_"):
            return Intention(
                action="evacuate",
                target_zone=next_zone,
                exit_code=EXIT_OF_ZONE[next_zone],
                belief_safe_exit=preferred_exit,
                belief_danger="smoke" if perception.smoke_seen else False,
            )
        return Intention(
            action="move",
            target_zone=next_zone,
            belief_safe_exit=preferred_exit,
            belief_danger="smoke" if perception.smoke_seen else False,
        )

    def _choose_exit(self, perception: Perception) -> str | None:
        """Score des sorties connues : proximité, sûreté, suivi du voisin."""
        candidates = ["A", "B", "C"]
        best: str | None = None
        best_score = -1e9
        desired = self.exit_pref or "A"
        # X2 : un agent n'évacue pas par une sortie qu'il sait fermée.
        open_candidates = [c for c in candidates if c not in perception.blocked_exits]
        if open_candidates:
            candidates = open_candidates
        # A2 / I4 : la sortie majoritaire parmi les voisins visibles. C'est
        # elle qu'on suit — pas une constante — sinon le levier X2 ne mesure
        # rien (il ne changeait aucun comportement).
        beliefs = list(perception.neighbor_beliefs.values())
        modal = max(set(beliefs), key=beliefs.count) if beliefs else None
        for code in candidates:
            score = -abs(_exit_rank(code) - _exit_rank(desired)) * W_DESIRED
            if perception.smoke_seen:
                score -= W_REPULSION  # la fumée rend l'environnement chargé
            if modal and code == modal:
                # poids x2 : suivre le groupe peut l'emporter sur la préférence
                score += self.follow_weight * 2.0
            if code in perception.exits_known:
                score += 0.5
            if score > best_score:
                best_score = score
                best = code
        return best

    # -- introspection pour Godot (D2) -------------------------------------

    def explanation(self, perception: Perception) -> dict:
        """Règle appliquée, affichée dans l'inspecteur Godot pour les agents
        à règles."""
        return {
            "kind": "rules",
            "zone": self.zone,
            "exit_pref": self.exit_pref,
            "chosen": self._choose_exit(perception),
            "weights": {
                "desired": W_DESIRED,
                "repulsion": W_REPULSION,
                "follow": self.follow_weight,
            },
        }


def _exit_rank(code: str) -> int:
    return {"A": 0, "B": 1, "C": 2}[code]