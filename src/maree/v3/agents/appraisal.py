"""agents.appraisal — l'appraisal PADM (comportement.md §7).

À chaque événement l'agent évalue cinq dimensions (menace, urgence,
efficacité, preuve sociale, responsabilité) puis choisit une action
protective. L'appraisal est **journalisé** : c'est ce qui permet au front
d'afficher « ce à quoi il pense », et de justifier chaque décision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from maree.v3.agents.knowledge import Knowledge
from maree.v3.agents.perception import Perception
from maree.v3.agents.social import SocialState
from maree.v3.agents.traits import Traits


class Action(Enum):
    """Les actions protectives (vocabulaire du domaine, en français)."""

    RESTER = "rester"
    CHERCHER = "chercher de l'information"
    EVACUER = "évacuer vers une sortie"
    CHERCHER_PROCHE = "chercher un proche"
    AIDER = "aider / guider"
    SUIVRE = "suivre quelqu'un"
    REVIRER = "revenir en arrière"


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True, slots=True)
class Appraisal:
    """Le résultat d'un appraisal : cinq dimensions + la justification."""

    menace: float
    urgence: float
    efficacite: float
    preuve_sociale: float
    responsabilite: float
    #: pourquoi, pour chaque dimension — porté par la décision.
    raisons: dict[str, str] = field(default_factory=dict)

    @property
    def dimensions(self) -> dict[str, float]:
        return {
            "menace": self.menace,
            "urgence": self.urgence,
            "efficacite": self.efficacite,
            "preuve_sociale": self.preuve_sociale,
            "responsabilite": self.responsabilite,
        }


def appraise(
    *,
    perception: Perception,
    traits: Traits,
    knowledge: Knowledge,
    social: SocialState,
    name: str,
) -> Appraisal:
    """Évalue les cinq dimensions à partir de la perception et des traits.

    ``name`` est le nom de l'agent pour les messages de justification.
    """
    raisons: dict[str, str] = {}
    per = perception

    # --- menace : fumée, menace perçue, annonce ---
    menace = per.threat
    if per.smoke_visible:
        menace += 0.5
        raisons["menace"] = f"{name} voit de la fumée"
    elif per.threat > 0.0:
        raisons["menace"] = f"{name} perçoit une menace ({per.threat:.2f})"
    if per.announcement:
        menace += 0.25
        raisons["menace"] = (
            f"{name} entend une annonce : « {per.announcement[:60]} »"
        )
    # la sensibilité au bruit amplifie la menace perçue
    menace *= 0.7 + 0.6 * traits.noise_sensitivity
    menace = _clip(menace)

    # --- urgence : la menace, amplifiée par le stress ---
    urgence = _clip(menace * (0.5 + 0.5 * per.state.stress))
    raisons.setdefault(
        "urgence",
        f"{name} a un niveau de stress {per.state.stress:.2f}",
    )

    # --- efficacité : crois-je savoir quoi faire ? ---
    knows_exit = any(
        k.startswith("exit:") for k in knowledge.known_keys()
    )
    efficacite = _clip(traits.spatial_confidence * (0.5 if not knows_exit else 1.0))
    raisons["efficacite"] = (
        f"{name} connaît une sortie ({efficacite:.2f})" if knows_exit
        else f"{name} ne connaît pas de sortie"
    )

    # --- preuve sociale : que font / disent les autres ---
    social_proof = 0.0
    if per.seen_agents:
        social_proof = 0.5 * traits.herding
        raisons["preuve_sociale"] = (
            f"{name} voit {len(per.seen_agents)} agent(s) bouger"
        )
    else:
        raisons.setdefault("preuve_sociale", "personne d'observé")
    preuve_sociale = _clip(social_proof)

    # --- responsabilité : proches, rôle, groupe ---
    responsabilite = 0.0
    if social.kin:
        responsabilite = traits.kin_attachment
        raisons["responsabilite"] = (
            f"{name} a {len(social.kin)} proche(s) non réunis"
        )
    elif traits.altruism > 0.5:
        responsabilite = _clip(0.2)
        raisons["responsabilite"] = f"{name} est altruiste (responsable)"
    else:
        raisons["responsabilite"] = f"{name} n'a aucun proche à chercher"

    return Appraisal(
        menace=menace,
        urgence=urgence,
        efficacite=efficacite,
        preuve_sociale=preuve_sociale,
        responsabilite=responsabilite,
        raisons=raisons,
    )


__all__ = [
    "Action",
    "Appraisal",
    "appraise",
]