"""Agents : interface uniforme `decide(perception, mémoire) -> intention`.

Décision 6 : agents LLM et agents à règles exposent la même interface,
ce qui rend la baseline (E1) triviale et la comparaison valide.
"""
from .base import Agent, Intention, Perception
from .llm_agent import LLMAgent
from .profiles import build_agents, split_agents
from .rules_agent import RulesAgent

__all__ = [
    "Agent",
    "Intention",
    "Perception",
    "LLMAgent",
    "RulesAgent",
    "build_agents",
    "split_agents",
]