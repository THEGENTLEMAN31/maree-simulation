# Rapport v3 — moteur, mesures, limites

_Ce document se lit seul. Il dit ce qui tourne, ce qui est mesuré, ce qui ne
l'est pas, et ce qui reste à faire. Les chiffres détaillés sont dans
`docs/v3/resultats-campagnes.md`._

---

## 1. Mission

La v3 change de question par rapport à la v2 :

> **Mission 1 — le comportement.** Deux agents du même archétype doivent
> **diverger** parce que leur **mémoire personnelle** diffère.
> **Mission 2 — l'aide à la conception** (sorties, feux, variantes), secondaire.

La v2 comptait des sorties ; la v3 doit expliquer des choix.

---

## 2. Ce qui tourne aujourd'hui

```text
WorldSpec généré ──► validation ──► graphe de navigation ──► artefact (spawn)
                                                        │
                    ┌───────────────────────────────────┘
                    ▼
      Simulation (tick entier, perception figée)
        ├─ agents : traits, mémoire, croyances, appréciation
        ├─ politiques : règles | hybride | LLM (grand/petit)
        ├─ physique : JuPedSimCrowd (mouvement réel)
        └─ bus + journal : chaque décision et chaque événement
                    │
     ┌──────────────┼───────────────────┐
     ▼              ▼                   ▼
  journal JSONL   bus (mémoire/Kafka)  WS (P4)
  rejeu sans LLM   trames live         client Godot
```

Points tenus par du code et des tests (suite `tests/v3`) :

| Exigence | État |
|---|---|
| Le journal est la source de vérité | `write_run` écrit en-tête + **flux complet** ; `replay` le relit |
| Rejeu sans LLM | `make v3-replay-demo` — aucune importation de port de chat |
| Temps simulé, jamais l'horloge | `tick` entier ; `t_prod`/`t_trait` dans chaque enveloppe |
| Sync et async | `ExecutionMode` ; lag mesuré (0 en sync, 4 en async) |
| Perception figée, ordre canonique | décisions appliquées par `agent_id` croissant |
| Émergence mesurée pendant le run | `indicator.emergence` à chaque tick |
| Incidents tracés et dénombrés | `agent.incident` + `indicator.incidents` par cause |
| Schémas versionnés | `schema: maree.event/1.0` sur chaque trame |
| Contrat front | trames WS, dossier agent étiqueté, injections au tick suivant |
| Campagnes multi-graines | `verify/campaign.py` + scripts `v3_campaign*` |
| Énergie | `scripts/v3_energy.py` (nvidia-smi 1 Hz, repos soustrait) |

---

## 3. Les mesures (résumé)

1. **Divergence par la mémoire** : les règles suivent le message personnel à
   100 % ; les deux LLM à 50 % (ils ignorent « B est libre »). Le LLM perd.
2. **Ordre public contradictoire** : l'annonce « évacuez par B » fait suivre
   les règles (0,50), les deux LLM arbitrent pour la mémoire (1,00). Le LLM
   gagne — sur une autre question.
3. **Grand contre petit, en décision** : aucun écart mesuré sur ces deux
   scénarios. C'est une tâche ouverte, pas un résultat caché.
4. **Énergie** : à nombre d'appels égal, le petit modèle coûte **4× moins**
   d'énergie active (0,0256 Wh contre 0,1058 Wh) et **3,8× moins** de temps
   mural. C'est le seul axe où la taille se voit dans nos mesures.
5. **Hybride** : ne déclenche le LLM que sur l'ambiguïté — zéro appel sur une
   fumée ou une annonce claire.

---

## 4. Limites, dites franchement

- **Pas d'écart grand/petit en décision** sur nos deux scénarios. Il faut une
  tâche où le petit ne peut pas réussir par règle — piste consignée dans
  `resultats-campagnes.md`.
- **Le client Godot n'est pas dans ce dépôt** : il est fait par une autre
  personne ; ici on livre le **contrat** (trames, dossier, injections) et un
  serveur qui tourne.
- **L'énergie** est une puissance moyenne intégrée à 1 Hz, pas un compteur
  matériel.
- **La reproductibilité LLM** n'est pas exacte : deux runs identiques ne
  prennent pas les mêmes décisions (batching). On agrège des graines, on
  n'apparie pas deux runs.
- **La calibration humaine** (« ça a l'air crédible ? ») reste un jugement,
  pas une mesure : c'est la soutenance, pas le code.

---

## 5. Démo en cinq commandes

```bash
uv sync --all-extras
uv run pytest                                   # toute la suite, sans GPU
make v3-replay-demo                             # E3 : rejeu sans LLM
make v3-llm-up                                  # grand modèle sur 8081
make v3-serve                                   # WS sur 8766 (règles + JuPedSim)
```

Puis, avec le client (ou `websocat ws://127.0.0.1:8766`) :

```json
{"type": "inject", "kind": "smoke"}
{"type": "agent", "agent": "A01"}
```

Pour les campagnes (serveurs requis) :

```bash
uv run python scripts/v3_campaign_divergence.py 1 2 3 4 5
uv run python scripts/v3_campaign_discriminant.py 1 2 3 4 5
uv run python scripts/v3_campaign_time.py 1 2 3
uv run python scripts/v3_energy.py --seeds 1 2 3
```

---

## 6. Pour la personne qui écrit le client

Le contrat est `docs/v3/donnees-et-api.md` §5 et §10. Ce qu'il faut savoir :

- se connecter sur `ws://127.0.0.1:8766` ; la première trame est `hello`
  (run, monde, hash, capacités), puis `world` (géométrie) et, si on arrive en
  cours de run, le dernier `snapshot` ;
- le flux : `decision`, `snapshot`, `hazard`, `message`, `evacuated`,
  `indicators`, `incident`, `event` (tout ce qui n'a pas de trame dédiée),
  et `end` en dernier ;
- envoyer `{"type":"inject","kind":"smoke"}` (ou `announcement` avec `text`,
  ou `message` avec `agent` + `text`) : le serveur répond `ack` puis applique
  au tick suivant ;
- demander un dossier : `{"type":"agent","agent":"A01"}` → trame
  `agent_dossier` étiquetée `measured` / `derived` / `generated` ;
- accepter **100 Ko par trame** (instantanés) et lire `schema` pour négocier.

---

## 7. État

- Branche `main`, arbre propre, tout poussé.
- `uv run pytest` : toute la suite passe (v2 + v3).
- `ruff` et `mypy` propres sur `src/maree/v3`.
- Serveurs de mesure : `gemma4-e2b` (8081) et `qwen3-0-6b` (8082),
  sur la RTX 3050 (4 Go), à arrêter quand ils ne servent plus.
