"""C7 — le décalage entre un événement et sa prise en compte.

Le cahier des charges demande deux choses distinctes, et il est facile de
n'en faire qu'une :

    1. **mesurer** le décalage entre un événement du monde et le moment où
       il apparaît dans les indicateurs ;
    2. **montrer comment il évolue sous charge** — donc le mesurer au moins
       deux fois, à deux tailles de population.

D'où deux mesures, et non une seule :

    `first_decision`
        le premier descendant causal de l'événement (B4 fournit
        `correlation_id`, donc l'arbre entier) : c'est le décalage entre le
        monde et la **cognition**.

    `first_indicator`
        le premier bloc d'indicateurs dont la valeur change après
        l'événement : c'est le décalage entre le monde et la **mesure**.
        Les deux ne sont pas égaux, et c'est normal : un indicateur est
        agrégé, il bouge quand assez d'agents ont bougé.

Ce module ne lit que le journal : il fonctionne sur un run terminé, sans
moteur ni LLM.
"""

from __future__ import annotations

import statistics as st
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from maree.domain.events import Event, EventType

#: Les événements qui « arrivent au monde » et dont on mesure la prise en
#: compte. Une décision n'est pas un événement du monde : elle est déjà une
#: conséquence.
WORLD_EVENTS = (
    EventType.WORLD_SMOKE,
    EventType.ANNOUNCEMENT,
    EventType.EXIT_CLOSED,
)

#: En deçà, la variation d'un indicateur est du bruit d'arrondi (les valeurs
#: sont arrondies à 1e-4 dans le journal).
EPSILON = 1e-3


@dataclass(slots=True)
class Lag:
    """Un événement du monde et le temps qu'il a mis à compter."""

    event_id: str
    type: str
    tick: int
    #: Premier descendant causal (décision, croyance, message) : le monde a
    #: été **perçu**.
    first_effect: int | None
    #: Premier bloc d'indicateurs dont la valeur a changé : le monde a été
    #: **mesuré**.
    first_indicator: int | None
    #: Nombre d'agents distincts touchés par la chaîne causale.
    agents: int
    #: Premier descendant **LLM** : le monde a été compris, pas seulement
    #: subi. C'est cette mesure qui grossit sous charge — les agents à
    #: règles réagissent au tick même, les agents LLM attendent leur tour
    #: dans la file du modèle.
    first_llm: int | None = None

    @property
    def effect_ticks(self) -> int | None:
        return None if self.first_effect is None else self.first_effect - self.tick

    @property
    def llm_ticks(self) -> int | None:
        return None if self.first_llm is None else self.first_llm - self.tick

    @property
    def indicator_ticks(self) -> int | None:
        return (
            None
            if self.first_indicator is None
            else self.first_indicator - self.tick
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "effect_ticks": self.effect_ticks,
            "indicator_ticks": self.indicator_ticks,
            "llm_ticks": self.llm_ticks,
        }


def _indicators(events: Iterable[Event]) -> list[Event]:
    return [e for e in events if e.type is EventType.INDICATORS]


def _first_change(blocks: list[Event], tick: int) -> int | None:
    """Premier tick où I2 ou I3 change après `tick`.

    On regarde I2 (entropie des croyances) et I3 (part évacuée) : ce sont
    les deux indicateurs qu'un signal de danger déplace réellement. I1 est
    écarté — la campagne X8 a montré qu'il ne bouge pas même quand on coupe
    la communication (B3), donc il ne peut pas servir de détecteur.
    """
    before = next((b for b in blocks if b.t_prod == tick), None)
    if before is None:
        return None
    ref = (before.data["I2_entropy"], before.data["I3_evacuated"])
    for block in blocks:
        if block.t_prod <= tick:
            continue
        now = (block.data["I2_entropy"], block.data["I3_evacuated"])
        if any(abs(a - b) > EPSILON for a, b in zip(now, ref, strict=False)):
            return block.t_prod
    return None


def lags(events: list[Event]) -> list[Lag]:
    """Un `Lag` par événement du monde, dans l'ordre du journal."""
    blocks = _indicators(events)
    out: list[Lag] = []
    for event in events:
        if event.type not in WORLD_EVENTS:
            continue
        # `correlation_id` est la racine de l'arbre causal (B4) : tout ce
        # que l'événement a provoqué, directement ou non, la porte.
        descendants = [
            e
            for e in events
            if e.correlation_id == event.id
            and e.type
            in {
                EventType.DECISION,
                EventType.BELIEF_UPDATED,
                EventType.MESSAGE_SENT,
                EventType.EVACUATED,
            }
        ]
        first = min((e.t_trait for e in descendants), default=None)
        first_llm = min(
            (
                e.t_trait
                for e in descendants
                if e.type is EventType.DECISION and e.data.get("kind") == "llm"
            ),
            default=None,
        )
        agents = {
            e.data.get("agent_id")
            for e in descendants
            if isinstance(e.data.get("agent_id"), str)
        }
        out.append(
            Lag(
                event_id=event.id,
                type=str(event.type),
                tick=event.t_prod,
                first_effect=first,
                first_indicator=_first_change(blocks, event.t_prod),
                agents=len(agents),
                first_llm=first_llm,
            )
        )
    return out


def summary(lags_: list[Lag]) -> dict[str, Any]:
    """Agrégat d'un run : médianes, et ce qui n'a jamais été pris en compte."""
    effects = [lag.effect_ticks for lag in lags_ if lag.effect_ticks is not None]
    indicators = [
        lag.indicator_ticks for lag in lags_ if lag.indicator_ticks is not None
    ]
    llm = [lag.llm_ticks for lag in lags_ if lag.llm_ticks is not None]
    return {
        "events": len(lags_),
        "llm_ticks_median": st.median(llm) if llm else None,
        "llm_ticks_max": max(llm) if llm else None,
        "effect_ticks_median": st.median(effects) if effects else None,
        "indicator_ticks_median": st.median(indicators) if indicators else None,
        "effect_ticks_max": max(effects) if effects else None,
        "indicator_ticks_max": max(indicators) if indicators else None,
        # Un événement jamais pris en compte n'est pas une mesure manquante,
        # c'est un résultat : la foule ne l'a pas vu, ou pas assez pour
        # déplacer un agrégat.
        "never_measured": sum(1 for lag in lags_ if lag.indicator_ticks is None),
    }
