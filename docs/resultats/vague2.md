# Vague 2 — ce que les protocoles X8 et X9 ont réellement mesuré

_Deux protocoles ont été joués le 2026-10-30 : X8 coupe la communication
(A2 / B3), X9 coupe la préhistoire (A1). Population hybride par défaut
(12 agents LLM + 48 à règles), 60 agents, 5 graines par bras, chroniqueur
désactivé pour ne pas mélanger son coût à celui des décisions._

Fichiers bruts : `runs/experiment_x8.json`, `runs/experiment_x9.json`.
Les journaux correspondants sont dans `runs/run_x8_*` et `runs/run_x9_*`.

---

## X8 — la communication change-t-elle ce qu'on mesure ? (B3)

Le bras `sans` coupe `run.communication` : aucun `message.sent`, aucun
`heard`, donc aucune influence sociale possible. Le bras `avec` est le
comportement par défaut.

| indicateur (médiane, n = 5) | `avec` | `sans` | lecture |
|---|---:|---:|---|
| I1 consensus | **0,990** | **0,992** | **ne bouge pas** |
| I2 entropie | 0,333 | 0,461 | la dispersion augmente sans communication |
| I3 évacués | 0,967 | 0,850 | 6 agents de plus restent piégés |
| I7 délai (s) | 460 | 210 | les sortants sortent plus tôt, mais moins nombreux |
| messages émis | 58 | **0** | le contrôle négatif est réel |
| appels LLM | 77 | 131 | **+70 % sans communication** |
| mural (s) | 26,1 | 47,6 | +82 % |

### Ce qu'il faut en dire

**I1 ne distingue rien.** C'est précisément l'artefact que B3 demandait
de chercher : dans cette population, 48 agents sur 60 suivent une règle
déterministe qui choisit la même sortie ; les 12 agents LLM convergent
de toute façon vers A. I1 mesure donc **la convergence**, pas
l'influence sociale — et il la mesure aussi bien quand personne ne parle.

**Ce qui distingue les deux bras**, ce sont I2 (0,333 → 0,461), I3
(0,967 → 0,850) et le nombre de messages (58 → 0). Un indicateur qui ne
bouge pas quand on coupe le mécanisme qu'il prétend mesurer ne doit pas
être mis en avant dans une soutenance : c'est la conclusion de B3, et
elle est négative pour I1, pas pour le modèle.

**La communication réduit le coût de 41 %** (77 contre 131 appels) : un
agent qui a entendu quelque chose arrête de redécider. Un système qui
parle est un système qui pense moins souvent — résultat non prévu, et
mesurable.

**I3 et I7 tirent en sens inverse.** Sans communication, ceux qui
sortent sortent plus tôt (I7 210 s) mais ils sont moins nombreux
(I3 0,850). Afficher I7 seul donnerait l'impression que couper la
diffusion accélère l'évacuation ; c'est faux, et I3 le dit.

---

## X9 — le passé pèse-t-il sur la décision ? (A1)

Le bras `avec_passe` sème une préhistoire de trois jours : de vrais
échanges `message.sent` / `heard` entre agents, datés d'un tick négatif
(J−3 = −25 920), mémorisés avec le nom de l'émetteur.

| indicateur (médiane, n = 5) | `sans_passe` | `avec_passe` |
|---|---:|---:|
| I1 consensus | 0,990 | 0,990 |
| I3 évacués | 0,967 | 0,976 |
| I7 délai (s) | 390 | 460 |
| appels LLM | 78 | 73 |

**Au niveau agrégé, l'effet est dans le bruit.** Avec 48 agents à règles
qui ne lisent pas la mémoire, un déplacement de quelques décisions LLM
ne peut pas bouger I3 de façon nette. Le dire est plus utile que de
surinterpréter un écart de 0,009.

**Au niveau des décisions, l'effet est net.** Sur l'ensemble des
décisions LLM des cinq graines :

| mesure | `sans_passe` | `avec_passe` |
|---|---:|---:|
| décisions LLM | 394 | 379 |
| décisions dont le contexte cite la préhistoire | **0** | **188 (50 %)** |
| choix de la sortie **C** | 3 | **9** |
| choix de la sortie **A** | 51 | 45 |

Deux choses, et une seule est un artefact :

1. **La mémoire est réellement rappelée** : une décision LLM sur deux
   porte un épisode de préhistoire dans son contexte journalisé. Ce n'est
   pas une décoration : `memory` est dans `agent.decision`, donc
   vérifiable après coup.
2. **Le choix se déplace vers la sortie dont le passé parlait.** Les
   visiteurs ont entendu « la sortie C existe, derrière les stands
   ouest » ; les habitués, « la sortie C évite la passerelle ». C est
   choisie **trois fois plus souvent** avec la préhistoire (9 contre 3),
   et A recule d'autant.

C'est cela qu'A1 demande : *« se souvenir d'un échange vieux de plusieurs
jours simulés et en tenir compte »*. Le souvenir est daté (J−3), il est
un échange (un agent a parlé, un autre a écouté), il est journalisé, et
il change la décision.

**Ce que X9 ne prouve pas** : que la préhistoire améliore l'évacuation.
I3 bouge à peine, I7 se dégrade même légèrement (les agents qui prennent
C passent par un passage plus étroit). Le passé rend les décisions plus
**fondées**, pas plus **efficaces** — et le projet est un banc d'essai
pour comparer des stratégies, pas un optimiseur.

---

## Ce que la vague 2 ajoute au dossier

| exigence | avant | maintenant |
|---|---|---|
| A1 préhistoire | absente | échanges J−3 journalisés, rappelés dans 50 % des décisions LLM, effet mesuré sur le choix de sortie |
| A2 communication | partielle | `run.communication` est un bras d'expérience, pas un commentaire |
| B3 « ce que le dispositif ne distingue pas » | non traité | **I1 est aveugle à la communication** (0,990 / 0,992) ; I2, I3 et le coût distinguent |
| C6 cohérence temporelle | absente | vérificateur + compteur ; 0 violation sur les 20 runs X8/X9 |
| D2 justification | partielle | `snapshot.agents[].last_decision` : raison, règle, passages, mémoire |
| D3 injection | absente | `maree live`, `inject` → `ack` → `injection` → `world`, appliqué au tick suivant |
| E4 coût | partielle | tokens par run et par bras ; `docs/resultats/sobriete-v2.md` |
| F4 schémas | partielle | `SCHEMAS` + `validate()`, quarantaine `invalid.jsonl`, `dlq.invalid` |
| F6 traçabilité | absente | `indicators.sources = {from_seq, to_seq, count}` |
