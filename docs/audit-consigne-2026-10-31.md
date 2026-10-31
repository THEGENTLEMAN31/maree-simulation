# Audit de conformité au cahier des charges

_31 octobre 2026. Source : `~/Downloads/Mondes-Vivants_Projet-5A-IABD.html`,
relu intégralement, confronté au code — pas aux documents que nous avons
écrits nous-mêmes._

> **Le verdict qui compte.** Le cahier des charges dit : « Une simulation
> qui n'atteint pas le socle du défi commun ne peut pas être validée. »
> Deux exigences de **socle** ne sont pas tenues : **D2** et **D3**. Elles
> sont tenues au niveau du *protocole*, pas de l'*interface*. Le reste est
> solide, mais `docs/plan-socle.md` annonçait 32/32 : c'était faux.

---

## 1. Non fait — et bloquant pour le socle

### D2 (Socle) — inspection d'un agent : mémoire et justification absentes

> « L'utilisateur peut sélectionner un agent pendant le run et consulter
> **sa mémoire** ainsi que **la justification de sa dernière décision**.
> Pour un agent à règles, il consulte **son état et la règle appliquée**. »

**Ce qui existe.** La sélection au clic (`_select_at`), et le moteur envoie
tout ce qu'il faut : `snapshot.agents[].memory` (3 épisodes datés),
`last_decision` (raison, règle, passages RAG), `beliefs`, `perceived`.
Voir `engine/simulation.py::_snapshot`.

**Ce qui manque.** Le client n'affiche que profil, intention, croyance
dominante, position (`godot/project/scripts/main.gd::_draw_inspector`).
Aucune référence à `memory` ni à `last_decision` dans tout `godot/`.
L'observateur ne peut donc pas répondre à « pourquoi ce commerçant garde
sa boutique ouverte ? », qui est la question que le cahier des charges met
explicitement sous D2.

**Coût.** Faible : les données sont déjà dans la trame, c'est de
l'affichage (panneau défilant). C'est la correction la plus rentable du
dépôt.

### D3 (Socle) — injection d'événement impossible depuis l'interface

> « L'utilisateur peut **injecter un événement en direct depuis
> l'interface** et en voir les effets se propager. »

**Ce qui existe.** Le protocole complet : `{"type": "inject", "kind":
"announcement" | "smoke" | "exit_closed"}`, `maree live`, file de contrôle
drainée en tête du tick suivant, `control.injection` journalisé, effets
vérifiés de bout en bout — **avec un script Python**, pas avec le client.

**Ce qui manque.** `grep "send|inject|put_packet" godot/` → **vide**. Le
client ne peut pas émettre. L'exigence dit « depuis l'interface » : elle
n'est pas tenue.

**Coût.** Modéré : trois boutons (annonce, fumée, fermeture) + un
`_ws.send_text()`. Le serveur sait déjà tout recevoir.

### Le livrable écrit : le rapport hybride n'existe pas comme document

> « **Rapport technique hybride.** Partie technique. Architecture et choix
> justifiés, architecture de données, modèle de temps, gestion des
> contraintes des LLM gratuits, articulation simulation / Kafka / Godot.
> Partie scientifique, rédigée comme un mini-article. **Bilan de
> sobriété.** »

Les matériaux existent et sont bons, mais éclatés : `architecture-v2.md`,
`hypotheses.md`, `resultats/rapport-v2.md` (tableaux par protocole),
`resultats/conclusions-v2.md` (lecture par hypothèse), `stockage.md`,
`resultats/sobriete-v2.md`, `resultats/vague2..4.md`, `plan-socle.md`.
Aucun document ne les assemble dans la forme demandée. Un jury qui reçoit
le dépôt doit pouvoir lire **un** rapport, pas reconstituer huit notes.

### Les six questions du jury

> « Les questions que le jury vous posera : Q1… Q6. »

Aucune réponse écrite nulle part (seul le cadrage mentionne Q5 en
passant). Or Q1, Q2, Q3, Q4 exigent des chiffres que nous avons mais
n'avons jamais assemblés. C'est la partie « communication » de la note.

### O2 — la « posture d'assistant prudent » n'est pas diagnostiquée

> « Diagnostiquer les dérives des agents (sortie de rôle, réponse
> inexploitable, **posture d'« assistant prudent »**). »

A4 typie `no_response`, `unparseable`, `unknown_exit`, `out_of_role`,
`unknown_zone`. Rien pour « ton calme et altruiste ». `grep "prudent"` sur
`docs/` et `src/` : aucun résultat.

### F2 / Q5 — la « récupération douteuse » promise n'existe pas

`docs/cadrage-maree.md:138` : « Un score de similarité sous un seuil à
calibrer **déclenche un événement de récupération douteuse** : c'est ainsi
que le système s'aperçoit d'une information mal retrouvée (question Q5 du
jury). » Aucun événement de ce type dans `src/` ; `grep douteuse` ne
renvoie que cette phrase. **Le cadrage documente une fonction absente.**

### B3 — le troisième contrôle négatif n'a jamais été joué

Le cadrage prévoit trois contrôles : (1) communication coupée, (2) annonce
neutre, (3) **diversité des justifications** (distance d'embeddings entre
agents d'un même modèle et de modèles différents). Les deux premiers sont
faits (X8) ; le troisième n'a pas de run et n'est même pas discuté dans
les docs v2 — c'est pourtant le contrôle qui répond à Q2 (« mesurez-vous
l'émergence ou la ressemblance des réponses d'un même modèle ? »).

### Les deux leviers d'expérimentation MARÉE non testés

La fiche du monde en propose quatre. Deux sont faits (clarté des annonces
→ X1 ; fermeture soudaine d'une sortie → X2). Deux ne le sont pas :

- **nombre et visibilité des agents de sécurité** — aucun protocole ;
- **proportion de groupes familiaux et d'individus seuls** — aucun
  protocole (`configs/experiment/*` ne fait varier que les effectifs
  totaux, jamais la composition).

### Divers

- **C8** « deux tailles de population **en soutenance** » : fait en
  protocole (X10, 20 vs 60), mais un seul run est versionné
  (`runs/demo_replay`). La démo 20/60 est à générer le jour J.
- **O4** « conditions dégradées : quota d'API atteint, pic d'événements » :
  jamais éprouvé. L'agent muet et la réponse inexploitable, oui.
- **« Panique irrationnelle »** (piste de réflexion n° 4 de la fiche) : le
  cadrage promet de rapporter si nos agents la reproduisent ; rien n'est
  mesuré.
- **LangGraph** — contrainte non négociable : « Frameworks autorisés **si
  vous savez expliquer leur fonctionnement interne** ». Aucun document
  n'explique `StateGraph`, les nœuds, les arêtes, la reprise.
- **CodeCarbon / EcoLogits** cités par les ressources « Mesurer la
  sobriété » et promis au cadrage : ni l'un ni l'autre.

---

## 2. Fait partiellement

### D1 (Socle) — la scène est lisible, mais 2 des 4 items du monde manquent

La fiche MARÉE liste ce qu'on doit voir. État réel :

| Attendu | État |
|---|---|
| déplacements individuels sur le plan | ✅ plan, obstacles, trois sorties colorées ouvertes/fermées |
| ce que chacun croit **et l'écart avec la réalité** | ⚠️ la croyance est colorée ; **l'écart (I6) n'est pas affiché**, et le HUD ne montre que I1 et I5 |
| **goulots, groupes qui suivent un meneur, zones d'hésitation** | ❌ le snapshot porte `density_grid` (goulots) et `beliefs` complets : rien n'est dessiné |
| décompte des évacués et temps écoulé | ✅ HUD |

D1 tient sur la lisibilité (« compréhensible pour un observateur qui ne
connaît pas le code » — partiellement : `I1 0.82` s'affiche sans légende),
mais pas sur le contenu que le sujet demande de rendre visible.

### F6 (Standard) — traçable par la CLI, pas par l'interface

`maree trace --run-id … --indicator I1_consensus` remonte aux événements
bruts (vérifié). Le cadrage promet un **clic sur un indicateur** dans
Godot ; il n'existe pas. L'exigence ne dit pas « dans l'interface », donc
elle est tenue — mais pas comme le projet l'avait écrit.

### B3 (Socle) — tenu par I2, pas par I1

X8 : I1 0,990 → 0,992 (**ne distingue rien**, c'est publié), I2 0,333 →
0,461 (**distingue**). B3 s'appuie donc sur I2. C'est honnête et mesuré,
mais la démonstration repose sur un seul indicateur et sur 2 contrôles
négatifs sur 3.

### O1 — « taux de sortie de rôle mesuré »

Nous comptons des incidents absolus (8 incidents sur `c4_async_02`), pas
un **taux** (incidents / décisions, par modèle, au fil du run). La
formulation du cahier des charges demande un taux.

### F2 — évalué sur des requêtes, pas sur des décisions

Le cahier des charges : « pour un échantillon de **décisions**, il montre
ce qui a été retrouvé et évalue sa pertinence ». Nous avons 24 **requêtes**
annotées (P@1 0,417, P@3 0,750, MRR 0,569) construites à partir de
situations réelles, mais pas un tirage aléatoire de décisions.

### E4 — énergie mesurée une fois, pas par bras

0,46 Wh sur un run hybride. X12 et X4 rapportent appels, jetons, mural,
pas l'énergie.

### C1 — Kafka est le défaut, mais pas dans les runs mesurés

`configs/config.yaml` : `backend: redpanda`. **Tous** les runs de campagne
tournent en `memory` ; Kafka est prouvé par un run dédié (1 002 messages,
Redpanda réel). « Les événements du monde transitent par Kafka » est donc
vrai de l'architecture, pas des mesures.

### Reproductibilité sur une autre machine

Le livrable demande « lancer la simulation de façon reproductible sur une
autre machine, **en suivant une procédure documentée** ». La procédure du
README commence par `make up` = `docker compose up -d`, qui **n'a jamais
tourné ici** (apt sans réseau, publication de ports cassée). La procédure
qui fonctionne est dans `AGENTS.md` (`docker run` + IP du conteneur),
c'est-à-dire dans une note interne, pas dans le README.

### E5 / A5 — dit et assumé, mais à redire dans le rapport

Deux tailles : oui. Mais le petit modèle **applique une politique** (il ne
juge pas), et l'apport n'est comparable qu'en I3 (I7 +70 s). Le 5ᵉ bras
« small → règles » qui trancherait la question n'a pas été joué.

### E2 — dispersion : min-max et Mann-Whitney, sans écart interquartile

Le cadrage promet « médiane et écart interquartile ». `rapport-v2.md`
donne médiane, [Q1–Q3] (donc l'IQR) et Mann-Whitney : c'est bon sur les
protocoles X1–X7 ; les tableaux de la vague 4 (X10–X12) ne donnent que la
médiane et des bornes.

---

## 3. Mal fait — à corriger avant de rendre

| Où | Ce qui est faux | Conséquence |
|---|---|---|
| `docs/plan-socle.md` | annonce **32/32** | surévaluation : D2 et D3 ne sont pas tenus dans l'interface |
| `README.md` | `make up` en tête ; « I1..I6 » sans I7 ; sous-commandes `experiment`, `query`, `state`, `lag`, `trace`, `live` non documentées ; diagramme « Redpanda → Godot » alors que les campagnes sont en `memory` | un lecteur ne peut pas lancer le projet tel que documenté |
| `docs/cadrage-maree.md` | L138 événement de récupération douteuse (inexistant) ; L226 clic sur un indicateur + inspection complète (inexistants) ; L250 « Parquet » alors que L171 dit JSONL ; L284 CodeCarbon/EcoLogits ; L322 « OpenRouter » | promesses contredites par le code, dans le document que le jury lira en premier |
| `maree report --help` | « agrège les runs mesurés (I1..I6) » | la commande sort aussi I7 |
| `docs/resultats/` | `rapport-experiences.md` est la v1 | déjà marqué obsolète — vérifier qu'aucune conclusion ne le cite |

---

## 4. Compte honnête

| Statut | Exigences | Nombre |
|---|---|---|
| **Tenu** | A1, A2, A3, A4, A5, A6, B1, B2, B4, C2, C3, C4, C5, C6, C7, D*—*, E1, E3, F1, F3, F4 | 20 |
| **Tenu partiellement** | B3, C1, C8, D1, E2, E4, E5, F2, F5, F6 | 10 |
| **Non tenu** | **D2**, **D3** | 2 |

\* D n'a que trois exigences : D1 partiel, D2 et D3 absents.

Et hors des 32, il manque des **livrables** qui comptent autant :
le rapport hybride unique, les réponses aux six questions du jury, et une
procédure de démarrage vérifiée.

Le socle n'est donc pas validé en l'état : D2 et D3 sont des exigences de
socle, et le cahier des charges est explicite sur ce point.
