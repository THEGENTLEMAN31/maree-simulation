# MARÉE v3 — plan consolidé (au 2026-11-10)

> Document de pilotage unique. Il hérite **des décisions mesurées** des
> documents v1/v2 (`docs/cadrage-maree.md`, `docs/plan-socle.md`,
> `docs/stockage.md`, `docs/hypotheses.md`) et **n'en redécide pas**. Il
> consigne ce que la v3 y **ajoute** : LangChain (RAG), le réalisme
> (distance / vitesse / mouvement continu), et les contrats front maximaux.
>
> Régle d'or v3 : **réimplémenter le code, hériter les décisions.** On ne
> réutilise pas le code v2 ; on reprend les choix d'architecture déjà
> validés et mesurés.

---

## 1. Mission

Étudier le comportement d'agents **LLM** en évacuation de foule :

- chaque agent a une **mémoire générale partagée** (le monde, les annonces,
  les faits — via RAG) et une **mémoire personnelle différente** (ce qu'il a
  vécu, entendu, cru) ;
- on observe des **décisions différentes, logiques et mesurables**, et on
  relie chaque écart à sa cause de mémoire (reçu, épisode, confiance) ;
- on fait tourner des **LLM de tailles différentes** (petit local vs grand)
  et des agents à règles, pour voir ce que *la taille change* ;
- le comportement est **réaliste et émergent**, jamais prescrit.

---

## 2. Réalisme (ce que ça implique concrètement)

1. **Chaque agent a un profil complet** : traits cognitifs (risque, herding,
   impulsivité…) + **caractéristiques physiques** (vitesse de déplacement,
   mobilité, endurance/fatigue, seuils de stress).
2. **Le contexte spatial compte** : la perception intègre la **distance au
   danger** → la menace, la visibilité, la température montent quand on se
   rapproche du départ de feu. On ne réagit pas pareil à 40 m et à 5 m de la
   flamme.
3. **Pas de téléportation** : le déplacement est **continu et visible**, par
   un **vrai moteur** (JuPedSim). Le moteur n'exécute que des **intentions**
   (frontière boucle rapide / boucle lente) : le corps bouge à chaque pas,
   le LLM met à jour l'intention quand il a fini de réfléchir.
4. **Le monde ne s'arrête jamais pour le LLM** : exécution asynchrone
   (mode réaliste) ; le mode synchrone est un contrôle, pour comparer
   (C4/C5).
5. **Hétérogénéité émergente** : deux agents différents réagissent
   différemment parce que leurs caractéristiques, leur mémoire et leur
   situation diffèrent — **jamais** une contrainte « pour faire varier ».

---

## 3. Mémoire (la pièce centrale)

- **Partagé = candidats** (RAG), **personnel = crédence**. Le partagé
  propose des faits ; l'agent y applique son **encodeur** (valuation de la
  source, prior, biais de confirmation) avant d'y croire.
- **Registre audit** (type event-sourcing) : chaque `observe / learn /
  consolidate / forget / rearm` est journalisé → la mémoire d'un agent se
  rejoue à l'identique à tout tick (service à A1 « plusieurs jours simulés »).
- **Préhistoire J−3** (héritée) : échanges datés en tick négatif, mémorisés
  avec l'émetteur ; la récence a un **plancher** pour les souvenirs anciens
  mais saillants.
- **Divergence** : les jumeaux de même archétype et même connaissance
  partagée, à mémoires personnelles différentes → **décisions différentes,
  expliquées par les reçus** ; **ablation** (mémoire off → divergence nulle).
- **Contre-factuel d'attribution** : rejouer en retirant un reçu → la
  décision bascule-t-elle ? (`flippability`) — la preuve « c'est ce message
  qui a inversé B14 ».

---

## 4. Architecture (héritée + ajouts v3)

### Hérité des décisions mesurées (à respecter, pas redécider)

| Brique | Décision |
|---|---|
| **Journal** | JSONL **append-only**, source de vérité, rejeu sans LLM ni broker (E3) |
| **Kafka/Redpanda** | **bus de diffusion** best-effort (C1), jamais la persistance |
| **Historique** | JSONL interrogé par **DuckDB** (F5) ; pas de serveur |
| **Base de connaissances** | **FAISS exact + JSON + `mean.npy`**, embeddings **bge-m3** (pooling CLS, correction d'anisotropie) |
| **Stockage** | **Pas de Postgres, pas de Parquet, pas de Chroma** (chacun ajouterait un service sans changer le besoin d'accès) |
| **Mouvement** | **JuPedSim** ; le moteur n'exécute que des intentions |
| **Temps** | horloge simulée, `t_prod`/`t_trait`/`t_real`, modes sync/async |
| **Godot** | consommateur **pur** du flux (D1) |
| **Granularité événements** | un événement par fait, instantané agrégé/seconde, pas un message/agent/pas |

### Ajouts v3

| Brique | Choix v3 |
|---|---|
| **RAG** | **LangChain** : `FAISS` vectorstore + `VectorStoreRetriever` + `ChatPromptTemplate`, filtré par **cohérence temporelle (C6)** et **profil** avant injection. La mémoire personnelle reste déterministe (rejeu). |
| **Réalisme spatial** | champ fumée/feu grossier `hazard(distance)` ; vitesse/mobilité par agent ; perception distance-aware. |
| **Contrats front maximaux** | enveloppe d'événement **auto-descriptive** (type + refs + `payload` libre), **dossier agent « superset »** (bio, croyances, reçus, décisions, trajectoire, ops de mémoire), IDs stables partout, **assets à la main du front**. |
| **Observabilité** | indicateurs d'émergence calculés pendant le run (B2), `E_social = consensus − consensus_à mémoires brouillées` (B3) — la ressemblance du modèle est le **null** ; coût/sobriété mesurés en direct. |

---

## 5. Passage de temps : flux d'un tick

```
événements du monde (t_prod = T, figé)
  → enveloppe (run_id, seq, type, schema_version, t_prod, t_trait, causation_id)
  → perception figée (un instant T pour tous)
  → appraisal PADM (menace distance-aware)
  → mémoire : recall(now) + registre, filtré par C6 (rien de t_prod > now)
  → politique : rules | hybrid | llm_small | llm_big
  → (si LLM) RAG LangChain → bloc « contexte » dans le prompt
  → décision (intention)
  → écriture mémoire (épisode + reçu + réarmement)
  → diffusion des messages (après toutes les décisions)
  → indicateurs d'émergence
  → snapshot (état dérivé) → chroniqueur (omniscient, stérile)
```

Le moteur de déplacement tourne **en continu** (pas de temps fixe) ; il lit
l'intention courante de chaque agent. En asynchrone, l'intention change
quand la réponse LLM arrive ; en synchrone, tous décident au même pas.

---

## 6. Programmes expérimentaux (hypothèses, plans)

**Hypothèses**
- **H1** — sous signal clair, petit et grand convergent ; sous ambiguïté/contradiction, le grand intègre mieux la mémoire, le petit est plus persuasible et sensible à la position.
- **H2** — à perception identique, deux mémoires personnelles différentes → des choix différents (KL > 0), chez les agents à règles **et** chez les LLM.
- **H3** — la mémoire partagée homogénéise ; la mémoire personnelle polarise.
- **H4** — une rumeur précoce produit une **cascade** (hystérésis) qui survit à un démenti tardif.
- **H5** — le démenti corrige la *croyance* mais pas le *comportement déjà engagé*.
- **H6** — l'émergence sociale est plus forte chez le petit modèle que chez le grand.

**Plans**
- **A — micro cognitif** : banc de situations calibrées (rappel, mise à jour, résistance au faux souvenir, contradiction, sensibilité à la source, interférence, biais de position). Le meilleur rapport information par appel.
- **B — jumeaux + contrefactuels** : divergence KL (on/off mémoire), `flippability` d'un reçu.
- **C — société + perturbations** : rumeur, démenti tôt/tard, backfire, oubli ; mesure `E_social`, chambres d'écho, hystérésis.

**Budget** : preuves déterministes à **0 appel** d'abord (divergence en `rules`), puis ≥5 runs × ≥2 configs, graines agrégées (jamais 2 runs appariés), robustesse comptée (sortie de rôle, muet, replis par cause).

---

## 7. Découpe de portée (pour éviter la sur-ingénierie)

**Doit (Socle + profondeur)**
- Mémoire partagée/personnelle + agents réalistes (vitesse, distance→menace) + LLM petit/grand + règles.
- Boucle temps réel : physique continue, décisions asynchrones.
- RAG **LangChain** + bge-m3 + FAISS ; Kafka (bus) ; journal/rejeu ; DuckDB (pas de Postgres/Parquet).
- Contrat front maximal + indicateurs d'émergence (`E_social` avec null).
- Une campagne de preuve (≥5×2) + coût/sobriété.

**Stretch (seulement si le temps le permet)**
- Monde génératif multi-étages étendu (d'abord 2–3 configurations paramétrées).
- Excellence : chambres d'écho fines (B4), C7 (lag sous charge), C8 (2 tailles de foule).

**Écarté** : IFC, procédural avancé, Postgres/pgvector, Pareto de variantes.

---

## 8. Phases de construction

| Phase | Livrable | Preuve |
|---|---|---|
| **P0** | mémoire (schema + registre + J−3) + agent réaliste (caractéristiques, distance, memorandum dans le prompt) + flux sync rejouable | jumeaux qui divergent, ablation, `flippability` |
| **P1** | monde génératif paramétré (2–3 configs) + RAG LangChain réel | F2 (pertinence), C6 filtré |
| **P2** | Kafka (bus) + stockage (DuckDB) + indicateurs d'émergence | C1, B2/B3, E3 |
| **P3** | sync/async + cohérence temporelle (C6) + mouvement continu visible | C3/C4/C5/C7 |
| **P4** | contrat API/Godot (dossier superset, injections) + assets libres | D1/D2/D3 |
| **P5** | campagne (≥5×2) + coût/sobriété + rapport | E1–E5, F5/F6 |

Règle de coupe : si un jalon prend trop, on gèle le stretch et on protège le
Socle et la profondeur mémoire/réalisme.

---

## 9. Correspondance avec le défi commun

Reprise de `docs/plan-socle.md` : les 32 exigences A→F gardent leur
emplacement et leur preuve. La v3 **réimplémente** ces preuves (code neuf)
en ajoutant LangChain (F1/F2), le réalisme (A1/A5/physique), l'émergence
robuste (B2/B3) et des contrats front maximaux (D1/D2/D3). L'état de
cohérence détaillé, exigence par exigence, vit dans `docs/plan-socle.md`
(à re-basculer sur le code v3 au fil des phases).