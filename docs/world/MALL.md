# MALL — le centre commercial `mall_aubel` (WorldSpec multi-étages)

_Ce document décrit le monde `configs/world/mall_aubel.yaml`, écrit pour la
tâche M-05. C'est le **bâtiment** que le projet vise, par opposition à
l'esplanade extérieure `configs/world/port_aubel.yaml`. Schéma de référence :
`docs/v3/monde-et-rendu.md` §1. Tout ce qui suit se régénère par une
commande (voir §7)._

---

## 1. Ce que c'est

Un centre commercial de **48 × 32 m**, deux niveaux :

- **L0 — Rez-de-chaussée** : le hall d'entrée (ouest) et le passage des
  Halles (est), reliés par un portique de 3 m. Trois sorties d'évacuation
  de largeurs très inégales — c'est la géométrie qui produit les goulots,
  pas un paramètre de débit (héritage direct de `port_aubel`) ;
- **L1 — Galerie** : un anneau de galeries autour d'un **atrium** percé
  d'une **trémie** de 10 × 8 m (`[20,12]–[30,20]`, trou déclaré dans le
  contour L1). L'anneau est découpé en deux espaces en C (ouest, est)
  reliés par deux portiques de 4 m (passage sud, pont nord) ;
- **les liens verticaux** : deux **escalators** appariés (ESC_NORD montant
  L0→L1, ESC_SUD descendant L1→L0) et un **escalier** principal (ST_MAIN).
  Ce sont l'**unique** passage entre les deux niveaux (preuve en §5).

Les boutiques sont des **obstacles** (7 au rez-de-chaussée, 4 en galerie,
`kind: boutique`), pas des espaces : la règle 8 du validateur (« tout
espace contient une sortie ») impose cette lecture, identique à celle du
générateur `generate.py` (un hall, des sorties, des obstacles).

## 2. Chargement

Aucun code v3 ne lisait de YAML de monde : les plans vivaient en Python
(`worldspec.from_dict`, presets de `world/generate.py`). Le pont tient en
un module :

```python
from maree.v3.world.loader import load
world = load("configs/world/mall_aubel.yaml")   # YAML → from_dict → validate_or_raise
```

Un plan invalide est **refusé avec la raison** (les erreurs du validateur),
jamais corrigé en silence. `configs/world/port_aubel.yaml` n'est pas
touché : c'est un plan **v2** (format `walkable`/`zones`), lu par
`maree.domain.geometry` pour la v2 ; ce chargeur ne le concerne pas.

Test de chargement et d'affichage : `uv run pytest tests/v3/test_mall.py -s`
(le premier test imprime niveaux, espaces, portiques et sorties).

## 3. Les plans des deux niveaux

Plans **calculés** depuis les polygones du WorldSpec par
`scripts/v3_mall.py` (étape 3) — si le YAML change, le plan change.
Échelle : 1 caractère = 1 m en x, 1 ligne = 2 m en y.
`#` obstacle, `|` portique, lettres = sorties, chiffres = liens verticaux
(1 = ESC_NORD, 2 = ESC_SUD, 3 = ST_MAIN).

```
  L0 — Rez-de-chaussée (élévation 0.0 m)
  +------------------------------------------------+
  |....................3333........................|
  |....................3333........................|
  |....##########....########........##########....|
  |....##########....########........##########....|
  |....##########....########........##########....|
  |....##########....########........##########....|
  |................................................|
  |..............1111............|.......2222......|
  |B.............1111............|.......2222.....C|
  |................................................|
  |....##########....................##########....|
  |....##########......######........##########....|
  |....##########......######........##########....|
  |....##########......######........##########....|
  |................................................|
  |...............A......###.......................|
  +------------------------------------------------+

  L1 — Galerie (élévation 4.5 m) — le vide au centre est la trémie
  +------------------------------------------------+
  |...........D........3333...........E............|
  |....................3333.|......................|
  |....##########...........|........##########....|
  |....##########...........|........##########....|
  |....##########....................##########....|
  |....##########....................##########....|
  |....................          ..................|
  |..............1111..          ........2222......|
  |..............1111..          ........2222......|
  |....................          ..................|
  |....##########....................##########....|
  |....##########...........|........##########....|
  |....##########...........|........##########....|
  |....##########...........|........##########....|
  |................................................|
  |................................................|
  +------------------------------------------------+
```

À lire sur le plan L1 : la galerie **evite** la trémie (polygones en C),
les deux escalators sont posés dans la galerie le long de l'atrium, et le
vide central n'appartient à aucun espace — `space_at` y renvoie `None` et
le marchable L1 (1136 m²) l'exclut.

## 4. Les sorties et les liens verticaux

Sorties d'évacuation du rez-de-chaussée (largeurs inégales, même logique
que `port_aubel` : l'évidente, la moyenne, la cachée) :

| id | nom | largeur | position | note |
|----|-----|---------|----------|------|
| A | Grand Hall sud | **6,0 m** | mur sud, x 12–18 | l'évidente |
| B | Passage des Cordiers | **3,0 m** | mur ouest, y 14–17 | derrière les boutiques nord |
| C | Ruelle de Service | **1,5 m** | mur est, y 15–16,5 | la ruelle, goulot massif |

Sorties de la galerie (terrasses de secours, imposées par la règle 8 du
validateur : chaque espace doit contenir une sortie) :

| id | nom | largeur | position |
|----|-----|---------|----------|
| D | Terrasse ouest | 2,4 m | mur nord, x 10–13 |
| E | Terrasse est | 2,4 m | mur nord, x 34–37 |

Liens verticaux (l'empreinte d'un lien est la même aux deux niveaux) :

| id | type | sens | largeur | capacité |
|----|------|------|---------|----------|
| ESC_NORD | escalator | L0 → L1 (montant) | 2,4 m | 1,1 pers/s |
| ESC_SUD | escalator | L1 → L0 (descendant) | 2,4 m | 1,1 pers/s |
| ST_MAIN | escalier | L0 ↔ L1 | 2,0 m | 0,9 pers/s |

## 5. Preuves

**Les escalators sont l'unique passage entre niveaux.** Le validateur
pose un graphe espaces–portails–liens verticaux ; sans les trois liens,
L0 et L1 forment deux composantes et la validation **refuse** :

```
$ uv run python scripts/v3_mall.py        (étape 2)
WorldSpec sans liens verticaux → 2 erreur(s) de validation :
   - espace(s) ['S_HALL', 'S_PASSAGE'] inatteignable(s) depuis ['S_GALERIE_EST', 'S_GALERIE_OUEST']
   - espace(s) ['S_GALERIE_EST', 'S_GALERIE_OUEST'] inatteignable(s) depuis ['S_HALL', 'S_PASSAGE']
```

Un agent qui veut quitter la galerie doit donc passer par ESC_SUD ou
ST_MAIN — c'est une propriété **structurelle** du plan, vérifiée par
`tests/v3/test_mall.py::test_les_liens_verticaux_sont_l_unique_passage_entre_niveaux`.

**Chaque niveau est navigable et évacuable.** Runs JuPedSim, 20 agents à
règles, fumée à t1 (origine = le danger déclaré du niveau), 15 ticks de
2 s = **30 s de temps simulé** (graine 1, `runs/v3/mall.json`, journaux
complets dans `runs/v3/mall_l0_s1.jsonl` et `mall_l1_s1.jsonl`) :

| run | niveau | évacués à 30 s | sortie empruntée | I5 pic | I7 |
|-----|--------|----------------|------------------|--------|----|
| `mall_l0_s1` | L0 | **14/20** | A (12 attribués) | 0,16 pers/m² | 28 s |
| `mall_l1_s1` | L1 | **9/20** | D (9 attribués) | 0,32 pers/m² | 28 s |

La foule part vers la sortie la plus « confiante » (A au rez, D en
galerie) — c'est le comportement connu de la politique `rules` (choix par
confiance, égalité → première sortie connue) ; les goulots B/C/D/E
restent donc à activer par des annonces ou des savoirs différenciés,
comme en v2. L'attribution de sortie lit le dernier instantané où l'agent
figure (les 2 évacués du tick 1 n'apparaissent sur aucun instantané).

**Le run est reproductible** : deux exécutions à graine égale produisent
les mêmes décisions et le même ensemble d'évacués (test
`test_le_run_mall_est_reproductible`) ; seul le temps mural varie.

## 6. Ce qui diffère de `port_aubel`

| | `port_aubel.yaml` (v2) | `mall_aubel.yaml` (WorldSpec v3) |
|---|---|---|
| nature | esplanade **extérieure** 60 × 40 m, un niveau | **bâtiment** 48 × 32 m, deux niveaux |
| schéma | format v2 (`walkable`, `zones`, `smoke`) lu par `domain/geometry.py` | WorldSpec v3 (`levels`, `spaces`, `portals`, `exits`, `vertical`, `hazards`) validé par `world/validate.py` |
| chargement | Hydra + `domain/geometry.py` | `maree.v3.world.loader.load` |
| espaces | 8 `zones` de perception declarées (`Z1`–`Z8`, dont une cachée) | 4 `spaces` (hall, passage, 2 galeries) — **les espaces SONT les zones de perception** du moteur v3 (`ZoneId` = id d'espace, `scene.py`) |
| portiques | aucun (plan ouvert) | 3 (P_HALL_PASSAGE, P_GALERIE_SUD, P_GALERIE_NORD) |
| sorties | 3 (A 6,0 / B 1,5 / C 3,0) | 3 principales (A 6,0 / B 3,0 / C 1,5) + 2 terrasses L1 (règle 8) |
| vertical | — | 2 escalators + 1 escalier, l'unique liaison L0↔L1 |
| trémie | — | atrium `[20,12]–[30,20]`, trou du contour L1 |
| obstacles | tour, fontaine, scène, stands | 7 boutiques + kiosque + caisse (RDC), 4 boutiques (galerie) |
| fumée | `smoke:` (position, rayon, tick) | `hazards:` (feux déclarés ; la fumée d'un run reste posée par le scénario) |
| physique | JuPedSim direct | JuPedSim, un niveau par run (v3.0) |

Subtilité utile : les **portiques sont sémantiques** (perception, routage
d'espaces, fermeture éventuelle) — la physique JuPedSim voit un plan
continu par niveau, sans mur sur les portiques. Et les empreintes
d'escalators ne sont pas des obstacles : on peut traverser un escalator
arrêté, et un v3.1 devra en faire des zones de transfert, pas des murs.

## 7. Reproduire

```bash
uv run python scripts/v3_mall.py 1        # inventaire + preuve structurelle + plans + 2 runs
uv run pytest tests/v3/test_mall.py -s    # les 8 tests (chargement, trémie, structure, runs)
```

Artefacts : `runs/v3/mall.json` (résumé), `runs/v3/mall_l{0,1}_s1.jsonl`
(journales complets, en-tête + enveloppes).

## 8. La limite honnête : la circulation inter-niveaux n'est pas simulée

`monde-et-rendu.md` §7 le dit explicitement : la **v3.0 est mono-étage** —
le WorldSpec porte plusieurs niveaux (chargés, validés, navigables), mais
la simulation tourne sur un niveau et « les escaliers sont visibles, non
simulés ». Le `LevelCoordinator` de la **v3.1** (transfert, conservation,
capacité, `progress ∈ [0,1]`, déterminisme, interdiction du double
comptage + ses tests obligatoires) n'existe pas encore : `grep -r
LevelCoordinator src/` ne renvoie rien, et `Simulation.spawn` ne peuple
qu'un étage (paramètre `level` ajouté en M-05, défaut = L0, comportement
historique inchangé).

Ce que M-05 prouve donc : le monde est **chargeable et simulable** niveau
par niveau, et la circulation entre niveaux **passe nécessairement par les
escalators** (preuve structurelle §5). Ce qu'il ne prouve pas : un agent
qui *emprunte* un escalator — il faut d'abord décider du `LevelCoordinator`
(v3.1), chantier à part avec ses cinq tests obligatoires.
