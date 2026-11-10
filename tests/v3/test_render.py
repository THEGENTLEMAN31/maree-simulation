"""Semaine 6 (noyau) — le RenderArtifact : manifeste + glTF pour le front.

Le client Godot est de la main de l'équipe front ; le noyau produit le
**contrat** : un manifeste d'IDs stables et un document glTF 2.0 valide.
"""

from __future__ import annotations

import base64
import json

from maree.v3.world.render import manifest, render_artifact, to_gltf
from maree.v3.world.sample import sample_worldspec
from maree.v3.world.worldspec import from_dict


def test_manifest_couvre_tous_les_ids() -> None:
    m = manifest(sample_worldspec())
    for node in ("S_HALL", "A", "B", "C", "O_STAND_12"):
        assert node in m.entries
    assert m.entries["A"]["kind"] == "exit"
    assert m.entries["O_STAND_12"]["extras"]["kind"] == "stand"


def test_gltf_a_une_structure_minimale_valide() -> None:
    g = to_gltf(sample_worldspec())
    assert g["asset"]["version"] == "2.0"
    assert g["scene"] == 0
    # un nœud nommé par ID, avec extras
    names = [n["name"] for n in g["nodes"]]
    assert "S_HALL" in names and "A" in names
    # le buffer est un data-uri base64 décodable
    uri = g["buffers"][0]["uri"]
    b64 = uri.split("base64,")[1]
    assert base64.b64decode(b64)
    # chaque accessor a des bornes min/max cohérentes
    for acc in g["accessors"]:
        assert acc["min"][0] <= acc["max"][0]
        assert acc["min"][1] <= acc["max"][1]


def test_render_artifact_serialise() -> None:
    art = render_artifact(sample_worldspec())
    data = json.loads(art.to_json())
    assert "manifest" in data and "gltf" in data
    assert data["manifest"]["C"]["kind"] == "exit"


def test_gltf_avec_deux_espaces_et_un_portail() -> None:
    data = {
        "id": "mini",
        "version": 1,
        "schema": "3.0.0",
        "levels": [
            {
                "id": "L0",
                "outline": [[0, 0], [100, 0], [100, 100], [0, 100]],
                "spaces": [
                    {"id": "S1", "kind": "hall", "polygon": [[0, 0], [50, 0], [50, 100], [0, 100]]},
                    {"id": "S2", "kind": "corr", "polygon": [[50, 0], [100, 0], [100, 100], [50, 100]]},
                ],
                "portals": [
                    {"id": "P12", "between": ["S1", "S2"], "segment": [[50, 30], [50, 70]], "width": 2.0}
                ],
                "exits": [{"id": "E", "segment": [[100, 40], [100, 60]], "width": 2.0}],
                "obstacles": [],
            }
        ],
        "vertical": [],
        "hazards": [],
    }
    g = to_gltf(from_dict(data))
    assert len(g["nodes"]) == 3  # 2 espaces + 1 sortie
    assert len(g["buffers"][0]["uri"]) > 40  # un buffer non vide