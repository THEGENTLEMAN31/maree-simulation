# Direction artistique — assets d'intérieur (M-04)

Date : 2026-11-25. Périmètre : `godot/project/assets/` (aucune scène modifiée).

Le projet simule une évacuation **dans un bâtiment** : hall d'entrée, galerie
marchande, atrium, cage d'escalier. La vague M-04 fournit **24 assets logiques,
66 fichiers, 28,7 Mo**, tous téléchargés ; détail dans `CREDITS.md` et
`manifest.json`. Aucun fichier n'a été généré par un modèle d'image, aucun
asset du dossier `_hors-sujet-exterieur/` n'a été réutilisé.

## Palette retenue

Les valeurs ci-dessous sont les moyennes RVB mesurées sur les cartes d'albedo
téléchargées (moyenne d'une image redimensionnée à 64 × 64). Ce sont les teintes
des fichiers tels quels — pas des teintes appliquées dans une scène.

| Rôle | Asset | Albedo moyen | Lecture |
|---|---|---|---|
| Carrelage poli du hall | `interior_tiles` | `#AA9884` | Beige tiède, contraste suffisant sous les agents colorés |
| Marbre clair de l'atrium | `marble_01` | `#B19D7A` | Clair mais veiné, à utiliser en grandes dalles |
| Béton ciré des circulations | `concrete_floor_01` | `#766B59` | Fond moyen, sobre |
| Moquette des galeries | `Carpet016` | `#BCB093` | Le plus clair des sols, absorbe le bruit visuel |
| Parquet en chevrons | `herringbone_parquet` | `#93704D` | Chaleureux, réservé aux galeries |
| Plâtre mural | `white_plaster_02` | `#8E877A` | Gris clair, plus sombre que son nom ne le suggère |
| Béton des cages d'escalier | `concrete_panels` | `#97836F` | Neutralité minérale |
| Plafond d'atrium | `ceiling_interior` | `#7B6F65` | Gris moyen, moins disant que le sol |
| Panneaux acoustiques | `wooden_panels` | `#4E2213` | Bois sombre, accent ponctuel uniquement |

Choix : une **base minérale claire et désaturée** (beige/gris), des accents
bois sombre limités aux panneaux acoustiques et au mobilier, et aucun motif
très contrasté au sol. Les fichiers sont livrés bruts : si l'éclairage Godot
les assombrit, c'est l'exposition du matériau qu'il faut corriger, pas
l'image téléchargée. Les cartes `nor_gl` et `arm` Poly Haven et les maps
ambientCG (NormalGL, Roughness, AO) sont fournies pour garder un relief lisible
sans saturer la couleur.

Les **couleurs de sortie** ne sont pas des assets de cette vague : aucun
panneau vert photoreal n'a été téléchargé. Les pictogrammes Kenney sont
monochromes blancs (`exit`, `exitRight`) et le support `sign` est neutre. La
couleur de sécurité doit être appliquée côté Godot (panneau plein vert
`#0B6E4F`, barrière rouge `#C0392B` si issue fermée) au-dessus de ces
pictogrammes. C'est un choix de matériau/UI, pas une image générée.

## Ce qui a été écarté et pourquoi

| Candidat | Raison |
|---|---|
| `coast_sand_01`, `gravel_floor`, `wood_floor_deck`, `rusty_metal_04`, `street_lamp_01`, caisses/tonneaux/seaux Poly Haven | Décors extérieurs / portuaires : hors sujet, déjà isolés dans `assets/_hors-sujet-exterieur/`. |
| Poly Haven `dirty_carpet` | Moquette sale et tachée : le bruit visuel masquerait la foule et la fumée. Remplacée par ambientCG `Carpet016`, claire et unie. |
| Poly Haven `fabric_pattern_05`, `quatrefoil_jacquard_fabric` | Motifs textiles à motifs fortes : concurrents des agents à l'écran. |
| Kenney `city-kit-commercial` | Kit validé CC0 et téléchargé pour inspection, mais composé de silhouettes d'immeubles et d'auvents : pas de vitrine intérieure exploitable. Non intégré. |
| Kenney `game-icons` variantes noires | Pictogrammes noirs illisibles sur sol sombre ; seules les variantes blanches 2× ont été retenues. |
| Sources sans licence explicite ou sans URL stable | Refusées par principe (règle du chantier). |
| Textures 2K/4K/8K | Inutiles à la résolution du client et coûteuses en taille ; le budget est de 28,7 Mo pour cette vague. |
| Assets « escalator » photorealistes | Aucun modèle CC0 vérifiable et disponible dans les trois sources retenues. Approximation assumée par `stairs-open` + `stairs-sides` + `wall-low` de Kenney, à réévaluer si une source fiable apparaît. |

## Comment chaque asset sert la lisibilité de l'évacuation

| Catégorie | Assets | Effet recherché |
|---|---|---|
| Sols | `interior_tiles`, `marble_01`, `concrete_floor_01`, `herringbone_parquet`, `Carpet016` | Différencier hall (carrelage clair), atrium (marbre) et galeries (parquet/moquette) sans changer brutalement de valeur : la foule reste détachable sur fond clair, et un changement de sol annonce un changement de zone avant même de lire la signalétique. |
| Murs/plafonds | `white_plaster_02`, `concrete_panels`, `ceiling_interior`, `wooden_panels` | Murs et plafonds plus calmes que le sol ; les panneaux bois sombres signalent les zones de repli/attente, pas les axes de fuite. |
| Vitrines et verre | `door-white-glass`, `window-white-large`, `building-window-large` | Repères de boutiques et limites visuelles des galeries. Le verre clair laisse voir la foule derrière la vitrine : un agent qui hésite reste visible, ce qui rend l'écart de décision lisible. |
| Circulation | `stairs-open`, `stairs-sides`, `wall-low`, `platform-ramp` | `stairs-open` porte les marches, `stairs-sides` la main courante, `wall-low` le socle du garde-corps ; `platform-ramp` indique la voie sans marche. Leur géométrie simple canalise le regard vers les niveaux, donc vers les issues. |
| Mobilier | `painted_wooden_bench`, `planter_box_02`, `metal_trash_can`, `wooden_display_shelves_01`, `modern_ceiling_lamp_01` | Obstacles crédibles qui créent des goulots sans boucher les sorties ; le plafonnier éclaire l'atrium pour que la couleur des panneaux reste lisible en fin de run. |
| Signalétique | `sign`, `exit`, `exitRight` | Support plus pictogrammes blancs : le panneau se lit comme un repère unique, distinct du mobilier. Deux directions (`exit`, `exitRight`) permettent de montrer un désaccord entre annonce et direction perçue. |

**Contraste sol/foule.** Les agents du client sont des disques colorés sur une
scène 2D ; plus le sol est clair et uni, plus leur trajectoire se lit. Les cinq
sols retenus sont tous dans une plage beige/gris clair à moyen (voir le tableau
de palette) ; aucun motif à fort contraste n'a été retenu.

**Couleurs des sorties.** La teinte de sécurité n'est pas dans les fichiers :
elle est appliquée au support `sign` par un matériau Godot. Le pictogramme
blanc garde ainsi un contraste élevé sur le vert, y compris quand la fumée
commence à désaturer la scène.

**Visibilité de la fumée.** Le voile de fumée est un effet de rendu, pas un
asset de cette vague. Les surfaces neutres et désaturées qui dominent la
palette le rendent visible par différence de saturation plus que par
différence de luminance ; c'est pourquoi ni le sable, ni le gravier, ni les
motifs textiles chargés n'ont été retenus. Les `arm`/`roughness` des sols évitent
les reflets blancs qui masqueraient le voile sur le marbre.

## Contraintes vérifiées

- Taille : 28,7 Mo pour les 66 fichiers de cette vague ; avec les assets
  extérieurs déjà présents, `godot/project/assets/` reste à ~50 Mo, très
  en dessous de 400 Mo.
- Aucune entrée de scène (`.tscn`, `.gd`) modifiée : les fichiers ne sont
  qu'un catalogue, aucun `load()`/`preload()` ajouté.
- Vérification au téléchargement : md5 et taille annoncés pour les fichiers
  Poly Haven, taille pour l'archive ambientCG, magic bytes `glTF`/PNG pour
  Kenney, décodage JPEG effectif pour les cartes. Le script reproductible est
  `tools/fetch_assets_m04.py`.
- Licence : CC0 1.0 pour les trois sources ; auteur, URL et date pour chaque
  fichier dans `godot/project/assets/CREDITS.md`, et `source` complète dans
  `godot/project/assets/manifest.json`.
