# État du projet

- [2026-11-25 17:30] M-01 → pass — toutes preuves OK
- [2026-11-25 17:39] M-02 → pass — toutes preuves OK
- [2026-11-25 17:45] M-03 → pass — toutes preuves OK
- [2026-11-25 17:56] M-04 → pass — 24 assets intérieurs téléchargés, 28,7 Mo, 0 généré
- [2026-11-25 18:21] M-05 → pass — mall_aubel.yaml (WorldSpec 2 niveaux, trémie,
  2 escalators + 1 escalier, sorties A/B/C 6/3/1,5 m) chargeable via
  `world.loader.load` + 8 tests ; runs JuPedSim L0 14/20 et L1 9/20 à 30 s ;
  circulation inter-niveaux = v3.1 (LevelCoordinator absent, documenté dans
  docs/world/MALL.md) ; bug spawn corrigé au passage (espace perçu = espace réel)
- [2026-11-25 17:56] M-04 → pass — toutes preuves OK
- [2026-11-25 18:22] M-05 → pass — toutes preuves OK
- [2026-11-25 19:45] M-06 → pass — rendu isométrique 2.5D (projection 2:1,
  tri de profondeur, sol tuilé, murs extrudés, 2 niveaux + coupe, agents teintés
  par croyance, fumée/densité) ; 13 sprites pré-rendus depuis les glTF de M-04
  (`tools/prerender_iso.gd`) ; 4 captures `docs/visuel/iso/` + `docs/visuel/ISO.md` ;
  repli `--view=top` (ancien rendu) ; `make godot-test` 20/20 ; coût ≈23 img/s
- [2026-11-25 19:43] M-06 → fail — grep -q 'isom' godot/project/scripts/mai, docs/visuel/ISO.md
