"""Les cinq profils de Port-Aubel.

Un profil n'est pas un caractère : c'est un **jeu de connaissances
initiales** et un **contrat de décision**. C'est ce qui rend le monde
neutre et l'expérience reproductible (le cadrage exige un monde fictif
et neutre).

La différence entre profils porte sur trois choses seulement :

    ce qu'il sait des sorties   (carte mentale initiale)
    ce qu'il peut lire          (collections RAG autorisées, décision 15)
    ce qu'il priorise           (fuir, chercher un proche, guider)

Tout le reste — le modèle, la température, la cadence — vient du YAML.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from maree.domain.ids import ExitId, ZoneId


@dataclass(frozen=True, slots=True)
class Profile:
    id: str
    label: str
    kind: Literal["llm", "rules"]
    #: Capacité cognitive attendue, attribuée par le **rôle et
    #: l'expérience** du profil, jamais par une catégorie sociale (A5).
    #: Le nom concret du GGUF vient du YAML (`llm.model` / `llm.small_model`) :
    #: un profil décrit un rôle, pas un fichier.
    tier: Literal["big", "small"]
    temperature: float
    cadence_ticks: int
    #: None = connaît toutes les sorties du plan.
    knows_exits: tuple[ExitId, ...] | None
    #: None = perçoit toutes les zones.
    knows_zones: tuple[ZoneId, ...] | None
    rag_collections: tuple[str, ...]
    priorities: tuple[str, ...]
    system_prompt: str

    @property
    def persona(self) -> str:
        """Le rôle seul, **sans** le contrat de sortie JSON.

        Le tier « small » ne répond pas en JSON : lui envoyer un prompt
        système qui dit « réponds UNIQUEMENT par un objet JSON » puis «
        réponds OUI ou NON » le laisse choisir la première consigne venue
        — mesuré : il répondait OUI à t1, sans fumée, et sortait au tick 3.
        """
        return self.system_prompt.removeprefix(_COMMUN).strip()

    def knows(self, exit_id: ExitId) -> bool:
        return self.knows_exits is None or exit_id in self.knows_exits


# ------------------------------------------------------------
# Prompts — français, courts, contraints.
#
# Volontairement factuels : on ne demande pas au modèle d'« être » un
# personnage, on lui demande de choisir une action compatible avec ce
# qu'il sait. Un LLM qui joue un rôle invente ; un LLM qui décide sous
# contrainte reste mesurable.
# ------------------------------------------------------------
_COMMUN = (
    "Tu incarnes un festivalier de la Fête des Lanternes à Port-Aubel, sur "
    "l'esplanade du quai. Tu ne vois que ce qui est décrit. Tu ne sais rien "
    "d'autre. Réponds UNIQUEMENT par un objet JSON : "
    '{"action": "go_exit|go_zone|follow|search|guide|stay", '
    '"target": "A|B|C|<zone>|null", "confidence": 0.0-1.0, "reason": "<=140 caractères"}. '
    "Aucun texte avant ou après le JSON."
)

PROFILES: dict[str, Profile] = {
    "securite": Profile(
        id="securite",
        label="Agent de sécurité",
        kind="llm",
        tier="big",
        temperature=0.2,
        cadence_ticks=2,
        knows_exits=None,
        knows_zones=None,
        rag_collections=("consignes_securite", "plan_signaletique"),
        priorities=("evaluer", "guider", "evacuer"),
        system_prompt=(
            _COMMUN
            + " Tu es agent de sécurité : tu connais les trois sorties et le plan. "
            "Tu cherches à orienter les personnes vers la sortie la plus sûre, "
            "pas forcément la plus proche. Si une annonce officielle te parvient, "
            "tu la suis."
        ),
    ),
    "habitue": Profile(
        id="habitue",
        label="Habitué du quartier",
        kind="llm",
        tier="big",
        temperature=0.2,
        cadence_ticks=3,
        knows_exits=("A", "B", "C"),
        knows_zones=None,
        rag_collections=("plan_signaletique", "souvenirs_editions"),
        priorities=("eviter_la_foule", "evacuer"),
        system_prompt=(
            _COMMUN
            + " Tu viens chaque année. Tu sais qu'une ruelle étroite à l'est "
            "mène à la rue des Cordiers et qu'elle est presque toujours vide. "
            "Tu préfères un détour discret à une bousculade."
        ),
    ),
    "famille": Profile(
        id="famille",
        label="Parent accompagné",
        kind="llm",
        tier="big",
        temperature=0.3,
        cadence_ticks=3,
        knows_exits=("A", "C"),
        knows_zones=None,
        rag_collections=("consignes_securite", "annonces"),
        priorities=("retrouver_proche", "evacuer"),
        system_prompt=(
            _COMMUN
            + " Tu es venu avec un proche. Tant que tu ne l'as pas retrouvé, "
            "tu le cherches, même si cela te fait remonter le flux. Ensuite, "
            "tu sors par la sortie la plus proche que tu connais."
        ),
    ),
    "visiteur": Profile(
        id="visiteur",
        label="Visiteur",
        kind="llm",
        tier="small",
        temperature=0.3,
        cadence_ticks=3,
        knows_exits=("A",),
        knows_zones=None,
        rag_collections=("consignes_securite",),
        priorities=("comprendre", "suivre", "evacuer"),
        system_prompt=(
            _COMMUN
            + " Tu es touriste, arrivé par l'entrée principale au nord. Tu ne "
            "connais que cette entrée. Si tu ne comprends pas la situation, tu "
            "suis la personne qui semble savoir."
        ),
    ),
    "vendeur": Profile(
        id="vendeur",
        label="Tenancier de stand",
        kind="llm",
        tier="small",
        temperature=0.2,
        cadence_ticks=4,
        knows_exits=("A", "C"),
        knows_zones=None,
        rag_collections=("annonces", "souvenirs_editions"),
        priorities=("proteger_stand", "evacuer"),
        system_prompt=(
            _COMMUN
            + " Tu tiens un stand près de la scène. Tu sais que le festival "
            "utilise une machine à brume en soirée. Tu ne quittes pas ton "
            "matériel sans raison solide, mais tu ne restes pas si le danger "
            "est confirmé."
        ),
    ),
}

#: Le bras de comparaison X4 : mêmes profils, décision par règles.
RULES_PROFILE = Profile(
    id="regles",
    label="Agent à règles (référence)",
    kind="rules",
    tier="small",
    temperature=0.0,
    cadence_ticks=3,
    knows_exits=None,
    knows_zones=None,
    rag_collections=(),
    priorities=("evacuer",),
    system_prompt="",
)


def get_profile(profile_id: str) -> Profile:
    if profile_id == RULES_PROFILE.id:
        return RULES_PROFILE
    try:
        return PROFILES[profile_id]
    except KeyError as exc:
        raise KeyError(f"profil inconnu : {profile_id!r}") from exc
