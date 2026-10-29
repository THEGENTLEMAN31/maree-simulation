"""Boucle de décision d'un agent — LangGraph.

    START → recall → (retrieve ?) → decide → validate → END

Pourquoi un graphe plutôt qu'une fonction : la décision n'est pas linéaire.
Un agent qui a déjà une croyance solide n'a pas besoin d'interroger le RAG ;
un agent qui découvre la fumée, si. L'arête conditionnelle rend ce choix
explicite et lisible — et c'est exactement ce que le cadrage autorise
(LangGraph figure dans la liste des frameworks du sujet).

Ce que LangGraph ne fait PAS ici :

    - il n'est pas la source de vérité : aucun checkpointer persistant,
      l'état entre et sort du graphe à chaque décision ;
    - il ne parle pas au modèle directement : tout passe par `LLMPort`,
      donc par la passerelle unique (décision 7), qui journalise prompt,
      graine, sortie brute et durée (condition du rejeu E3).

Un seul graphe est compilé par run ; il est invoqué avec l'état de
l'agent. Le coût d'un passage de nœud est de l'ordre de la milliseconde,
négligeable devant les ~2,8 s d'un appel LLM.
"""

from __future__ import annotations

import hashlib
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from maree.agents.parsing import parse_decision
from maree.agents.profiles import Profile
from maree.agents.rules import rules_decide
from maree.agents.triggers import Percept
from maree.domain.geometry import Plan
from maree.domain.ids import AgentId
from maree.domain.intentions import Intention, IntentionKind
from maree.ports import ChatMessage, LLMPort, MemoryPort, RetrieverPort

#: Ce que le LLM écrit quand il n'a pas de cible, mais qu'il remplit quand même
#: le champ. Comparé en minuscules, après `strip()`.
_EMPTY_TARGETS = {"", "null", "none", "aucun", "aucune", "n/a", "undefined"}


class AgentState(TypedDict, total=False):
    agent_id: AgentId
    profile: str
    tick: int
    percept: dict[str, Any]
    trigger: str
    memories: list[dict[str, Any]]
    beliefs: dict[str, Any]
    passages: list[dict[str, Any]]
    intention: dict[str, Any] | None
    reasoning: str
    llm: dict[str, Any]
    #: Vrai si l'intention finale vient des règles et non du modèle.
    fallback: bool


class DecisionGraph:
    """Graphe de décision partagé par tous les agents LLM d'un run."""

    def __init__(
        self,
        *,
        llm: LLMPort,
        retriever: RetrieverPort | None,
        memory: MemoryPort,
        plan: Plan,
        max_tokens: int = 256,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._memory = memory
        self._plan = plan
        self._max_tokens = max_tokens
        self._compiled = self._build()

    # ---- construction -----------------------------------------
    def _build(self):
        graph = StateGraph(AgentState)
        graph.add_node("recall", self._recall)
        graph.add_node("retrieve", self._retrieve)
        graph.add_node("decide", self._decide)
        graph.add_node("validate", self._validate)

        graph.add_edge(START, "recall")
        graph.add_conditional_edges(
            "recall",
            self._needs_rag,
            {"retrieve": "retrieve", "decide": "decide"},
        )
        graph.add_edge("retrieve", "decide")
        graph.add_edge("decide", "validate")
        graph.add_edge("validate", END)
        return graph.compile()

    # ---- nœuds ------------------------------------------------
    def _recall(self, state: AgentState) -> AgentState:
        """Rappel borné : 5 souvenirs, classés, jamais ceux d'un autre."""
        percept = state["percept"]
        query = " ".join(
            filter(
                None,
                [
                    "fumee" if percept.get("smoke_visible") else "",
                    "sortie fermee" if state.get("trigger") == "sortie_fermee" else "",
                    " ".join(m.get("content", "") for m in percept.get("messages", [])),
                ],
            )
        )
        episodes = self._memory.recall(
            state["agent_id"], query=query, k=5, tick=state["tick"]
        )
        beliefs = self._memory.beliefs(state["agent_id"])
        return {
            **state,
            "memories": [e.to_dict() for e in episodes],
            "beliefs": beliefs.snapshot(),
        }

    def _needs_rag(self, state: AgentState) -> str:
        """Arête conditionnelle : le RAG n'est utile que si l'agent doute."""
        if self._retriever is None:
            return "decide"
        if state.get("trigger") in {"fumee_visible", "annonce", "sortie_fermee"}:
            return "retrieve"
        # Croyance vide ou très faible : il faut chercher.
        beliefs = state.get("beliefs") or {}
        best = max((b.get("confidence", 0.0) for b in beliefs.values()), default=0.0)
        return "retrieve" if best < 0.5 else "decide"

    async def _retrieve(self, state: AgentState) -> AgentState:
        profile = state["profile"]
        query = self._query_for(state)
        passages = await self._retriever.retrieve(  # type: ignore[union-attr]
            query, profile=profile, tick=state["tick"], k=3
        )
        return {
            **state,
            "passages": [
                {
                    "doc_id": p.doc_id,
                    "text": p.text,
                    "score": round(p.score, 4),
                    "collection": p.collection,
                }
                for p in passages
            ],
        }

    async def _decide(self, state: AgentState) -> AgentState:
        prompt = self._build_prompt(state)
        result = await self._llm.chat(
            [
                ChatMessage("system", self._system_for(state)),
                ChatMessage("user", prompt),
            ],
            seed=self._seed_for(state),
            max_tokens=self._max_tokens,
        )
        parsed = parse_decision(result.text)
        return {
            **state,
            "intention": parsed,
            "reasoning": (parsed or {}).get("reason", ""),
            "llm": {
                "prompt": result.prompt,
                "seed": result.seed,
                "model": result.model,
                "raw_output": result.text,
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
                "duration_s": round(result.duration_s, 3),
                "ok": result.ok,
                "error": result.error,
            },
        }

    def _validate(self, state: AgentState) -> AgentState:
        """Aucune intention invalide ne sort du graphe.

        Si le modèle propose une sortie qui n'existe pas, ou une action
        inconnue, on replie sur les règles. Le repli est journalisé, jamais
        silencieux (décision 7).
        """
        parsed = state.get("intention") or {}
        intention = self._to_intention(parsed, state)
        if intention is None:
            intention = rules_decide(
                _percept_from_state(state), self._plan, profile=state["profile"]
            )
            state = {
                **state,
                "fallback": True,
                "reasoning": f"[repli regles] {intention.reason}",
            }
        return {**state, "intention": intention.to_dict()}

    # ---- API --------------------------------------------------
    async def decide(
        self,
        *,
        agent_id: AgentId,
        profile: Profile,
        percept: Percept,
        trigger: str,
    ) -> tuple[Intention, AgentState]:
        state: AgentState = {
            "agent_id": agent_id,
            "profile": profile.id,
            "tick": percept.tick,
            "trigger": trigger,
            "percept": _percept_to_dict(percept),
        }
        out = await self._compiled.ainvoke(state)
        return _intention_from_dict(out.get("intention")), out

    # ---- helpers ----------------------------------------------
    def _system_for(self, state: AgentState) -> str:
        from maree.agents.profiles import get_profile

        return get_profile(state["profile"]).system_prompt

    def _seed_for(self, state: AgentState) -> int:
        """Graine déterministe : run + agent + tick (décision 3).

        `hash()` de Python est salé par processus (PYTHONHASHSEED) : il ne
        peut pas servir ici. On utilise SHA-256, stable entre machines.
        """
        raw = f"{state['profile']}:{state['agent_id']}:{state['tick']}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return int(digest, 16) % 2_147_483_647

    def _query_for(self, state: AgentState) -> str:
        percept = state["percept"]
        bits = ["évacuation esplanade"]
        if percept.get("smoke_visible"):
            bits.append("fumée incendie")
        if state.get("trigger") == "sortie_fermee":
            bits.append("sortie fermée itinéraire alternatif")
        for m in percept.get("messages", []):
            bits.append(m.get("content", ""))
        return " ".join(bits)[:400]

    def _build_prompt(self, state: AgentState) -> str:
        percept = state["percept"]
        beliefs = state.get("beliefs") or {}
        lines = [
            f"Tick {state['tick']} — tu es en {percept.get('zone') or 'esplanade'}.",
            f"Position : {percept.get('position')}.",
            f"Fumée visible : {'oui' if percept.get('smoke_visible') else 'non'}"
            + (
                f" (intensité {percept.get('smoke_intensity'):.2f})"
                if percept.get("smoke_visible")
                else ""
            ),
            f"Densité locale : {percept.get('density', 0):.2f} pers/m².",
            f"Sorties ouvertes : {', '.join(sorted(percept.get('exits_open', []))) or 'aucune'}.",
        ]
        if beliefs:
            lines.append(
                "Tes croyances : "
                + "; ".join(
                    f"{k} {v['confidence']:.2f} (source {v['source']})"
                    for k, v in sorted(beliefs.items())
                )
            )
        else:
            lines.append("Tes croyances : aucune.")
        if percept.get("announcement"):
            lines.append(f"Annonce officielle : {percept['announcement']}")
        if percept.get("missing_kin"):
            lines.append(
                f"Un proche manque depuis {percept.get('missing_kin_ticks', 0)} ticks."
            )
        for m in percept.get("messages", []):
            lines.append(f"Message de {m.get('sender')} : {m.get('content')}")
        if state.get("memories"):
            lines.append("Souvenirs :")
            lines.extend(f"  - t{e['tick']} {e['content']}" for e in state["memories"])
        if state.get("passages"):
            lines.append("Extraits du guide :")
            lines.extend(f"  - {p['text'][:180]}" for p in state["passages"])
        return "\n".join(lines)

    def _to_intention(
        self, parsed: dict[str, Any], state: AgentState
    ) -> Intention | None:
        try:
            kind = IntentionKind(parsed.get("action", ""))
        except ValueError:
            return None
        target = parsed.get("target")
        # Le LLM écrit parfois `"target": "null"` (la chaîne), ou une cible
        # qui ne veut rien dire pour l'action choisie. Sans ce nettoyage,
        # `stay` partait au journal avec `target: "null"`, et le client
        # dessinait une cible sur un agent immobile.
        if isinstance(target, str):
            cleaned = target.strip()
            target = None if cleaned.lower() in _EMPTY_TARGETS else cleaned
        # Une intention qui mène physiquement à une sortie doit porter un
        # identifiant de sortie réel. `guide` et `follow` acceptaient une
        # étiquette ou une sortie dans le champ agent : l'agent croyait
        # alors à une fermeture inexistante, ou se figeait sur place.
        if kind in {IntentionKind.GO_EXIT, IntentionKind.GUIDE}:
            if target not in self._plan.exits:
                return None
        elif kind is IntentionKind.GO_ZONE:
            if target not in self._plan.zones:
                return None
        elif kind is IntentionKind.FOLLOW:
            if target in self._plan.exits:
                # « suivre la foule vers C » : c'est une sortie, pas un agent.
                kind = IntentionKind.GO_EXIT
            elif not (isinstance(target, str) and target.startswith("A")):
                return None
        elif kind is IntentionKind.SEARCH:
            target = None  # chercher un proche ne vise personne de précis
        elif kind is IntentionKind.STAY:
            # Rester ne vise rien : `_apply` ignore la cible de toute façon,
            # mais le journal et le client, eux, la liraient.
            target = None
        # Une cible de sortie doit être une sortie que le profil
        # **connaît**, pas seulement une sortie du plan. Sans ce garde, un
        # visiteur (qui ne connaît que A) pouvait nommer B : la cible
        # passait la validation, et l'agent allait vers une issue qu'il
        # ignorait. Mesuré sur la campagne pré-correctif : 108 décisions
        # dans X1, 349 dans X4, 12 dans X6.
        if kind in {IntentionKind.GO_EXIT, IntentionKind.GUIDE}:
            from maree.agents.profiles import get_profile

            if not get_profile(state["profile"]).knows(str(target)):
                return None
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        return Intention(
            kind=kind,
            target=target,
            reason=str(parsed.get("reason", ""))[:200],
            tick=state["tick"],
            confidence=max(0.0, min(1.0, confidence)),
        )


# ------------------------------------------------------------
# Conversions (le graphe transporte des dicts, pas des objets : l'état
# LangGraph doit rester sérialisable pour être journalisé tel quel).
# ------------------------------------------------------------
def _percept_to_dict(p: Percept) -> dict[str, Any]:
    return {
        "tick": p.tick,
        "position": list(p.position),
        "zone": p.zone,
        "smoke_visible": p.smoke_visible,
        "smoke_intensity": p.smoke_intensity,
        "density": p.density,
        "exits_open": sorted(p.exits_open),
        "messages": [
            {"sender": m.sender, "content": m.content, "tick": m.tick, "claim": m.claim}
            for m in p.messages
        ],
        "nearby": list(p.nearby),
        "announcement": p.announcement,
        "missing_kin": p.missing_kin,
        "missing_kin_ticks": p.missing_kin_ticks,
    }


def _percept_from_state(state: AgentState) -> Percept:
    d = state["percept"]
    from maree.agents.triggers import Message

    return Percept(
        tick=d["tick"],
        position=tuple(d["position"]),  # type: ignore[arg-type]
        zone=d.get("zone"),
        smoke_visible=bool(d.get("smoke_visible")),
        smoke_intensity=float(d.get("smoke_intensity", 0.0)),
        density=float(d.get("density", 0.0)),
        exits_open=frozenset(d.get("exits_open", [])),
        messages=tuple(
            Message(
                sender=m["sender"], content=m["content"], tick=m["tick"], claim=m.get("claim")
            )
            for m in d.get("messages", [])
        ),
        nearby=tuple(d.get("nearby", [])),
        announcement=d.get("announcement"),
        missing_kin=bool(d.get("missing_kin")),
        missing_kin_ticks=int(d.get("missing_kin_ticks", 0)),
    )


def _intention_from_dict(d: dict[str, Any] | None) -> Intention:
    if not d:
        return Intention(IntentionKind.STAY, None, "aucune décision", 0)
    return Intention(
        kind=IntentionKind(d["kind"]),
        target=d.get("target"),
        reason=d.get("reason", ""),
        tick=int(d.get("tick", 0)),
        confidence=float(d.get("confidence", 0.0)),
    )
