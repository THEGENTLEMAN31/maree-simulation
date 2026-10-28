# MARÉE — foule et évacuation interprétative

> Monde 02 · Fête des Lanternes de Port-Aubel · esplanade du quai, 60 × 40 m.
> Soixante personnes, trois sorties, une fumée près de la scène.

MARÉE simule une évacuation de foule où **chaque agent se construit sa
propre croyance** sur la sortie à prendre. Le sujet n'est pas de savoir
si les gens courent vite : c'est de mesurer comment une croyance circule,
se déforme, et parfois piège la foule qui l'a adoptée.

---

## Ce que le projet démontre

| Question | Réponse mesurée |
|---|---|
| Peut-on simuler 60 agents ? | Oui. JuPedSim fait 60 agents × 100 s simulées en **0,06 s** → **1 761× le temps réel**. |
| Où est le coût ? | Uniquement dans l'appel LLM : **2,8 s** par décision. |
| Combien d'appels par run ? | **Quelques centaines**, pas 2 160 — parce qu'on ne décide que sur changement, et qu'un signal persistant ne déclenche qu'une fois. |
| Le run est-il rejouable ? | Oui, depuis le journal JSONL seul, sans LLM ni Kafka. |

---

## Démarrage

```bash
cp .env.example .env
make up          # Redpanda + Schema Registry + llama.cpp + simulateur
make index       # construit l'index RAG (bge-m3, 214 passages)
make run         # un run de démonstration
make replay      # rejoue le dernier run depuis le journal
make serve       # diffuse le run en WebSocket
make godot       # client de visualisation (Godot 4.4)
```

Sans GPU, sans Docker : `uv sync --all-extras && uv run pytest` exécute
toute la suite de tests (physique factice, population à règles), et
`make smoke` fait un run complet de 60 agents **sans aucun appel LLM**.

---

## Architecture en une page

Trois horloges, un seul état du monde.

```
       0,05 s            10,00 s              0,10 s
   ┌───────────┐     ┌──────────────┐     ┌───────────┐
   │  physique │     │   cognition  │     │   rendu   │
   │ JuPedSim  │     │  LangGraph   │     │   Godot   │
   └─────┬─────┘     └──────┬───────┘     └─────┬─────┘
         │                  │                   │
         └──────────┬───────┴───────────────────┘
                    ▼
            ┌───────────────┐
            │  journal JSONL│  ← source de vérité, append-only
            └───────┬───────┘
                    ▼
            ┌───────────────┐
            │ Redpanda      │  → Godot, chroniqueur, indicateurs
            └───────────────┘
```

**Le mouvement n'attend jamais la pensée.** JuPedSim avance à 20 Hz, les
agents réfléchissent toutes les 10 s simulées, et Godot interpole entre
deux instantanés. C'est ce découplage qui rend 60 agents tenables.

### Les trois moteurs

| Couche | Outil | Rôle |
|---|---|---|
| Foule | **JuPedSim 1.4** | `CollisionFreeSpeedModel` et `SocialForceModel` (Helbing & Molnár 1995) |
| Cognition | **LangGraph 1.2** | `recall → retrieve? → decide → validate` |
| Configuration | **Hydra 1.3** | tout paramètre en YAML, rien en dur |
| LLM | **SDK OpenAI** → llama.cpp | décisions, embeddings, récit |
| RAG | **FAISS** + bge-m3 | 214 passages, filtres profil/tick |
| Bus | **Redpanda** | diffusion temps réel, jamais persistance |
| Mesure | **scipy**, **DuckDB** | médianes, Mann-Whitney, agrégats |

### Ce qu'on n'utilise pas, et pourquoi

- **Mesa** : son ordonnanceur (`Model.run_until`) est synchrone et ne peut
  pas héberger un appel LLM asynchrone. L'utiliser aurait signifié le
  combattre. LangGraph couvre le besoin multi-agents, JuPedSim la physique.
- **LlamaIndex** : le corpus est déjà découpé en 214 passages annotés. Le
  seul traitement qui compte — le centrage sur la moyenne du corpus, qui
  fait passer la précision@1 de 0,17 à 0,73 — aurait dû être réécrit
  par-dessus l'abstraction. Voir `docs/architecture-v2.md`.

---

## Les cinq profils

Un profil n'est pas un caractère : c'est un **jeu de connaissances
initiales** et un contrat de décision.

| Profil | Sorties connues | Priorité |
|---|---|---|
| `securite` | A, B, C | évaluer, guider |
| `habitue` | A, B, C | éviter la foule |
| `famille` | A, C | retrouver un proche |
| `visiteur` | A | comprendre, suivre |
| `vendeur` | A, C | protéger son stand |

La ruelle B (1,5 m) n'est connue que de l'habitué. C'est le levier
narratif : **le savoir local sauve, l'ignorance piège**.

---

## Indicateurs

| ID | Mesure | Ce qu'elle dit |
|---|---|---|
| I1 | consensus | part de la croyance majoritaire |
| I2 | entropie | incertitude moyenne (0 = sûrs, 1 = perdus) |
| I3 | évacués | part des agents sortis |
| I4 | temps | durée d'évacuation |
| I5 | densité max | le goulot, en personnes/m² |
| I6 | écart | part des agents croyant en une sortie fermée |

I6 est l'indicateur central : la croyance partagée qui sauve à t10 et
piège à t40.

---

## Structure

```
configs/        Hydra : monde, population, run, expériences
src/maree/
  domain/       plan, horloges, croyances, intentions, événements
  ports/        les contrats (Protocol) — aucun import concret
  agents/       profils, déclencheurs, règles, graphe LangGraph
  memory/       mémoire épisodique cloisonnée
  metrics/      I1..I6
  narrative/    digest + chroniqueur + validateur
  engine/       boucle à trois horloges, rejeu
  adapters/     JuPedSim, llama.cpp, FAISS, JSONL, Redpanda
  cli.py        run | index | replay | report
tests/          domaine, cloisonnement, déterminisme, rejeu
godot/          client de visualisation
docs/           cadrage, hypothèses, architecture, résultats
```

## Documentation

- `docs/architecture-v2.md` — décisions, et ce qu'on a écarté
- `docs/hypotheses.md` — hypothèses préenregistrées H1..H7
- `docs/cadrage-maree.md` — cadrage du monde
- `AGENTS.md` — mémoire de chantier (pièges, mesures, conventions)
