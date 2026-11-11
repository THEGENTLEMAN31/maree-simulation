"""knowledge.corpus — la base de connaissances du monde MARÉE (fictive).

Chaque passage porte la **date de disponibilité simulée** et la **liste des
profils autorisés** à le retrouver (décision 15 des docs) : un agent ne
retrouve jamais ce qu'il n'aurait pas pu savoir à cet instant (C6) ni ce
que son profil n'est pas censé lire. C'est ce qui rend le RAG **sourcé**
(collection, titre, importance) et évaluable (F2).
"""

from __future__ import annotations

from dataclasses import dataclass

ALL = ("tous",)


@dataclass(frozen=True, slots=True)
class Passage:
    id: str
    collection: str
    title: str
    content: str
    available_tick: int = 0            # date de disponibilité simulée
    allowed_profiles: tuple[str, ...] = ALL
    importance: float = 0.5            # 0..1

    def as_langchain_document(self):
        from langchain_core.documents import Document

        return Document(
            page_content=self.content,
            metadata={
                "id": self.id,
                "collection": self.collection,
                "title": self.title,
                "available_tick": self.available_tick,
                "allowed_profiles": list(self.allowed_profiles),
                "importance": self.importance,
            },
        )


#: corpus du monde MARÉE — quelques passages par collection (plan, consignes,
#: annonces, souvenirs, profils).
CORPUS: tuple[Passage, ...] = (
    Passage("plan_A", "plan", "Sortie A (nord)",
            "La sortie A est large, au nord de l'esplanade ; c'est l'entrée "
            "habituelle de la majorité du public.", 0),
    Passage("plan_B", "plan", "Sortie B (est)",
            "La sortie B est étroite, au bout de la passerelle est ; elle se "
            "bouche dès que la foule est dense.", 0),
    Passage("plan_C", "plan", "Sortie C (sud, discrète)",
            "La sortie C, au sud, est discrète et surtout connue des habitués ; "
            "elle évite la passerelle encombrée.", 0, ("habitue", "agent_de_securite")),
    Passage("consigne_evac", "securite", "Consigne d'évacuation",
            "En cas d'alerte, le personnel guide le public vers la sortie "
            "la plus proche et dégage la passerelle.", 0, ("agent_de_securite",)),
    Passage("consigne_annonce", "securite", "Rôle des annonces",
            "Une annonce ne se fait qu'avec l'accord du poste de sécurité et "
            "nomme une seule sortie : jamais deux à la fois.", 0, ("agent_de_securite",)),
    Passage("souvenir_2019", "souvenirs", "Édition 2019 : fumée",
            "En 2019, une odeur de fumée au sud a vidé l'esplanade ; ceux qui "
            "ont pris la sortie C sont sortis sans attendre.", 50, ("habitue",)),
    Passage("souvenir_rumeur_A", "souvenirs", "Rumeur : sortie A fermée",
            "L'an dernier, certains affirment que la sortie A avait été fermée "
            "au dernier moment — aucun organiser ne le confirme.", 30, ALL, 0.8),
    Passage("annonce_claire", "annonces", "Annonce claire",
            "« Veuillez évacuer immédiatement par la sortie A. »", 60),
    Passage("annonce_ambigue", "annonces", "Annonce ambiguë",
            "« Veuillez rester calmes, tout va bien. »", 60),
    Passage("annonce_fausse", "annonces", "Annonce erronée",
            "« La sortie B est bloquée, ne partez pas par là. »", 60, ALL, 0.7),
)


def passages() -> tuple[Passage, ...]:
    return CORPUS


def documents() -> list[object]:
    return [p.as_langchain_document() for p in CORPUS]


__all__ = ["CORPUS", "Passage", "documents", "passages"]