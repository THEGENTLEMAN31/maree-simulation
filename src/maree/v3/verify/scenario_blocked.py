"""verify.scenario_blocked — le scénario qui sépare *lire* de *suivre une position*.

Quatre visiteurs **identiques** qui connaissent A et B. À t2, la moitié
apprend « la sortie A est bloquée », l'autre moitié « la sortie B est
bloquée ». À t10, la fumée, **sans annonce**.

La bonne réponse est donc de contourner la sortie crue bloquée :

===========  =============  =========
agent        croit bloquée  doit aller
===========  =============  =========
A01, A02     A              B
A03, A04     B              A
===========  =============  =========

Le défaut du moteur (la sortie la plus confiante, ``A``, à égalité de
confiance initiale) est **faux pour la moitié des agents** : une politique
qui répond « toujours A » ou « la première de la liste » vaut 0,50 *par
construction*. C'est ce qui rend le scénario discriminant entre un modèle
qui lit la mémoire et un modèle qui applique une position.

Ce module est le banc, pas la mesure : les campagnes réelles
(``scripts/v3_campaign_blocked.py``) l'utilisent avec les vrais modèles, et
``tests/v3/test_scenario_blocked.py`` le vérifie avec des stubs — la preuve
que 0,50 est un plafond de méthode, pas une opinion.
"""

from __future__ import annotations

from dataclasses import dataclass

from maree.v3.agents.perception import Message
from maree.v3.core.ids import AgentId
from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import EventBus, MemoryBus
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.world.sample import sample_worldspec

#: la sortie que chaque agent croit bloquée — et donc celle qu'il doit éviter.
BLOCKED: dict[str, str] = {"A01": "A", "A02": "A", "A03": "B", "A04": "B"}

#: confiance du message reçu. Pour un visiteur (herding = 0,8) le poids vaut
#: ``0,8 × (0,3 + 0,7·0,8) = 0,69``, au-dessus du seuil 0,5 de
#: ``_believed_blocked`` : les règles *doivent* éviter la sortie crue bloquée.
TRUST = 0.8

#: instant du message, instant de la fumée, fin du run.
T_MESSAGE = 2
T_SMOKE = 10


def messages() -> tuple[tuple[int, Message], ...]:
    """« La sortie X est bloquée », chacun pour la sortie qui le concerne."""
    return tuple(
        (i + 1, Message(f"La sortie {label} est bloquée", AgentId(99), T_MESSAGE, TRUST))
        for i, label in enumerate(["A", "A", "B", "B"])
    )


def timeline() -> list[Timestep]:
    """Le message à t2, la fumée seule à t10 (aucune annonce : pas de confondant)."""
    return [
        Timestep(T_MESSAGE, messages=messages()),
        Timestep(T_SMOKE, smoke=True),
        Timestep(20),
        Timestep(30),
        Timestep(40),
    ]


def build(
    seed: int = 1,
    policy: PolicyName = PolicyName.RULES,
    alias: str | None = None,
    bus: EventBus | None = None,
    run_id: str | None = None,
) -> Simulation:
    """Monte le scénario (monde fixe, quatre visiteurs) sans le jouer."""
    sim = Simulation(
        seed=seed,
        policy=policy,
        bus=bus or MemoryBus(),
        run_id=run_id or f"blocked_{alias or 'rules'}_s{seed}",
    ).build(sample_worldspec())
    sim.spawn("visiteur", 4, frozenset({"A", "B"}), llm_alias=alias)
    return sim


@dataclass(frozen=True, slots=True)
class BlockedScore:
    """Ce que le scénario mesure : la sortie évitée, agent par agent."""

    choices: dict[str, str | None]
    #: agents ayant choisi une sortie *autre* que celle qu'ils croient bloquée.
    avoided: int
    total: int

    @property
    def accuracy(self) -> float:
        return self.avoided / self.total if self.total else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "choices": self.choices,
            "avoided": self.avoided,
            "total": self.total,
            "accuracy": round(self.accuracy, 3),
        }


def score(sim: Simulation) -> BlockedScore:
    """Note le run : la **dernière** cible d'évacuation de chaque agent."""
    last: dict[str, str] = {}
    for row in sim.log.rows:
        if row.action.startswith("évacuer") and row.target:
            last[row.agent] = row.target
    choices: dict[str, str | None] = {
        agent: last.get(agent) for agent in sorted(BLOCKED)
    }
    avoided = sum(
        1
        for agent, blocked in BLOCKED.items()
        if choices.get(agent) not in (None, blocked)
    )
    return BlockedScore(choices=choices, avoided=avoided, total=len(BLOCKED))


def run(
    seed: int = 1,
    policy: PolicyName = PolicyName.RULES,
    alias: str | None = None,
    bus: EventBus | None = None,
) -> BlockedScore:
    """Monte, joue et note le scénario d'un trait (raccourci des campagnes)."""
    sim = build(seed=seed, policy=policy, alias=alias, bus=bus)
    sim.run(timeline())
    return score(sim)


__all__ = [
    "BLOCKED",
    "TRUST",
    "T_MESSAGE",
    "T_SMOKE",
    "BlockedScore",
    "build",
    "messages",
    "run",
    "score",
    "timeline",
]
