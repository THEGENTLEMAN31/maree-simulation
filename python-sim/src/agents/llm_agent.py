"""Agent LLM : mémoire propre (A1), dialogue en langage naturel (A2),
décision via la passerelle LLM (décision 7), RAG (F1, décision 12),
dérives tracées (A4).

La mémoire est un journal de faits textuels datés (event-sourcé, décision 1)
qui influence les décisions : un agent doit pouvoir se souvenir d'un échange
vieux de plusieurs jours simulés et en tenir compte (A1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..llm_gateway import LLMGateway, LLMCallResult
from .base import Agent, Intention, Perception

SYSTEM_TEMPLATE = """Tu es {profile_name} ({agent_id}) à Port-Aubel, pendant la Fête des Lanternes.

Priorité : {priority}
Ce que tu sais au départ : {knows}

Résous la situation d'évacuation en restant strictement dans ton rôle.
Réponds UNIQUEMENT en JSON valide avec cette structure :
{{"explanation": "ton raisonnement", "action": "move|stay|evacuate",
"target_zone": "id_de_zone_ou_null", "exit_choice": "A|B|C|null",
"message": "message langage naturel adressé à un voisin, ou null"}}

Ne jamais sortir du personnage. Ne pas donner de conseils de sécurité génériques."""


@dataclass
class MemoryEntry:
    """Un fait mémorisé, daté en temps simulé (A1)."""

    tick: int
    kind: str  # "observation" | "exchange" | "announcement" | "belief"
    text: str
    source: str | None = None
    importance: float = 0.5

    def to_prompt(self) -> str:
        return f"[J{self.tick}] ({self.kind}) {self.text}"


class LLMAgent(Agent):
    """Agent piloté par un LLM local, avec mémoire et RAG."""

    def __init__(
        self,
        agent_id: str,
        profile_name: str,
        model: str,
        priority: str,
        knows: str,
        temperature: float = 0.3,
    ) -> None:
        super().__init__(agent_id, profile_name)
        self.model = model
        self.priority = priority
        self.knows = knows
        self.temperature = temperature
        self.memory: list[MemoryEntry] = []
        self.belief_safe_exit: str | None = None
        self.belief_danger: bool = False
        self.zone = "scene"
        self.evacuated = False
        self.gateway: LLMGateway | None = None
        self.rag = None  # attaché par l'orchestrateur (injection, décision 12)
        self.last_call: LLMCallResult | None = None
        self.drift_events: list[dict] = field(default_factory=list)

    # -- mémoire (A1) ------------------------------------------------------

    def remember(self, tick: int, kind: str, text: str, *, source: str | None = None) -> None:
        self.memory.append(MemoryEntry(tick=tick, kind=kind, text=text, source=source))
        # mémoire bornée : on garde les 40 faits les plus récents + importants.
        self.memory.sort(key=lambda e: (e.importance, e.tick), reverse=True)
        self.memory = self.memory[:40]

    def recent_memory(self, n: int = 8) -> list[MemoryEntry]:
        return sorted(self.memory, key=lambda e: e.tick, reverse=True)[:n]

    # -- décision ----------------------------------------------------------

    async def decide(self, perception: Perception) -> Intention:
        if self.gateway is None:
            raise RuntimeError("gateway non attaché (orchestrateur requis)")
        rag_text = ""
        if self.rag is not None:
            rag_text = await self.rag.retrieve_for(self, perception)

        system = SYSTEM_TEMPLATE.format(
            profile_name=self.profile_name,
            agent_id=self.agent_id,
            priority=self.priority,
            knows=self.knows,
        )
        mem_txt = "\n".join(e.to_prompt() for e in self.recent_memory(10))

        user = (
            f"Perception (tick {perception.tick}) : zone={perception.zone}, "
            f"fumée_visible={perception.smoke_seen}, "
            f"voisins_visibles={perception.visible_neighbors}, "
            f"annonces={perception.announcements}, "
            f"infos={perception.false_infos}\n"
            f"Mémoire récente :\n{mem_txt or '(aucune)'}\n"
            f"Informations retrouvées :\n{rag_text or '(aucune)'}\n"
            "Décide :"
        )
        result = await self.gateway.chat(
            self.model,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=self.temperature,
        )
        self.last_call = result

        intent = self._parse_decision(result, perception)
        # Mémorise ce qu'il vient de décider (auto-observation).
        from dataclasses import asdict

        self.remember(
            perception.tick,
            "observation",
            f"J'ai décidé : {json.dumps(asdict(intent), ensure_ascii=False, default=str)[:200]}",
        )
        return intent

    def _parse_decision(self, result: LLMCallResult, perception: Perception) -> Intention:
        """Parse la décision JSON ; toute dérive est comptée (A4) et repliée."""
        data = self.gateway.parse_json_robust(result.text) if self.gateway else None
        if data is None or not result.ok:
            self._drift("unparseable_or_error", result.error or "JSON invalide", result)
            # Repli sûr : ne pas bouger.
            return Intention(action="stay", target_zone=perception.zone)

        action = data.get("action", "stay")
        target = data.get("target_zone")
        exit_code = data.get("exit_choice")
        message = data.get("message")

        # A2 : le message modifie ce que le DESTINATAIRE croit — on le publie
        # par événement agent.message (l'orchestrateur le relaie aux voisins).
        if message and isinstance(message, str):
            self._pending_message = message  # consommé par l'orchestrateur
        else:
            self._pending_message = None

        if action not in {"move", "stay", "evacuate"}:
            self._drift("bad_action", action, result)
            action = "stay"
            target = perception.zone

        self.belief_safe_exit = exit_code if exit_code in {"A", "B", "C"} else self.belief_safe_exit
        self.belief_danger = bool(perception.smoke_seen or self.belief_danger)

        return Intention(
            action=action,
            target_zone=target,
            exit_code=exit_code,
            belief_safe_exit=self.belief_safe_exit,
            belief_danger=self.belief_danger,
        )

    def _drift(self, kind: str, detail: str, result: LLMCallResult) -> None:
        """Traitement des dérives (A4, O2) : tracées et comptées."""
        self.drift_events.append({"kind": kind, "detail": detail, "call_id": result.call_id})