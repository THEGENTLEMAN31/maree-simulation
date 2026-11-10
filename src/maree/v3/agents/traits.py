"""agents.traits — les traits stables qui définissent un archétype.

Un archétype est un **jeu de traits**, pas un caractère littéraire
(docs/v3/comportement.md §3). Deux agents du même archétype partagent ces
valeurs par défaut ; ils diffèrent par leur **histoire, leur mémoire et
leurs liens sociaux**.

Les valeurs par défaut sont des points de départ à calibrer (validation
sur la littérature, pas sur l'intuition — voir comportement.md §13).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Échelle commune, 0..1 pour les traits numériques.
CLAMPED_RANGE = (0.0, 1.0)


@dataclass(frozen=True, slots=True)
class Traits:
    """Jeu de traits stables d'un archétype (échelle 0..1 sauf mention)."""

    risk_aversion: float = 0.5   # seuil de menace avant de bouger
    herding: float = 0.5         # poids de l'observation des autres
    altruism: float = 0.5        # probabilité d'aider, de guider
    spatial_confidence: float = 0.5
    mobility: float = 0.5        # vitesse, handicaps
    authority_trust: float = 0.5 # poids d'une annonce officielle
    kin_attachment: float = 0.5  # priorité à la recherche d'un proche
    impulsivity: float = 0.5     # passage à l'acte sans vérification
    noise_sensitivity: float = 0.5

    def __post_init__(self) -> None:
        # verrouille le domaine : un trait hors 0..1 est une erreur, pas
        # un réglage débattu.
        for name in self._half_open_range_names():
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"trait {name}={value} hors de 0..1")

    @classmethod
    def _half_open_range_names(cls) -> tuple[str, ...]:
        return tuple(f.name for f in cls.__dataclass_fields__.values())


#: Archétypes de référence de la v3 (à calibrer, pas gravés dans le marbre).
#: Les valeurs illustrent des postures distinctes que les jumeaux doivent
#: pouvoir partager.
ARCHETYPES: dict[str, Traits] = {
    # connaît les lieux, confiant, peu sensible à la foule
    "habitue": Traits(
        spatial_confidence=0.9,
        risk_aversion=0.6,
        herding=0.2,
        authority_trust=0.5,
        kin_attachment=0.3,
        mobility=0.6,
    ),
    # ne connaît pas les sorties, suit la foule et les annonces
    "visiteur": Traits(
        spatial_confidence=0.2,
        risk_aversion=0.4,
        herding=0.8,
        authority_trust=0.7,
        kin_attachment=0.3,
        mobility=0.5,
    ),
    # cherche ses proches avant tout
    "famille": Traits(
        spatial_confidence=0.5,
        risk_aversion=0.6,
        herding=0.4,
        authority_trust=0.5,
        kin_attachment=0.9,
        mobility=0.4,
    ),
    # personnel : rassure, guide, connaît le plan
    "agent_de_securite": Traits(
        spatial_confidence=1.0,
        risk_aversion=0.3,
        herding=0.0,
        altruism=0.95,
        authority_trust=0.9,
        kin_attachment=0.1,
        mobility=0.7,
        impulsivity=0.2,
    ),
}


def archetype(name: str) -> Traits:
    """Retourne les traits d'un archétype, ou une erreur si inconnu."""
    try:
        return ARCHETYPES[name]
    except KeyError:
        raise KeyError(
            f"archétype inconnu : {name!r} (disponibles : {sorted(ARCHETYPES)})"
        ) from None


def with_trait(traits: Traits, **overrides: float) -> Traits:
    """Dérive un archétype en surchargeant certains traits (les jumeaux)."""
    unknown = set(overrides) - set(traits.__dataclass_fields__)
    if unknown:
        raise ValueError(f"traits inconnus : {sorted(unknown)}")
    return replace(traits, **overrides)


__all__ = ["ARCHETYPES", "Traits", "archetype", "with_trait"]