#!/usr/bin/env python3
"""M-04 — téléchargement et vérification d'assets intérieurs (jamais générés).

Sources : Poly Haven (API publique), ambientCG (API v2), Kenney (download-link).
Aucun générateur d'image n'est utilisé. Les fichiers sont téléchargés puis
vérifiés (md5 annoncé quand disponible, taille, magic bytes) avant copie.
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import urllib.request
import zipfile
from pathlib import Path

DATE = "2026-11-25"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "godot" / "project" / "assets"
STAGING = ASSETS / "_staging_m04"

CC0 = "CC0-1.0"
PH_LICENSE_URL = "https://polyhaven.com/license"
ACG_LICENSE_URL = "https://ambientcg.com/license"
CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"

# (id, catégorie, usage prévu)
TEXTURES = [
    ("interior_tiles", "sols", "Carrelage poli du hall et des galeries ; fond clair sous la foule."),
    ("marble_01", "sols", "Marbre clair de l'atrium et du hall principal."),
    ("concrete_floor_01", "sols", "Béton ciré des circulations et cages d'escalier."),
    ("herringbone_parquet", "sols", "Parquet en chevrons des galeries marchandes."),
    ("white_plaster_02", "murs_plafonds", "Plâtre clair des murs de galerie."),
    ("concrete_panels", "murs_plafonds", "Panneaux de béton des cages d'escalier et murs techniques."),
    ("ceiling_interior", "murs_plafonds", "Plafond intérieur de l'atrium."),
    ("wooden_panels", "murs_plafonds", "Panneaux bois acoustiques des galeries."),
]

MODELS_PH = [
    ("painted_wooden_bench", "mobilier", "Banc d'attente dans le hall et les galeries."),
    ("planter_box_02", "mobilier", "Bac à plante pour délimiter les flux sans boucher les issues."),
    ("metal_trash_can", "mobilier", "Poubelle le long des vitrines."),
    ("wooden_display_shelves_01", "mobilier", "Présentoir de galerie marchande."),
    ("modern_ceiling_lamp_01", "eclairage", "Plafonnier de l'atrium et du hall."),
]

# pack -> (download id Kenney, page, [entrées ZIP -> chemin final])
KENNEY = {
    "modular-buildings": (
        "6173736574732f6d6f64756c61722d6275696c64696e6773",
        "https://kenney.nl/assets/modular-buildings",
        [
            ("Models/GLB format/door-white-glass.glb", "models/kenney/modular-buildings/door-white-glass.glb",
             "vitrines_verre", "Porte vitrée des sorties et des boutiques (panneau vitré blanc)."),
            ("Models/GLB format/window-white-large.glb", "models/kenney/modular-buildings/window-white-large.glb",
             "vitrines_verre", "Vitrine de boutique / garde-corps vitré de l'atrium (panneau large)."),
            ("Models/GLB format/building-window-large.glb", "models/kenney/modular-buildings/building-window-large.glb",
             "vitrines_verre", "Grande vitrine de galerie marchande, remplissage vitré."),
        ],
    ),
    "building-kit": (
        "6173736574732f6275696c64696e672d6b6974",
        "https://kenney.nl/assets/building-kit",
        [
            ("Models/GLB format/stairs-open.glb", "models/kenney/building-kit/stairs-open.glb",
             "circulation", "Marches ouvertes d'escalator / cage d'escalier."),
            ("Models/GLB format/stairs-sides.glb", "models/kenney/building-kit/stairs-sides.glb",
             "circulation", "Garde-corps d'escalator et main courante latérale."),
            ("Models/GLB format/wall-low.glb", "models/kenney/building-kit/wall-low.glb",
             "circulation", "Socle maçonné du garde-corps vitré de l'atrium."),
        ],
    ),
    "platformer-kit": (
        "6173736574732f706c6174666f726d65722d6b6974",
        "https://kenney.nl/assets/platformer-kit",
        [
            ("Models/GLB format/platform-ramp.glb", "models/kenney/platformer-kit/platform-ramp.glb",
             "circulation", "Rampe d'accès entre hall et galerie."),
            ("Models/GLB format/sign.glb", "models/kenney/platformer-kit/sign.glb",
             "signaletique", "Support de panneau de sortie de secours."),
        ],
    ),
    "game-icons": (
        "6173736574732f67616d652d69636f6e73",
        "https://kenney.nl/assets/game-icons",
        [
            ("PNG/White/2x/exit.png", "signage/kenney_game_icons/exit.png",
             "signaletique", "Pictogramme blanc de sortie à coller sur panneau vert de sécurité."),
            ("PNG/White/2x/exitRight.png", "signage/kenney_game_icons/exitRight.png",
             "signaletique", "Pictogramme directionnel blanc vers la sortie de secours."),
        ],
    ),
}

ACG_ASSET = "Carpet016"
ACG_PAGE = "https://ambientcg.com/a/Carpet016"
ACG_ZIP_URL = "https://ambientcg.com/get?file=Carpet016_1K-JPG.zip"
ACG_MAPS = [
    ("Carpet016_1K-JPG_Color.jpg", "textures/ambientcg/Carpet016/Carpet016_Color.jpg", "albedo"),
    ("Carpet016_1K-JPG_NormalGL.jpg", "textures/ambientcg/Carpet016/Carpet016_NormalGL.jpg", "normal OpenGL"),
    ("Carpet016_1K-JPG_Roughness.jpg", "textures/ambientcg/Carpet016/Carpet016_Roughness.jpg", "rugosité"),
    ("Carpet016_1K-JPG_AmbientOcclusion.jpg", "textures/ambientcg/Carpet016/Carpet016_AmbientOcclusion.jpg", "occlusion ambiante"),
]


def get(url: str, headers: dict[str, str] | None = None) -> bytes:
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def api_json(url: str, headers: dict[str, str] | None = None) -> dict:
    return json.loads(get(url, headers))


def verified_write(data: bytes, relative: str, expected_md5: str | None, expected_size: int | None) -> dict:
    if not data:
        raise RuntimeError(f"fichier vide : {relative}")
    if expected_md5 and md5(data) != expected_md5:
        raise RuntimeError(f"md5 divergent : {relative}")
    if expected_size and len(data) != expected_size:
        raise RuntimeError(f"taille divergente : {relative} ({len(data)} != {expected_size})")
    destination = ASSETS / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return {"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


records: list[dict] = []


def add_asset(asset_id: str, category: str, author: str, source: str, usage: str,
              license_url: str, files: list[dict], license_name: str = CC0,
              extra: dict | None = None) -> None:
    entry = {
        "id": asset_id,
        "path": files[0]["path"],
        "files": [f["path"] for f in files],
        "category": category,
        "license": license_name,
        "license_url": license_url,
        "author": author,
        "source": source,
        "date_downloaded": DATE,
        "usage_prevu": usage,
    }
    if extra:
        entry.update(extra)
    entry["file_details"] = files
    records.append(entry)


def download_polyhaven_texture(asset_id: str, category: str, usage: str) -> None:
    info = api_json(f"https://api.polyhaven.com/info/{asset_id}")
    files = api_json(f"https://api.polyhaven.com/files/{asset_id}")
    author = ", ".join(info["authors"].keys())
    out = []
    for map_name, suffix in [("Diffuse", "diff"), ("nor_gl", "nor_gl"), ("arm", "arm")]:
        entry = files[map_name]["1k"]["jpg"]
        data = get(entry["url"])
        name = Path(entry["url"].split("?")[0]).name
        out.append(verified_write(data, f"textures/poly_haven/{asset_id}/{name}",
                                  entry.get("md5"), entry.get("size")))
    add_asset(asset_id, category, author, f"https://polyhaven.com/a/{asset_id}",
              usage, PH_LICENSE_URL, out)


def download_polyhaven_model(asset_id: str, category: str, usage: str) -> None:
    info = api_json(f"https://api.polyhaven.com/info/{asset_id}")
    files = api_json(f"https://api.polyhaven.com/files/{asset_id}")
    author = ", ".join(info["authors"].keys())
    gltf = files["gltf"]["1k"]["gltf"]
    base = f"models/poly_haven/{asset_id}_1k"
    out = []
    main_name = Path(gltf["url"].split("?")[0]).name
    out.append(verified_write(get(gltf["url"]), f"{base}/{main_name}",
                              gltf.get("md5"), gltf.get("size")))
    for relative, entry in gltf["include"].items():
        out.append(verified_write(get(entry["url"]), f"{base}/{relative}",
                                  entry.get("md5"), entry.get("size")))
    add_asset(asset_id, category, author, f"https://polyhaven.com/a/{asset_id}",
              usage, PH_LICENSE_URL, out)


def download_ambientcg() -> None:
    info = api_json(
        "https://ambientcg.com/api/v2/full_json?id=Carpet016&include=downloadData"
    )["foundAssets"][0]
    downloads = info["downloadFolders"]["default"]["downloadFiletypeCategories"]["zip"]["downloads"]
    target = next(d for d in downloads if d["fileName"] == "Carpet016_1K-JPG.zip")
    archive = get(target["downloadLink"])
    if len(archive) != target["size"]:
        raise RuntimeError("taille du ZIP ambientCG divergente")
    out = []
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        for name, destination, role in ACG_MAPS:
            data = zf.read(name)
            detail = verified_write(data, destination, None, None)
            detail["role"] = role
            out.append(detail)
    add_asset("Carpet016", "sols", "Lennart Demes (ambientCG)", ACG_PAGE,
              "Moquette claire des galeries et du hall ; absorbe le bruit et garde un fond neutre.",
              ACG_LICENSE_URL, out)


def download_kenney() -> None:
    STAGING.mkdir(parents=True, exist_ok=True)
    for pack, (download_id, page, entries) in KENNEY.items():
        headers = {"Referer": page}
        link = api_json(f"https://kenney.nl/download-link/{download_id}", headers)["url"]
        archive = get(link, headers)
        if len(archive) < 10_000:
            raise RuntimeError(f"archive Kenney invalide pour {pack}")
        archive_path = STAGING / f"{pack}.zip"
        archive_path.write_bytes(archive)
        with zipfile.ZipFile(archive_path) as zf:
            names = set(zf.namelist())
            for source_name, destination, category, usage in entries:
                if source_name not in names:
                    raise RuntimeError(f"entrée absente de {pack} : {source_name}")
                data = zf.read(source_name)
                if destination.endswith(".glb") and data[:4] != b"glTF":
                    raise RuntimeError(f"GLB invalide : {destination}")
                if destination.endswith(".png") and data[:8] != b"\x89PNG\r\n\x1a\n":
                    raise RuntimeError(f"PNG invalide : {destination}")
                detail = verified_write(data, destination, None, None)
                add_asset(Path(destination).stem, category,
                          "Kenney (Kenney Vleugels)", page, usage, CC0_URL,
                          [detail], extra={
                              "pack": pack,
                              "source_archive": "https://kenney.nl/assets/" + pack,
                              "source_entry": source_name,
                          })


def write_catalog() -> None:
    manifest = {
        "version": 1,
        "generated": DATE,
        "scope": "Assets intérieurs (centre commercial / musée) — téléchargés, jamais générés",
        "total_assets": len(records),
        "total_files": sum(len(a["files"]) for a in records),
        "license_summary": {"CC0-1.0": len(records)},
        "sources": ["https://polyhaven.com/", "https://ambientcg.com/", "https://kenney.nl/assets"],
        "assets": [
            {k: v for k, v in a.items() if k != "file_details"}
            for a in records
        ],
    }
    (ASSETS / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# CREDITS — assets intérieurs MARÉE (M-04)",
        "",
        "Date de constitution : 2026-11-25.",
        "",
        "Tous les fichiers ci-dessous ont été **téléchargés** depuis Poly Haven, ambientCG",
        "ou Kenney. Aucun asset généré, aucun asset extérieur réutilisé, aucune image",
        "produite par un modèle. Les archives Kenney sont signées CC0 dans leur",
        "`License.txt` ; les métadonnées Poly Haven et ambientCG proviennent de leurs API.",
        "",
        "## Assets logiques (une ligne par asset)",
        "",
        "| Asset | Fichiers | Auteur | Licence | URL source | Date |",
        "|---|---:|---|---|---|---|",
    ]
    for a in records:
        lines.append(
            f"| `{a['id']}` | {len(a['files'])} | {a['author']} | {a['license']} "
            f"| <{a['source']}> | {a['date_downloaded']} |"
        )
    lines += [
        "",
        "## Fichiers téléchargés (une ligne par fichier)",
        "",
        "| Fichier (relatif à `godot/project/assets/`) | Asset | Auteur | Licence | URL source | Date |",
        "|---|---|---|---|---|---|",
    ]
    for a in records:
        for f in a["files"]:
            lines.append(
                f"| `{f}` | `{a['id']}` | {a['author']} | {a['license']} "
                f"| <{a['source']}> | {a['date_downloaded']} |"
            )
    lines += [
        "",
        "Licences : Poly Haven <https://polyhaven.com/license>, ambientCG",
        "<https://ambientcg.com/license>, CC0 1.0",
        "<https://creativecommons.org/publicdomain/zero/1.0/>.",
        "",
    ]
    (ASSETS / "CREDITS.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    for asset_id, category, usage in TEXTURES:
        download_polyhaven_texture(asset_id, category, usage)
    for asset_id, category, usage in MODELS_PH:
        download_polyhaven_model(asset_id, category, usage)
    download_ambientcg()
    download_kenney()
    write_catalog()
    print(f"{len(records)} assets, {sum(len(a['files']) for a in records)} fichiers")


if __name__ == "__main__":
    main()
