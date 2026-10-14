"""Profils de la population (C2 : pilotée par la config YAML).

Population cible : 60 agents = 15 LLM + 45 règles.
La répartition des modèles respecte la règle d'attribution A5 (rôle et
expérience, jamais une catégorie sociale) : les profils à expérience
(sécurité, habitués) utilisent le plus grand modèle.

Les valeurs par défaut ci-dessous (priorités, connaissances) complètent la
config ; les counts et modèles viennent du YAML (décision 11, C2).
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import ProfileSpec

from .base import Agent
from .llm_agent import LLMAgent
from .rules_agent import RulesAgent

# Compléments par profil (priorité, savoir initial) — docs/cadrage § Population.
PROFILE_META: dict[str, dict] = {
    "famille": {
        "priority": "Retrouver l'enfant égaré avant de partir",
        "knows": "son entrée d'arrivée",
    },
    "securite": {
        "priority": "Guider, sa parole pèse plus",
        "knows": "les trois sorties et le protocole",
    },
    "habitue": {
        "priority": "Partir vite, par la sortie C",
        "knows": "la sortie discrète (C)",
    },
    "visiteur": {
        "priority": "Comprendre avant d'agir",
        "knows": "son entrée d'arrivée",
    },
    "amis": {
        "priority": "Filmer plutôt que partir",
        "knows": "son entrée d'arrivée",
    },
    "foule": {
        "priority": "Suivre le flux",
        "knows": "rien",
    },
}


def build_agents(population: list["ProfileSpec"], rng: random.Random) -> list[Agent]:
    """Construit les agents à partir de la config (C2).

    Ordre canonique : trié par identifiant (décision 3).
    """
    agents: list[Agent] = []
    for spec in population:
        meta = PROFILE_META.get(spec.name, {})
        for i in range(spec.count):
            agent_id = f"{spec.name}_{i + 1:02d}"
            if spec.kind == "rules":
                agents.append(
                    RulesAgent(agent_id=agent_id, profile_name=spec.name, rng=rng)
                )
            else:
                agents.append(
                    LLMAgent(
                        agent_id=agent_id,
                        profile_name=spec.name,
                        model=spec.model or "gemma4-e2b",
                        priority=spec.priority or meta.get("priority", ""),
                        knows=spec.knows_at_start or meta.get("knows", ""),
                        temperature=spec.temperature,
                    )
                )
    agents.sort(key=lambda a: a.agent_id)
    return agents


def split_agents(agents: list[Agent]) -> tuple[list[LLMAgent], list[RulesAgent]]:
    """Sépare la population en agents LLM et agents à règles (baseline E1)."""
    llm: list[LLMAgent] = []
    rules: list[RulesAgent] = []
    for a in agents:
        if isinstance(a, LLMAgent):
            llm.append(a)
        elif isinstance(a, RulesAgent):
            rules.append(a)
    return llm, rules