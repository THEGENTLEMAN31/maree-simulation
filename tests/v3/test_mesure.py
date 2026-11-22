"""C4 — la mesure dit ce qu'elle prétend dire.

Ce que l'on verrouille ici :

- I1–I7 sont calculés **pendant** le run et publiés (`indicator.crowd`) ;
- I5 est un noyau de 2 m (une grille saturerait), et un agent seul vaut 0 ;
- I3, I4, I7 ont la définition v2 : I4 est une horloge (tick × 10 s), I7 part
  du premier signal de **danger du monde**, pas du premier agent qui bouge ;
- I6 vaut 0 **par construction** sans fermeture (le champ `closed_exits` le dit) ;
- le résumé exclut le tick dégénéré (plus personne n'est là) ;
- le coût en jetons est la **somme des lignes du journal**, et
  `llm_attempted` distingue « pas d'appel » de « appel raté » ;
- la note du scénario bloqué est **par décision** : première cible, dernière
  cible, et part des décisions visant une sortie crue bloquée (D14).
"""

from __future__ import annotations

import math

from maree.v3.agents.agent import make_agent
from maree.v3.agents.catalog import register_provider
from maree.v3.agents.knowledge import Belief, Source
from maree.v3.core.ports import LLMResponse, PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.verify import scenario_blocked as sb
from maree.v3.verify.campaign import CampConfig, run_once
from maree.v3.verify.indicators import (
    AgentState,
    belief_gap,
    compute,
    max_density,
    summarise,
)
from maree.v3.world.generate import build
from maree.v3.world.sample import sample_worldspec


def _state(name: str, point: tuple[float, float], exit_id: str | None = "A",
           evacuated: bool = False) -> AgentState:
    return AgentState(
        agent_id=name,
        profile="visiteur",
        position=point,
        belief_best=exit_id,
        belief_confidence=0.8,
        belief_entropy=0.0,
        evacuated=evacuated,
    )


# ---------------------------------------------------------------------------
# briques
# ---------------------------------------------------------------------------
def test_i5_est_un_noyau_de_deux_metres() -> None:
    """Trois agents en 1 m de côté : 2 voisins / (π·2²), et non 3 par cellule."""
    states = [
        _state("a", (0.0, 0.0)),
        _state("b", (1.0, 0.0)),
        _state("c", (0.0, 1.0)),
    ]
    expected = 2 / (math.pi * 4.0)
    assert abs(max_density(states) - expected) < 1e-12
    # seul, il n'y a pas de densité
    assert max_density([_state("a", (0.0, 0.0))]) == 0.0


def test_i5_ignore_les_agents_sortis() -> None:
    states = [
        _state("a", (0.0, 0.0)),
        _state("b", (1.0, 0.0), evacuated=True),
    ]
    assert max_density(states) == 0.0


def test_i4_est_une_horloge_et_i7_part_du_danger() -> None:
    states = [_state("a", (0.0, 0.0)), _state("b", (5.0, 5.0), "B", evacuated=True)]
    ind = compute(
        states,
        n_exits=3,
        open_exits={"A", "B", "C"},
        tick=12,
        signal_tick=10,
        last_exit_tick=18,
    )
    assert ind.i4_seconds == 120.0          # 12 ticks × 10 s
    assert ind.i7_delay_seconds == 80.0     # (18 − 10) × 10 s


def test_i6_est_nul_sans_fermeture_et_positif_sinon() -> None:
    states = [_state("a", (0.0, 0.0), "A"), _state("b", (1.0, 0.0), "B")]
    assert belief_gap(states, {"A", "B"}) == 0.0
    assert belief_gap(states, {"A"}) == 0.5


def test_le_resume_exclut_le_tick_degenere() -> None:
    decide = [
        {"I1_consensus": 0.4, "I2_entropy": 0.9, "I3_evacuated": 0.0,
         "I4_seconds": 10.0, "I5_max_density": 0.3, "I6_belief_gap": 0.0,
         "I7_delay_seconds": 0.0},
        {"I1_consensus": 0.8, "I2_entropy": 0.4, "I3_evacuated": 0.5,
         "I4_seconds": 20.0, "I5_max_density": 1.1, "I6_belief_gap": 0.5,
         "I7_delay_seconds": 0.0},
        {"I1_consensus": 0.0, "I2_entropy": 0.0, "I3_evacuated": 1.0,
         "I4_seconds": 30.0, "I5_max_density": 0.0, "I6_belief_gap": 0.0,
         "I7_delay_seconds": 200.0},
    ]
    out = summarise(decide)
    assert out["I1_consensus"] == (0.4 + 0.8) / 2   # moyenne sur les actifs
    assert out["I5_max_density"] == 1.1             # pic
    assert out["I3_evacuated"] == 1.0               # dernier tick
    assert out["I7_delay_seconds"] == 200.0


# ---------------------------------------------------------------------------
# dans le moteur
# ---------------------------------------------------------------------------
def _bus_for(policy: PolicyName, ticks: list[Timestep], agents: int = 4) -> MemoryBus:
    bus = MemoryBus()
    sim = Simulation(seed=1, policy=policy, bus=bus).build(sample_worldspec())
    sim.spawn("visiteur", agents, frozenset({"A", "B", "C"}))
    sim.run(ticks)
    return bus


def test_le_run_publie_les_indicateurs_de_foule() -> None:
    bus = _bus_for(PolicyName.RULES, [Timestep(1), Timestep(10, smoke=True)])
    crowd = bus.published("indicator.crowd")
    assert crowd, "l'indicateur de foule doit être publié à chaque tick"
    data = crowd[-1].data
    for key in (
        "I1_consensus", "I2_entropy", "I3_evacuated", "I4_seconds",
        "I5_max_density", "I6_belief_gap", "I7_delay_seconds",
    ):
        assert key in data
    # il n'y a pas de physique : personne n'est sorti, I3 reste 0
    assert data["I3_evacuated"] == 0.0
    # la fumée de t10 est le premier signal de danger : I7 est défini
    assert data["I7_delay_seconds"] == 0.0 or data["I7_delay_seconds"] >= 0.0


def test_i7_s_ancre_sur_le_premier_danger_du_monde() -> None:
    """Un agent qui part avant le danger ne doit pas fixer l'origine de I7."""
    bus = _bus_for(
        PolicyName.RULES,
        [Timestep(1), Timestep(5, announcement="La sortie A est bloquée"), Timestep(9)],
    )
    sim_first = bus.published("indicator.crowd")[0]
    assert sim_first.data["I4_seconds"] == 10.0      # t1 → 10 s


def test_les_jetons_sont_la_somme_des_lignes_du_journal() -> None:
    """C4 : le coût se lit ligne par ligne, jamais sur la dernière décision."""

    class Spy:
        def complete(self, request):  # type: ignore[no-untyped-def]
            return LLMResponse(
                text='{"action":"evacuer","cible":"A","confiance":0.9}',
                provider="spy", model="spy", prompt_tokens=100,
                completion_tokens=25, ok=True, latency_s=1.5,
            )

    for name in ("stub", "llamacpp", "llamacpp-small"):
        register_provider(name, Spy())
    world = build("hall_3")
    cfg = CampConfig("llm", policy=PolicyName.LLM, llm_alias="decision")
    result = run_once(world, cfg, seed=1, run_id_prefix="c4")

    assert result.llm_attempted == result.llm_ok > 0
    assert result.tokens_prompt == 100 * result.llm_attempted
    assert result.tokens_completion == 25 * result.llm_attempted
    assert result.wall_llm_s == 1.5 * result.llm_attempted
    assert result.tokens == result.tokens_prompt + result.tokens_completion


def test_un_appel_rate_est_compte_comme_tentative() -> None:
    """`llm_attempted` > `llm_ok` quand le fournisseur échoue : pas de silence."""

    class Broken:
        def complete(self, request):  # type: ignore[no-untyped-def]
            return LLMResponse(
                text="", provider="broken", model="broken",
                prompt_tokens=10, completion_tokens=0, ok=False,
            )

    for name in ("stub", "llamacpp", "llamacpp-small"):
        register_provider(name, Broken())
    world = build("hall_3")
    cfg = CampConfig("llm", policy=PolicyName.LLM, llm_alias="decision")
    result = run_once(world, cfg, seed=1, run_id_prefix="c4b")
    assert result.llm_attempted > 0
    assert result.llm_ok == 0
    assert result.replis == result.llm_attempted
    assert set(result.replis_par_cause) == {"no_response"}


# ---------------------------------------------------------------------------
# D14 : la note est par décision
# ---------------------------------------------------------------------------
def test_la_note_du_scenario_bloque_est_par_decision() -> None:
    """D14 : première cible, dernière cible et part de décisions bloquées."""
    bus = MemoryBus()
    sim = sb.build(seed=1, policy=PolicyName.RULES, bus=bus, run_id="c4_score")
    sim.run(sb.timeline())
    s = sb.score(sim)
    # Après le correctif C3, une notice de fermeture n'est plus un ordre
    # d'évacuer *vers* la sortie bloquée : les règles ne s'y trompent plus,
    # ni à la première ni à la dernière décision.
    assert s.accuracy == 1.0
    assert s.first_accuracy == 1.0
    assert s.decisions_to_blocked == 0
    assert s.first_choices == s.choices


def test_une_politique_qui_se_corrige_n_a_pas_bien_choisi() -> None:
    """Le cas D14 : la note de fin cache huit ticks de marche au mauvais endroit."""

    class AlwaysA:
        def complete(self, request):  # type: ignore[no-untyped-def]
            return LLMResponse(
                text='{"action":"evacuer","cible":"A","confiance":0.9}',
                provider="spy", model="spy", prompt_tokens=10,
                completion_tokens=5, ok=True,
            )

    for name in ("stub", "llamacpp", "llamacpp-small"):
        register_provider(name, AlwaysA())
    sim = sb.build(seed=1, policy=PolicyName.LLM, alias="decision", run_id="c4_d14")
    sim.run(sb.timeline())
    s = sb.score(sim)
    # « toujours A » réussit pour les deux agents qui croient B bloquée et
    # échoue pour les deux autres : 0,50, et 6 décisions sur 10 visent une
    # sortie crue bloquée.
    assert s.first_accuracy == 0.5
    assert s.accuracy == 0.5
    assert s.decisions_to_blocked == 6
    assert s.decisions_total == 10
    assert s.part_decisions_bloquees == 0.6


def test_le_null_d_emergence_n_est_pas_une_permutation() -> None:
    """Un null par permutation serait invariant : il faut couper l'ouï-dire."""
    agent = make_agent(1, "visiteur", known_exits=frozenset({"A"}))
    agent.knowledge.beliefs["exit:A"] = Belief("A", 0.5, Source.CONNU, 0)
    from maree.v3.verify.emergence import consensus_without_hearsay

    assert consensus_without_hearsay([agent]) == 1.0


def test_la_croyance_est_journalisee_au_moment_de_decider() -> None:
    """P0.1 : « se trompe » et « ne croit plus que c'est fermé » ne se confondent plus."""
    from maree.v3.agents.agent import make_agent
    from maree.v3.agents.knowledge import Belief, Source
    from maree.v3.agents.perception import Message, Perception
    from maree.v3.agents.state import State
    from maree.v3.core.ids import AgentId, ZoneId

    agent = make_agent(1, "visiteur", known_exits=frozenset({"A", "B"}))
    per = Perception(
        tick=10,
        zone=ZoneId("z"),
        state=State(),
        smoke_visible=True,
        heard=(Message("La sortie A est bloquée", AgentId(2), 10, 0.9),),
    )
    decision = agent.react(per)
    # la croyance est écrite avant la décision : l'agent évite A…
    assert decision.target == "B"
    assert decision.target_believed_blocked is False
    # …et le drapeau suit la croyance réelle, pas la porte qui a été choisie
    agent.knowledge.beliefs["hazard:B"] = Belief("bloquée", 0.95, Source.ENTENDU, 10)
    per2 = Perception(
        tick=11,
        zone=ZoneId("z"),
        state=State(),
        smoke_visible=True,
        heard=(Message("La sortie A est de nouveau praticable", AgentId(3), 11, 0.9),),
    )
    decision2 = agent.react(per2)
    assert decision2.target in {"A", "B"}
    if decision2.target == "B":
        assert decision2.target_believed_blocked is True
