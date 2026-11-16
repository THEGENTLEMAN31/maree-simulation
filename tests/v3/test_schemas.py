"""F4 (schémas versionnés) et A4 (incidents tracés et dénombrés).

- chaque enveloppe publiée porte ``schema: maree.event/<version>`` et satisfait
  le schéma de son type (aucune trame n'est publiée hors contrat) ;
- un champ manquant ou un type inconnu est **signalé** par ``validate`` (mais
  rien n'est filtré : le journal reste complet) ;
- un repli de politique n'est pas un silence : ``agent.incident`` est émis et
  ``indicator.incidents`` dénombre les causes pendant le run.
"""

from __future__ import annotations

from maree.v3.adapters.chat_stub import StubChat
from maree.v3.agents.catalog import register_provider
from maree.v3.core.ports import PolicyName
from maree.v3.sim.bus import MemoryBus
from maree.v3.sim.orchestrator import Simulation, Timestep
from maree.v3.sim.schemas import EVENT_SCHEMA_ID, SCHEMA_VERSION, validate
from maree.v3.world.sample import sample_worldspec


def _run_rules() -> MemoryBus:
    bus = MemoryBus()
    sim = Simulation(seed=4, policy=PolicyName.RULES, bus=bus).build(sample_worldspec())
    sim.spawn("visiteur", 2, frozenset({"A", "B"}))
    sim.run([Timestep(1), Timestep(10, smoke=True)])
    return bus


# ---- F4 : le contrat versionné des trames ----

def test_chaque_enveloppe_porte_un_schema_versionne() -> None:
    bus = _run_rules()
    assert bus.envelopes, "le run doit publier des trames"
    for env in bus.envelopes:
        assert env.to_dict()["schema"] == EVENT_SCHEMA_ID


def test_toutes_les_trames_du_run_satisfont_leur_schema() -> None:
    bus = _run_rules()
    for env in bus.envelopes:
        assert validate(env.type, env.data) == [], (env.type, validate(env.type, env.data))


def test_un_champ_manquant_est_signale() -> None:
    errors = validate("world.smoke", {})                 # « visible » manque
    assert "champ manquant : visible" in errors


def test_un_type_inconnu_est_signale_sans_etre_filtre() -> None:
    errors = validate("experience.custom", {"x": 1})
    assert errors and "non schématisé" in errors[0]
    # et le type reste publiable : validate est un diagnostic, pas un filtre
    assert SCHEMA_VERSION == "1.0"


# ---- A4 : incidents tracés et dénombrés ----

def test_a4_les_replis_sont_traces_et_denombres_pendant_le_run() -> None:
    # un fournisseur qui répond du texte non parsable → repli « unparseable »
    register_provider("llamacpp", StubChat(lambda _r: "je ne sais pas"))
    bus = MemoryBus()
    sim = Simulation(seed=2, policy=PolicyName.LLM, bus=bus).build(sample_worldspec())
    sim.spawn("visiteur", 2, frozenset({"A", "B"}), llm_alias="decision")
    sim.run([Timestep(1), Timestep(5, smoke=True)])

    assert sim.incidents["unparseable"] == 2        # compteur du moteur
    traces = bus.published("agent.incident")
    assert len(traces) == 2                         # A4 : tracé
    assert {e.data["cause"] for e in traces} == {"unparseable"}
    last = bus.published("indicator.incidents")[-1]
    assert last.data["total"] == 2                  # A4 : dénombré
    assert last.data["par_cause"] == {"unparseable": 2}


def test_a4_aucun_incident_ne_vaut_pas_silence() -> None:
    bus = _run_rules()
    last = bus.published("indicator.incidents")[-1]
    assert last.data["total"] == 0
    assert last.data["par_cause"] == {}
    assert bus.published("agent.incident") == []
