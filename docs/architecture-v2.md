# Architecture v2 — décisions et mesures

_Ce document remplace la v1. Il explique ce qui tourne, pourquoi, et ce
qui a été écarté **avec la mesure qui a motivé l'abandon**._

Date : 2026-10-28

---

## 1. Le problème que la v1 n'avait pas résolu

La v1 simulait 60 agents, mais chaque agent décidait à chaque tick :

```
60 agents × 36 ticks = 2 160 appels LLM par run
débit mesuré du routeur : 0,36 décision/s (parallel=1)
→ 6 000 s, soit 1 h 40 de calcul pour 6 min simulées
```

Ce n'était pas un problème de modèle. C'était un problème de **fréquence
de décision**. Une foule ne réfléchit pas vingt fois par seconde, et
surtout : elle ne réfléchit pas *en même temps*.

## 2. La réponse, en trois chiffres mesurés

| Mesure | Valeur | Où |
|---|---|---|
| Physique, 60 agents × 100 s simulées | **0,06 s** mural → **1 761×** temps réel | `spike4` |
| Physique, `SocialForceModel` | 0,07 s → **1 353×** temps réel | `spike4` |
| Déterminisme JuPedSim (12 agents, 200 pas) | positions identiques à **1e-9** | `spike4` |
| Un appel LLM | **2,8 s** | v1 |
| Débit, `parallel=4` | **1,43 décision/s** | v1 |

**Conclusion : la foule ne coûte rien. Seul le LLM coûte.** Toute
l'architecture en découle.

Trois leviers, appliqués ensemble :

1. **Décisions événementielles** — on ne décide que sur changement
   (fumée, message, sortie fermée, densité, filet périodique).
   Les signaux **persistants** (fumée visible, annonce, sortie fermée)
   sont traités en **front**, une fois par agent : sinon la fumée, qui
   reste visible jusqu'à la fin, redéclencherait 60 décisions par tick.
   Mesuré sur le scénario du piège (90 ticks, 60 agents à règles) :
   **271 décisions** au lieu de 2 160 — dont 132 par le filet
   périodique, parce que 6 agents restent piégés jusqu'au bout.
2. **Population hybride** — 12 agents LLM, 48 agents à règles. Les
   seconds ne coûtent rien et servent de référence (X4).
3. **`parallel = 4`** dans llama.cpp — 1,43 décision/s, suffisant pour
   une pointe de 4 appels simultanés.

> 60 agents × 90 ticks, 12 agents LLM qui décident ~5 fois chacun :
> ~60 appels × 2,8 s / 4 en parallèle ≈ **45 s de calcul** pour 15 min
> simulées. Contre 1 h 40 en v1.

### La phase d'avant

Une foule ne s'évacue pas parce qu'elle est arrivée. Sans fumée, sans
annonce, sans message, les agents **restent** : c'est ce qui donne au
scénario sa phase « avant » et ce qui rend la fumée de t10 causale.
Sans cette règle, les 60 agents quittaient l'esplanade au tick 1 et la
fumée ne commentait plus qu'une évacuation déjà finie.

## 3. Trois horloges

```
physique    0,05 s   JuPedSim : positions, contacts, files
cognition  10,00 s   LangGraph + LLM : décision, RAG, mémoire
rendu       0,10 s   Godot : interpolation
```

Le mouvement n'attend jamais la pensée. Un agent qui réfléchit pendant
2,8 s de temps réel continue d'avancer pendant ce temps : c'est ce qui
produit des trajectoires crédibles malgré un LLM lent.

**Perception figée** : tous les agents perçoivent le même instant T, même
si leurs décisions arrivent à des moments différents. Sans cela, un agent
qui décide en dernier verrait un monde que les autres n'ont pas vu.

## 4. Déterminisme — quatre règles

Le déterminisme n'est pas un luxe : c'est la condition du rejeu (E3).

1. **Aucune horloge système** dans la logique du monde. Le temps est un
   entier (`tick`). `t_real` existe, mais uniquement pour le journal.
2. **Graine dérivée par SHA-256**, jamais `hash()` : le hash de Python
   est salé par processus (`PYTHONHASHSEED`), donc deux runs identiques
   divergeraient. C'est un piège silencieux, et il a été corrigé.
3. **Ordre canonique** : les décisions sont appliquées par `agent_id`
   croissant, jamais dans l'ordre d'arrivée des réponses LLM.
4. **Aucun tirage non semé** : le spawn utilise un `random.Random(seed)`
   unique, jamais le module global.

Preuve : `tests/test_simulation.py::test_deux_runs_de_meme_graine_sont_identiques`
compare l'empreinte SHA-256 de la série d'indicateurs.

## 5. Le journal est la source de vérité

`runs/<run_id>/events.jsonl`, append-only, une ligne par événement.

Chaque événement porte :

```
seq             ordre canonique (le tri suffit)
t_prod          tick de production
t_trait         tick de traitement
t_real          temps mural (journal seulement)
causation_id    quel événement l'a causé
schema_version  compatibilité
```

**Un run_id n'est jamais réutilisé.** Le journal étant en append, réutiliser
un identifiant mélangerait deux runs — c'est une erreur, pas un détail.
`JsonlJournal.last_seq()` le détecte.

Le bus (Redpanda) sert à la diffusion temps réel. **Si Kafka tombe, le run
reste rejouable** : c'est la différence entre un journal et une file.

## 6. Rejeu (E3)

`maree replay --run-id <id>` ne fait aucun appel réseau. Il :

- reconstruit chaque décision en re-parsant la sortie brute et vérifie que
  l'intention appliquée est bien celle du modèle ;
- recalcule l'empreinte des indicateurs ;
- réaffiche le récit du chroniqueur sans rappeler le modèle.

Un journal incomplet (`run.ended` absent) est refusé, pas « réparé ».

## 7. Mémoire : le cloisonnement est vérifié

Chaque agent a trois mémoires : épisodique (ce qu'il a vu/entendu/dit),
sémantique (ses croyances), sociale (sa confiance envers les autres).

La garantie centrale :

```
recall("A19", …) ne peut jamais retourner un épisode d'un autre agent.
```

Elle est testée **par propriété** (`hypothesis`, 50 exemples), pas par un
exemple choisi. L'accès global (`read_all`) est réservé au narrateur et à
l'analyste ; un agent qui l'appelle lève `PermissionError`.

Sans cette garantie, un visiteur « saurait » ce qu'un habitué sait, et
l'expérience ne mesurerait plus la circulation d'une croyance mais la
diffusion d'une réponse unique.

## 8. Le chroniqueur est omniscient et stérile

```
lit      tout : événements, croyances de tous, densités, indicateurs
écrit    narrative.generated, et rien d'autre
jamais   aucun agent ne s'abonne à sa sortie
```

Sans cette isolation, il deviendrait un oracle. Les agents apprendraient
par lui, et le monde n'aurait plus besoin d'être exploré.

Garde-fou anti-hallucination : le texte est validé contre le digest. Toute
sortie inventée (« sortie D ») ou tout nombre absent du digest est refusé,
et le gabarit de repli est publié avec l'incident journalisé.

**Limite assumée** : le validateur lit les chiffres, pas les mots.
« Quarante-deux » passe. On l'écrit plutôt que de prétendre à une
vérification sémantique qu'on ne fait pas.

## 9. RAG : pourquoi le centrage n'est pas délégué

bge-m3 produit des embeddings **anisotropes** : tous les vecteurs
s'alignent dans un cône étroit, et la similarité cosinus ne discrimine
plus. Mesuré en v1 : précision@1 de **0,167** sans correction, **0,733**
après centrage sur la moyenne du corpus.

C'est le seul traitement qui compte. Le déléguer à une abstraction
générique aurait signifié le réécrire par-dessus. D'où : FAISS exact
(215 passages, 0,9 Mo — un index approximatif serait plus lent à charger
qu'à interroger) + numpy, et pas de couche d'ingestion.

Filtrage (décision 15) : un agent ne lit que les collections de son profil
et les passages disponibles à son tick simulé.

## 10. Ce qu'on n'utilise pas, et pourquoi

### Mesa

Inspecté en spike (3.5.2). `Model` fournit bien `schedule_event`,
`schedule_recurring` et `run_until` — mais `run_until` est **synchrone**.
Un gestionnaire d'événement ne peut pas `await` un appel LLM de 2,8 s.
L'utiliser aurait signifié soit bloquer la boucle, soit faire tourner deux
ordonnanceurs en parallèle.

LangGraph couvre la cognition multi-agents, JuPedSim la physique. Mesa
aurait été une troisième couche sans emploi. **On ne garde pas un
framework pour la vitrine.**

### LlamaIndex

Le corpus est déjà découpé en 215 passages annotés (front matter :
collection, `available_tick`, `allowed_profiles`, importance). Il n'y a
rien à ingérer ni à découper. Le seul traitement qui compte est le
centrage (§9).

### Vector DB

0,9 Mo de vecteurs. Une base vectorielle serait de l'infrastructure pour
un fichier qui tient en mémoire.

### 3D

Le sujet est la croyance, pas le rendu. Godot en `gl_compatibility`, vue
de dessus, une police. Le plan vient du YAML, il n'est pas dupliqué en
GDScript (défaut de la v1).

## 11. Ports et adaptateurs

Le domaine ne connaît aucun outil. Tout passe par des `Protocol` :

| Port | Aujourd'hui | Demain |
|---|---|---|
| `CrowdPhysics` | JuPedSim | autre moteur |
| `LLMPort` | llama.cpp | API distante |
| `RetrieverPort` | FAISS + bge-m3 | autre index |
| `JournalPort` | JSONL | Parquet |
| `EventBus` | Redpanda / mémoire | autre bus |
| `MemoryPort` | projection du journal | autre store |

Conséquence concrète : les tests d'intégration tournent **sans GPU, sans
JuPedSim, sans Kafka**, avec une physique factice et une population à
règles. C'est ce qui permet de vérifier le déterminisme en 2 s.

## 12. Limites assumées

- **Le suivi d'agent** (`FOLLOW`) vise la position du meneur au moment de
  la décision, pas en continu. Un suiveur re-décide au déclencheur suivant.
- **La fermeture d'une sortie** ne détruit pas l'issue dans JuPedSim
  (l'API ne le permet pas proprement) : les agents sont redirigés vers un
  point d'arrêt 1,5 m à l'intérieur. Ils s'y accumulent — comportement
  réaliste, mais ce n'est pas une barrière physique.
- **Les zones de spawn** diffèrent par profil, ce qui confond légèrement
  l'effet du savoir dans X6. Noté dans le protocole plutôt que masqué.
- **Le narrateur** est validé sur les chiffres et les sorties, pas sur le
  sens.
