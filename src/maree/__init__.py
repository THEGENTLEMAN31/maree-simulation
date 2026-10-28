"""MARÉE — foule et évacuation interprétative à Port-Aubel.

Architecture hexagonale :

    domain/     règles métier pures (aucune I/O, aucun framework)
    ports/      protocoles : ce dont le domaine a besoin du monde extérieur
    adapters/   implémentations réelles (JuPedSim, llama.cpp, Redpanda…)
    agents/     cognition (LangGraph)
    narrative/  chroniqueur omniscient (lecture seule)
    engine/     orchestration des trois horloges
    metrics/    I1..I6

Règle d'or : `domain/` n'importe ni Mesa, ni JuPedSim, ni Kafka, ni LangGraph.
C'est ce qui rend le projet modulaire et remplaçable pièce par pièce.
"""

__version__ = "2.0.0"
