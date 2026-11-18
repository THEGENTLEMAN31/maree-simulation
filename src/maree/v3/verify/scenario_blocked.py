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

from dataclasses import dataclass, field

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
    """Ce que le scénario mesure : la sortie évitée, **par décision**.

    D14 : garder seulement la dernière cible faisait passer une politique qui
    se corrige à t10 pour une politique qui a bien choisi à t2. On publie donc
    trois choses distinctes :

    - ``choices`` : la dernière cible d'évacuation de chaque agent (l'état
      final, celui que le corps suit) ;
    - ``first_choices`` : la **première** cible d'évacuation (le choix fait
      avant toute correction) ;
    - ``decisions_to_blocked`` / ``decisions_total`` : la part des décisions
      qui visent une sortie **crue bloquée** — c'est le coût réel, celui que
      la physique transforme en mètres parcourus au mauvais endroit.
    """

    choices: dict[str, str | None]
    avoided: int
    total: int
    first_choices: dict[str, str | None] = field(default_factory=dict)
    decisions_to_blocked: int = 0
    decisions_total: int = 0
    #: décisions dont la cible a été **résolue par le moteur** au lieu du
    #: modèle (petit tier : « SORTIR » sans lettre). Une réussite de ces
    #: décisions mesure le moteur, pas la lecture du modèle.
    decisions_cible_resolue: int = 0

    @property
    def accuracy(self) -> float:
        return self.avoided / self.total if self.total else 0.0

    @property
    def first_accuracy(self) -> float:
        first = sum(
            1
            for agent, blocked in BLOCKED.items()
            if self.first_choices.get(agent) not in (None, blocked)
        )
        decided = sum(
            1 for agent in BLOCKED if self.first_choices.get(agent) is not None
        )
        return first / decided if decided else 0.0

    @property
    def part_decisions_bloquees(self) -> float:
        """Part **des décisions** visant une sortie crue bloquée (D14)."""
        if not self.decisions_total:
            return 0.0
        return self.decisions_to_blocked / self.decisions_total

    def as_dict(self) -> dict[str, object]:
        return {
            "choices": self.choices,
            "first_choices": self.first_choices,
            "avoided": self.avoided,
            "total": self.total,
            "accuracy": round(self.accuracy, 3),
            "first_accuracy": round(self.first_accuracy, 3),
            "decisions_to_blocked": self.decisions_to_blocked,
            "decisions_total": self.decisions_total,
            "decisions_cible_resolue": self.decisions_cible_resolue,
            "part_decisions_bloquees": round(self.part_decisions_bloquees, 3),
        }


def score(sim: Simulation) -> BlockedScore:
    """Note le run **par décision** : dernière cible, première cible, et la
    part de décisions qui visent la sortie que l'agent croit bloquée."""
    last: dict[str, str] = {}
    first: dict[str, str] = {}
    to_blocked = 0
    total = 0
    resolved = 0
    for row in sim.log.rows:
        if not (row.action.startswith("évacuer") and row.target):
            continue
        total += 1
        if row.target_resolved:
            resolved += 1
        last[row.agent] = row.target
        first.setdefault(row.agent, row.target)
        if BLOCKED.get(row.agent) == row.target:
            to_blocked += 1
    choices: dict[str, str | None] = {
        agent: last.get(agent) for agent in sorted(BLOCKED)
    }
    first_choices: dict[str, str | None] = {
        agent: first.get(agent) for agent in sorted(BLOCKED)
    }
    avoided = sum(
        1
        for agent, blocked in BLOCKED.items()
        if choices.get(agent) not in (None, blocked)
    )
    return BlockedScore(
        choices=choices,
        avoided=avoided,
        total=len(BLOCKED),
        first_choices=first_choices,
        decisions_to_blocked=to_blocked,
        decisions_total=total,
        decisions_cible_resolue=resolved,
    )


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
