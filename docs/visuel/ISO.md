# Rendu isométrique 2.5D du bâtiment (M-06)

_Décision de rendu : **isométrique 2.5D**, pas de vraie 3D. Client Godot
`godot/project/`, consommateur pur du journal (protocole WebSocket conservé)._

## 1. Pourquoi l'isométrique et pas la 3D

Le point de vue est **fixe** et l'information utile n'est pas la géométrie :
c'est la **répartition des croyances** (qui croit quelle sortie est bonne, qui
est piégé, où la foule s'étrangle). Une vraie 3D coûterait un pipeline
glTF/PBR complet, une caméra, des ombres, un budget GPU — pour un gain
d'information nul sur ce que le projet veut montrer.

L'isométrique 2.5D :

- garde la lisibilité (60 agents, étages, fumée) ;
- accepte des **tuiles et des sprites réels** (pré-rendus depuis les glTF de
  M-04, coût nul au runtime) ;
- ne coûte presque rien (pas de scène 3D, pas d'éclairage dynamique) ;
- se compare à l'ancien rendu 2D (`--view=top`) à la demande.

Ce n'est donc **pas** de la 3D : aucune géométrie 3D n'est rendue à l'exécution.
Les seuls objets 3D du dépôt sont les modèles de M-04, et ils ne servent qu'à
produire des PNG (voir §5).

## 2. Projection isométrique (2:1)

Le passage monde (mètres) → écran est exactement la projection 2:1 demandée :

```
sx = (x − y) · k
sy = (x + y) · k / 2 − élévation(niveau) · ELEV_K · k
écran = (sx, sy) + origine
```

- `k` est recalculé à chaque dessin pour tenir dans la surface libre
  (`_fit`), de 800×480 à 1920×1080 ;
- `ELEV_K = 1,15` : un mètre d'élévation monte l'étage de `1,15·k` pixels ;
- l'étage L1 (`élévation 4,5 m`) est donc posé au-dessus du rez-de-chaussée.

La conversion **inverse** sert à cliquer un agent (`_uniso`) :

```
x − y = sx/k
x + y = 2·(sy/k + élévation·ELEV_K)
⇒ x = (sx + 2·sy') / 2 ,  y = (2·sy' − sx) / 2
```

Le clic essaie chaque niveau visible et retient le premier dont l'inverse tombe
dans le contour (sinon L0). Un clic sur un indicateur du HUD est prioritaire
(F6, chaîne causale demandée au serveur).

## 3. Tri de profondeur

Chaque objet dessiné (obstacle, lien vertical, décor, agent) reçoit une clé de
profondeur `x + y` (au centroïde pour les polygones, à la position pour les
agents). La liste est triée par clé croissante et dessinée dans l'ordre : les
objets au plus grand `x + y` (les plus proches du spectateur) sont dessinés en
dernier et recouvrent les autres. C'est ce qui donne le recouvrement correct
sans z-buffer.

## 4. Sol, murs, étages

- **Sol en tuiles** : chaque espace est pavé de losanges de 2 m
  (`_draw_tiles`), avec un damier clair/sombre et un test d'appartenance au
  polygone (les trous — la trémie de l'atrium — ne sont pas pavés). Les
  textures PBR de M-04 restent disponibles ; le rendu courant utilise des
  dégradés lissés (damier) pour rester net à toute échelle.
- **Murs extrudés** : chaque obstacle est un prisme (`_draw_prism`) : faces
  latérales ombrées (côté droit plus sombre que le côté gauche) triées par
  profondeur, puis face supérieure claire. Les hauteurs viennent du
  `WorldSpec` (boutiques 3,5 m, kiosque 2,5 m, caisses 1,1 m).
- **Liens verticaux** : les deux escalators et l'escalier relient les dalles
  des deux niveaux (deux polygones + arêtes), sans quadrilatère
  auto-intersectant.
- **Multi-étages** : deux niveaux (`mall_aubel`, L0 et L1). Un sélecteur de
  niveau (touches `1`/`2`/`3`, ou `MAREE_LEVEL=L0|L1|cut`) choisit L0, L1 ou
  la **coupe** (les deux). En coupe, la trémie de l'atrium laisse voir le
  rez-de-chaussée sous la galerie ; un agent d'un niveau non actif est
  **atténué** (alpha 0,30).

## 5. Pré-rendu des sprites (vrai asset, coût nul)

`tools/prerender_iso.gd` charge chaque `.glb`/`.gltf` de M-04, le place sous
une caméra **orthographique isométrique** (lacet 45°, inclinaison 35,264°),
l'éclaire de façon neutre (deux lumières directionnelles + ambiant), rend sur
fond transparent et sauvegarde un PNG par modèle dans
`godot/project/assets/sprites_iso/`.

```bash
godot --headless --path godot/project --import          # importe les glTF
godot --path godot/project --rendering-driver opengl3 \
      --script "$PWD/tools/prerender_iso.gd"
```

**13 sprites** produits (escaliers, rampe, mur bas, porte, fenêtres, banc,
jardinière, poubelle, étagères, lampe, signalétique), tous à fond transparent et
issus de la géométrie téléchargée — **aucun modèle d'image**. Le runtime ne fait
que charger les PNG (`_load_sprites`) et les place en décor (hall).

## 6. Agents, fumée, densité

- **Agents** : une silhouette isométrique (ombre au sol + corps + tête)
  **teintée par la sortie crue** (A bleu, B vert, C orange, D violet, E cyan,
  gris = aucune croyance). Anneau orange si l'agent croit une sortie fermée,
  anneau blanc pour l'agent sélectionné. Taille `clamp(0,5·k, 3,5, 9)` px,
  lisible à 60 agents.
- **Fumée** : nappe semi-transparente au-dessus du sol, avec anneaux, à la
  position du danger (`world.smoke` ou instantané).
- **Densité** : losanges rouges translucides pour les cellules à ≥ 2 agents
  (`density_grid`).

## 7. HUD conservé

Le HUD de la v2 est conservé et adapté : six indicateurs cliquables (F6),
inspecteur à droite (mémoire, dernière décision, règle), panneau d'injection à
gauche (annonce, fermeture de sortie, fumée au clic — D3), bandeau d'annonce,
récits. La légende a été réécrite pour la projection isométrique.

## 8. Repli `--view=top`

`godot --path godot/project -- --view=top` (ou `MAREE_VIEW=top`) recharge
l'ancien rendu 2D vu de dessus (`scenes/top.tscn`, copie exacte de l'ancien
`main.gd`) pour comparer. En capture, `MAREE_VIEW=top` sélectionne la même
scène.

## 9. Protocole et captures

Le protocole WebSocket v2 est **conservé** (`hello`/`snapshot`/`world`/
`indicators`/`end`, injections D3). Le client charge la géométrie de
`mall_aubel` depuis `assets/world/mall_aubel.json` (dérivé du YAML versionné
par `tools/export_world_json.py`) et reçoit les agents par le flux.

Les quatre captures de `docs/visuel/iso/` sont produites en **mode démo**
(`MAREE_DEMO=1`) : une population déterministe de 60 agents (15 par espace),
croyance = sortie la plus proche, sans serveur. **Ce n'est pas une mesure de
simulation**, c'est une illustration du rendu (documenté comme tel). Le chemin
WebSocket, lui, reste le mode normal pour un run réel.

```bash
MAREE_DEMO=1 MAREE_LEVEL=L0  MAREE_SMOKE=0 MAREE_CAPTURE_PATH=docs/visuel/iso/01_hall_rdc.png     tools/capture.sh
MAREE_DEMO=1 MAREE_LEVEL=cut MAREE_SMOKE=0 MAREE_CAPTURE_PATH=docs/visuel/iso/02_atrium_coupe.png tools/capture.sh
MAREE_DEMO=1 MAREE_LEVEL=L1  MAREE_SMOKE=0 MAREE_CAPTURE_PATH=docs/visuel/iso/03_galerie_etage.png tools/capture.sh
MAREE_DEMO=1 MAREE_LEVEL=L0  MAREE_SMOKE=1 MAREE_CAPTURE_PATH=docs/visuel/iso/04_hall_fumee.png    tools/capture.sh
```

Les captures sont des PNG 1200×760, rendus en `--rendering-driver opengl3`
(pas de `--headless`, dont le pilote factice renvoie une texture nulle).

## 10. Coût mesuré

Mesure sur l'iGPU Intel via OpenGL Compatibility (`--rendering-driver opengl3`,
fenêtre 1000×640, 60 agents, mode coupe, `MAREE_FPS=1`) :

| Scène | Images/s |
|---|---|
| coupe, 60 agents, tuiles + murs | **18 à 27** (médiane ≈ 23) |

Le rendu se fait dans un `SubViewport` hors écran pour les captures : il n'y a
pas de cible de FPS en headless, seule l'image compte. Le coût est dominé par
le redessin complet à chaque frame (`queue_redraw`) des ~768 losanges de sol et
des prismes ; il reste très inférieur à un rendu 3D et n'utilise pas le GPU
pour de la géométrie.

## 11. Fichiers

| Chemin | Rôle |
|---|---|
| `godot/project/scripts/iso.gd` | le rendu isométrique (client) |
| `godot/project/scripts/top_view.gd` | ancien rendu 2D (repli `--view=top`) |
| `godot/project/scenes/main.tscn` | scène principale (iso) |
| `godot/project/scenes/top.tscn` | scène de repli (haut) |
| `godot/project/assets/world/mall_aubel.json` | géométrie dérivée du YAML |
| `godot/project/assets/sprites_iso/*.png` | 13 sprites pré-rendus |
| `tools/prerender_iso.gd` | pré-rendu glTF → sprites |
| `tools/export_world_json.py` | YAML → JSON pour le client |
| `docs/visuel/iso/*.png` | les 4 captures |