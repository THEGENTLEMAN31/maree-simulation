# Sources d'assets — MARÉE M-01

Date : 2026-11-25

## Sources retenues

| Source | Licence | Usage | Notes |
|---|---|---|---|
| [Poly Haven](https://polyhaven.com/) | CC0 1.0 | Textures PBR et modèles glTF | API publique, métadonnées et checksums MD5 disponibles. Téléchargement en 1K JPG pour les textures, glTF 1K pour les modèles. |

## Assets retenus

12 assets logiques (8 matériaux texture + 4 props 3D), 39 fichiers, ~22,9 Mo au total. Voir `godot/project/assets/manifest.json` et `godot/project/assets/CREDITS.md` pour le détail par asset.

## Sources / candidats écartés

| Candidat | Source | Raison de l'écart |
|---|---|---|
| Kit Kenney (divers packs port/urbain) | https://kenney.nl/assets | CC0, mais le site renvoyait HTTP 403 au fetch programmatique direct pendant la session ; les packs ZIP complets sont moins sélectifs que les téléchargements par asset. Poly Haven couvrait les besoins portuaires identifiés avec une API claire. |
| ambientCG Water002 / Planks034 | https://ambientcg.com/ | CC0, mais la requête API `full_json?id=...` a renvoyé 0 résultat pour ces identifiants dans le format testé ; plutôt que de deviner l'URL de téléchargement sans métadonnées confirmées, l'asset a été écarté. |
| Poly Haven `wooden_barrels_01` (modèle) | https://polyhaven.com/a/wooden_barrels_01 | CC0, pertinent visuellement, mais le glTF 1K pesait ~31 Mo (textures incluses) pour un seul prop ; écarté pour garder un budget taille confortable et privilégier plusieurs props plus légers. |
| HDRI Poly Haven (ciel / éclairage port) | https://polyhaven.com/hdris | CC0, utile pour rendu, mais les HDRI 1K+ sont volumineux et non nécessaires pour cette première vague de matériaux/props ; reporté à une tâche dédiée éclairage. |
| Textures 2K/4K | Poly Haven | CC0, meilleure résolution, mais inutile pour la première intégration et plus coûteux en taille. Les 1K JPG ont été choisis pour rester sous 300 Mo au total. |
| Textures d'eau dédiées | Divers | Pas de texture d'eau Poly Haven évidente en catégorie textures ; les candidats externes sans métadonnée de licence claire dans la session ont été écartés par principe. |

## Règles appliquées

- Aucun asset sans licence identifiable.
- Aucun asset généré.
- Aucun asset existant remplacé.
- Vérification après téléchargement : taille non nulle, MD5 Poly Haven conforme pour les fichiers avec checksum exposé, glTF parsable et références internes résolues.
- Écriture limitée à `godot/project/assets/` et `docs/assets/`.
