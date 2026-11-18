"""G1 — le calendrier et l'escalade tiennent (sans GPU).

Ce que l'on prouve ici, avant toute campagne :

- ``regles`` ne paie **aucun** appel : son calendrier s'arrête aux fronts ;
- ``hybride`` escalade sur un **fait du monde** (information contradictoire),
  quatre fois à t2, et pas en boucle ;
- ``llm`` ne rappelle pas le modèle tant que la perception pertinente ne
  change pas (le coût suit le monde, pas l'horloge) ;
- une escalade est journalisée (`agent.escalation`) avec sa cause et ses
  valeurs, avant la décision qu'elle a provoquée ;
- ε est un tirage **déterministe** par SHA-256, jamais par ``hash()`` ;
- une trame 1.0 reste lisible sous le contrat 1.1.

Rien ici n'exige un serveur : les fournisseurs sont des espions qui comptent
les appels et répondent une cible fixe. C'est justement le point — le
calendrier se prouve sans modèle.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from maree.v3.agents.agent import make_agent
from maree.v3.agents.perception import Perception
from maree.v3.agents.schedule import epsilon_hit, should_decide
from maree.v3.agents.state import State
from maree.v3.core.ids import ZoneId
from maree.v3.core.ports import LLMResponse, PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.verify import scenario_blocked as sb


class Spy:
    """Un fournisseur qui compte les appels et répond toujours la même chose."""

    def __init__(self, target: str = "B") -> None:
        self.calls = 0
        self.target = target

    def complete(self, request):  # type: ignore[no-untyped-def]
        self.calls += 1
        return LLMResponse(
            text=json.dumps(
                {"action": "evacuer", "cible": self.target, "confiance": 0.9},
                ensure_ascii=False,
            ),
            provider="spy",
            model="spy",
            prompt_tokens=10,
            completion_tokens=5,
            ok=True,
        )


def _spy(target: str = "B") -> Spy:
    """Câble tous les alias sur le même espion (visiteur → ``petit``)."""
    from maree.v3.agents.catalog import register_provider

    spy = Spy(target)
    for name in ("stub", "llamacpp", "llamacpp-small"):
        register_provider(name, spy)
    return spy


def _perception(tick: int = 0) -> Perception:
    return Perception(
        tick=tick,
        zone=ZoneId("z1"),
        state=State(),
    )


# ---------------------------------------------------------------------------
# règles : zéro appel
# ---------------------------------------------------------------------------
def test_les_regles_ne_paient_aucun_appel() -> None:
    spy = _spy()
    bus = MemoryBus()
    sim = sb.build(seed=1, policy=PolicyName.RULES, bus=bus, run_id="g1_rules")
    sim.run(sb.timeline())
    assert spy.calls == 0
    # et elles ont bien décidé : le silence n'est pas une absence de décision
    assert sim.log.rows
    assert sb.score(sim).accuracy == 1.0


# ---------------------------------------------------------------------------
# hybride : escalade sur contradiction, bornée
# ---------------------------------------------------------------------------
def test_l_hybride_escalade_quatre_fois_a_t2() -> None:
    spy = _spy()
    bus = MemoryBus()
    sim = sb.build(seed=1, policy=PolicyName.HYBRID, bus=bus, run_id="g1_hybrid")
    sim.run(sb.timeline())

    escalations = bus.published("agent.escalation")
    assert spy.calls == 4
    assert len(escalations) == 4
    assert {e.t_prod for e in escalations} == {sb.T_MESSAGE}
    assert {e.data["cause"] for e in escalations} == {"information_contradictoire"}

    # chaque escalade nomme la sortie que l'agent croyait praticable
    named = {
        (e.data["agent"], e.data["detail"]["sortie"]) for e in escalations
    }
    assert named == {
        ("A01", "A"),
        ("A02", "A"),
        ("A03", "B"),
        ("A04", "B"),
    }


def test_l_hybride_ne_repete_pas_la_meme_contradiction() -> None:
    """La même rumeur ne doit pas rappeler le modèle à chaque tick."""
    spy = _spy()
    sim = sb.build(seed=1, policy=PolicyName.HYBRID, bus=MemoryBus(), run_id="g1_b")
    sim.run(sb.timeline())
    # 4 agents × (message t2) — puis plus rien : ni la fumée déjà vue,
    # ni la cible bloquée déjà signalée ne rappellent le modèle.
    assert spy.calls == 4
    called_ticks = Counter(
        row.tick for row in sim.log.rows if row.llm_model is not None
    )
    assert set(called_ticks) == {sb.T_MESSAGE}


def test_l_escalade_precede_la_decision_qu_elle_provoque() -> None:
    _spy()
    bus = MemoryBus()
    sim = sb.build(seed=1, policy=PolicyName.HYBRID, bus=bus, run_id="g1_order")
    sim.run(sb.timeline())
    types = [e.type for e in bus.envelopes]
    first_escalation = types.index("agent.escalation")
    first_decision = types.index("agent.decision")
    assert first_escalation < first_decision


# ---------------------------------------------------------------------------
# llm : le coût suit le changement perçu, pas l'horloge
# ---------------------------------------------------------------------------
def test_le_llm_ne_rappelle_pas_sans_changement() -> None:
    spy = _spy()
    sim = sb.build(seed=1, policy=PolicyName.LLM, bus=MemoryBus(), run_id="g1_llm")
    sim.run(sb.timeline())
    # t2 : le message ; t3 : la cible crue bloquée (plan invalidé) ;
    # t10 : la fumée. Les ticks 20/30/40 n'ajoutent rien.
    called_ticks = {row.tick for row in sim.log.rows if row.llm_model is not None}
    assert called_ticks == {sb.T_MESSAGE, sb.T_MESSAGE + 1, sb.T_SMOKE}
    # borné : 4 agents × 3 moments, pas 4 agents × 40 ticks
    assert spy.calls == 10


def test_au_spawn_sans_front_on_ne_decide_pas() -> None:
    agent = make_agent(1, "visiteur", known_exits=frozenset({"A", "B"}))
    gate = should_decide(agent, _perception(tick=0))
    assert gate.decide is False
    assert agent._last_decision is None


# ---------------------------------------------------------------------------
# ε : instrument déterministe
# ---------------------------------------------------------------------------
def test_epsilon_est_deterministe_et_reproductible() -> None:
    first = [epsilon_hit("run", tick, 3, 0.25) for tick in range(20)]
    second = [epsilon_hit("run", tick, 3, 0.25) for tick in range(20)]
    assert first == second
    # et ce n'est pas `hash()` : on recalcule le tirage à la main
    digest = hashlib.sha256(b"run:5:3").digest()
    draw = int.from_bytes(digest[:8], "big") / 2**64
    assert epsilon_hit("run", 5, 3, 0.25) == (draw < 0.25)


def test_epsilon_aux_bornes_est_declare() -> None:
    assert not any(epsilon_hit("run", tick, 1, 0.0) for tick in range(10))
    assert all(epsilon_hit("run", tick, 1, 1.0) for tick in range(10))
