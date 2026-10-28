"""RAG : le seul traitement qui compte est le centrage.

On teste avec un encodeur factice mais **déterministe** (sac de mots
haché), pas avec bge-m3 : le but est de vérifier la mécanique — filtres,
centrage, sauvegarde — pas la qualité sémantique du modèle.
"""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

from maree.adapters.retrieval.faiss_corpus import (
    FaissRetriever,
    _normalise,
    load_corpus,
)

DIM = 32


class FakeEmbedder:
    """Sac de mots haché. Déterministe entre processus (crc32, pas hash())."""

    def __init__(self) -> None:
        self.calls = 0

    @staticmethod
    def _vector(text: str) -> list[float]:
        vector = [0.0] * DIM
        for word in text.lower().split():
            cleaned = "".join(c for c in word if c.isalnum())
            if len(cleaned) > 2:
                vector[zlib.crc32(cleaned.encode()) % DIM] += 1.0
        return vector

    async def embed(self, texts):
        self.calls += len(texts)
        return [self._vector(t) for t in texts]


PASSAGES = {
    "consignes/securite-fumee.md": """---
title: Procédure fumée
collection: consignes_securite
available_tick: 0
allowed_profiles: [securite]
importance: 0.9
---
En cas de fumée près de la scène, l'agent de sécurité guide le public vers
la sortie nord sans traverser la scène et compte les personnes évacuées.
""",
    "consignes/foule.md": """---
title: Gestion de foule
collection: consignes_securite
available_tick: 0
allowed_profiles: [securite, habitue]
importance: 0.7
---
Une foule dense se comprime aux passages étroits. Il faut ouvrir les
sorties larges et éviter les contre-courants.
""",
    "plan/sortie-b.md": """---
title: Ruelle des Cordiers
collection: plan_signaletique
available_tick: 0
allowed_profiles: [habitue]
importance: 0.8
---
La ruelle des Cordiers mène à la rue du même nom. Elle est étroite mais
presque toujours vide pendant le festival.
""",
    "plan/sortie-a.md": """---
title: Grand Quai
collection: plan_signaletique
available_tick: 0
allowed_profiles: [securite, habitue, visiteur]
importance: 0.6
---
Le Grand Quai est la sortie principale au nord de l'esplanade, large de
six mètres.
""",
    "souvenirs/2016.md": """---
title: Édition 2016
collection: souvenirs_editions
available_tick: 10
allowed_profiles: [habitue]
importance: 0.5
---
En 2016, la foule avait reflué vers le passage des Halles sans incident.
""",
    "souvenirs/2021.md": """---
title: Édition 2021
collection: souvenirs_editions
available_tick: 10
allowed_profiles: [habitue]
importance: 0.5
---
En 2021, la ruelle était fermée et tout le monde est passé par le quai.
""",
}


@pytest.fixture()
def corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    for name, content in PASSAGES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


@pytest.fixture()
async def retriever(corpus: Path) -> FaissRetriever:
    return await FaissRetriever.build(corpus, FakeEmbedder())


def test_chargement_du_front_matter(corpus: Path) -> None:
    passages = load_corpus(corpus)
    assert len(passages) == len(PASSAGES)
    securite = next(p for p in passages if "securite-fumee" in p.doc_id)
    assert securite.collection == "consignes_securite"
    assert securite.allowed_profiles == ("securite",)
    assert securite.available_tick == 0
    assert "fumée" in securite.text


async def test_recherche_retrouve_le_bon_passage(retriever: FaissRetriever) -> None:
    results = await retriever.retrieve(
        "fumée scène sécurité", profile="securite", tick=0, k=2
    )
    assert results
    assert "securite-fumee" in results[0].doc_id


async def test_filtre_de_profil(retriever: FaissRetriever) -> None:
    """Un visiteur ne doit jamais recevoir une consigne réservée."""
    results = await retriever.retrieve("fumée scène", profile="visiteur", tick=0, k=5)
    assert all("securite-fumee" not in r.doc_id for r in results)
    assert all("sortie-b" not in r.doc_id for r in results)


async def test_filtre_de_disponibilite(retriever: FaissRetriever) -> None:
    early = await retriever.retrieve("édition foule", profile="habitue", tick=5, k=5)
    late = await retriever.retrieve("édition foule", profile="habitue", tick=12, k=5)
    assert all(not r.doc_id.startswith("souvenirs") for r in early)
    assert any(r.doc_id.startswith("souvenirs") for r in late)


async def test_aller_retour_disque(retriever: FaissRetriever, tmp_path: Path) -> None:
    retriever.save(tmp_path / "index")
    reloaded = FaissRetriever.load(tmp_path / "index", FakeEmbedder())
    before = await retriever.retrieve("ruelle étroite", profile="habitue", tick=0, k=1)
    after = await reloaded.retrieve("ruelle étroite", profile="habitue", tick=0, k=1)
    assert [r.doc_id for r in before] == [r.doc_id for r in after]
    assert before[0].score == pytest.approx(after[0].score, abs=1e-5)


async def test_centrage_et_normalisation(corpus: Path) -> None:
    """La moyenne est celle du corpus brut ; les vecteurs stockés sont unitaires.

    C'est le contrat qui compte : `_mean` doit pouvoir être soustraite à la
    requête (c'est elle qui corrige l'anisotropie), et l'index IP n'est
    valide que si les lignes sont de norme 1.
    """
    import numpy as np

    embedder = FakeEmbedder()
    retriever = await FaissRetriever.build(corpus, embedder)
    raw = np.asarray([embedder._vector(p.text) for p in retriever._passages], dtype=np.float32)
    assert np.allclose(retriever._mean, raw.mean(axis=0), atol=1e-6)
    norms = np.linalg.norm(retriever._matrix, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)
    # Centrage réellement appliqué : la matrice n'est pas celle des bruts.
    assert not np.allclose(retriever._matrix, _normalise(raw), atol=1e-3)


async def test_repli_lexical_sans_encodeur(corpus: Path) -> None:
    retriever = await FaissRetriever.build(corpus, FakeEmbedder())
    degraded = FaissRetriever.load(
        _save(retriever, corpus.parent), embedder=None
    )
    assert degraded.degraded
    results = await degraded.retrieve("ruelle Cordiers", profile="habitue", tick=0, k=2)
    assert results
    assert results[0].metadata.get("degraded") is True


def _save(retriever: FaissRetriever, directory: Path) -> Path:
    target = directory / "index_degraded"
    retriever.save(target)
    return target


async def test_le_corpus_reel_se_construit_et_filtre() -> None:
    """Le corpus de production passe par le vrai adaptateur, sans bge-m3.

    Ce test ne dit rien de la qualité sémantique (l'encodeur est un sac de
    mots) ; il vérifie que 215 fichiers réels se chargent, s'indexent,
    se sauvegardent et respectent les filtres profil/tick.
    """
    root = Path(__file__).resolve().parents[1] / "world_corpus"
    passages = load_corpus(root)
    assert len(passages) >= 200
    assert len({p.doc_id for p in passages}) == len(passages), "doc_id dupliqué"

    retriever = await FaissRetriever.build(root, FakeEmbedder())
    par_id = {p.doc_id: p for p in passages}
    for profile in ("securite", "visiteur", "vendeur"):
        for tick in (0, 90):
            results = await retriever.retrieve(
                "évacuation fumée sortie", profile=profile, tick=tick, k=5
            )
            assert results, f"aucun résultat pour {profile} à t{tick}"
            for result in results:
                assert par_id[result.doc_id].allowed_for(profile, tick)
