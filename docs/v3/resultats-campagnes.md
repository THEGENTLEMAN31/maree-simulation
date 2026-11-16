# Résultats des campagnes v3 (2026-11-16)

_Mesures faites sur le dépôt, avec le serveur réel : `gemma4-e2b` sur 8081
(grand) et `qwen3-0-6b` sur 8082 (petit). Chaque chiffre ci-dessous vient
d'un run qui a tourné ; les JSON sont versionnés dans `runs/v3/`._

---

## 1. Divergence par la mémoire (mission 1)

Scénario : 4 visiteurs **identiques** ; à t2, deux reçoivent « B est
bloquée », deux « B est libre » ; à t10, la même fumée. Question : le choix
de sortie suit-il la mémoire personnelle ?

| config | `mem_acc` | appels | tokens | replis |
|---|---:|---:|---:|---:|
| règles | **1,00** | 0 | 0 | 0 |
| grand (e2b) | 0,50 | 8 | ~1 476 | 0 |
| petit (qwen) | 0,50 | 8 | ~1 476 | 0 |

**Lecture honnête.** Les règles suivent parfaitement le message ; les deux
LLM ignorent « B est libre » et retombent sur A (biais d'ancrage). Aucun
effet de taille. Résultat E1 recevable : *sur cette tâche, le LLM n'apporte
rien*.

## 2. Le même scénario avec un ordre public contradictoire

Scénario : mêmes messages personnels, mais la fumée de t10 s'accompagne de
« Veuillez évacuer par la sortie B ». La mémoire et l'ordre se contredisent.

| config | `mem_acc` | appels | tokens | replis |
|---|---:|---:|---:|---:|
| règles | 0,50 | 0 | 0 | 0 |
| grand | **1,00** | 8 | ~1 514 | 0 |
| petit | **1,00** | 8 | ~1 514 | 0 |

**Lecture honnête.** L'ordre public fait basculer les règles (tout le monde
va à B, y compris ceux qui « savent » B bloquée) ; les deux LLM arbitrent en
faveur de la mémoire. Le couple LLM > règles se retourne donc selon la
question posée. **Toujours aucun écart grand/petit sur la décision.**

> Piste consignée pour la suite : il faut une tâche où le petit modèle
> *ne peut pas* réussir par règle (mémoire + contradiction interne), pour
> chercher un écart de décision entre tailles. L'énergie, elle, sépare déjà
> les tailles (ci-dessous).

## 2bis. Le scénario qui sépare les tailles : la sortie bloquée

Les deux scénarios précédents laissent le défaut (aller à A) gagner : on ne
sait donc pas si un modèle *lit* sa mémoire ou s'il **applique une
position**. Ce scénario retire le défaut comme solution.

Quatre visiteurs identiques, qui connaissent A et B. À t2, deux apprennent
« la sortie A est bloquée », deux « la sortie B est bloquée » ; à t10, la
fumée, **sans annonce** (aucun ordre ne nomme de sortie). La bonne réponse
est de contourner la sortie crue bloquée : A01/A02 → B, A03/A04 → A.

Le défaut du moteur (A, la sortie la plus confiante à égalité) est **faux
pour la moitié des agents** : une politique qui répond « toujours A » ou
« la première de la liste » vaut **0,50 par construction**. Le banc est
rejoué sans GPU avec des stubs (`tests/v3/test_scenario_blocked.py`) : un
stub « toujours A » obtient 0,50, un stub qui lit `dangers` obtient 1,00.

| config | évite la bloquée | appels | tokens | replis |
|---|---:|---:|---:|---:|
| règles | **1,00** | 0 | 0 | 0 |
| grand (e2b) | **1,00** | 8 | 1 480 | 0 |
| petit (qwen) | **0,50** | 8 | 1 492 | 0 |
| grand **sans** `dangers` (ablation) | 1,00 | 8 | 1 444 | 0 |

5 graines, 5/5 identiques (monde fixe, température 0 : les graines testent la
stabilité, pas la variance).

**Lecture honnête.**

- C'est le **premier écart de décision mesuré entre les tailles** : 1,00
  contre 0,50, séparation parfaite. Le petit modèle choisit A pour les quatre
  agents — y compris ceux qui viennent d'apprendre que A est bloquée. Il ne
  lit pas la mémoire : il suit la position de la liste.
- **L'ablation corrige l'explication facile.** Retirer le champ `dangers` du
  prompt ne change rien au grand (1,00) : il ne s'appuie pas sur ce champ
  seul, mais sur `messages_recus`/`memoire` — le fait brut y figure. Dire
  « le grand lit `dangers` » aurait été faux ; ce qui est vrai, c'est qu'il
  **intègre un fait mémorisé** que le petit ignore.
- Le résultat ne dit pas que le petit est « mauvais » partout : sur les deux
  scénarios précédents il égalait le grand. Il dit où la taille compte :
  quand la décision exige de **croiser** un fait mémorisé avec l'état du
  monde, au lieu de suivre un ordre ou un défaut.


## 3. Temps : sync contre async (C5/O10)

| mode | `lag_max` | décisions | appels | tokens | consensus |
|---|---:|---:|---:|---:|---:|
| sync | **0** | 8 | 8 | 1 476 | 0,00 |
| async | **4** | 8 | 8 | 1 476 | 0,00 |

**Lecture.** Le mode asynchrone applique les décisions 4 ticks après leur
perception (latence déclarée du tier LLM), sans changer le résultat sur ce
scénario. Le lag est mesuré, pas supposé.

## 4. Énergie et temps mural par bras (E4/E5)

Même monde, même population (4 visiteurs + 2 habitués), même chronologie,
3 graines ; puissance `nvidia-smi` à 1 Hz, repos GPU soustrait.

| config | mural médian | appels | énergie totale | énergie active |
|---|---:|---:|---:|---:|
| règles | 0,03 s | 0 | 0,0001 Wh | 0,0000 Wh |
| hybride | 0,03 s | 0 | 0,0001 Wh | 0,0000 Wh |
| grand (e2b) | **5,72 s** | 11 | **0,1058 Wh** | 0,0834 Wh |
| petit (qwen) | **1,51 s** | 11 | **0,0256 Wh** | 0,0193 Wh |

**Lecture.** Le petit modèle fait **le même nombre d'appels** (même
politique) pour **4× moins d'énergie active** et **3,8× moins de temps
mural**. Comparé à décisions égales (§2), le petit coûte un quart ; comparé
à §2bis, où il se trompe une fois sur deux, il coûte un quart *et* décide
moins bien.

Le bras hybride ne déclenche aucun appel ici : la fumée et l'annonce sont
des cas que les règles traitent — l'hybride ne paie le LLM que sur
l'ambiguïté, ce qui est le comportement voulu.

---

## Ce que ces chiffres ne disent pas

- ils ne prouvent pas que le LLM est « meilleur » : sur §1 il est pire que
  les règles, sur §2bis il égale la règle et dépasse le petit ;
- l'écart de décision entre tailles (§2bis) est mesuré sur **un** scénario
  à quatre agents : il établit *où* la taille compte, pas une loi générale ;
- l'ablation ne dit pas *par quel champ* le grand gagne (il reste à 1,00
  sans `dangers`) — elle dit seulement que ce n'est pas ce champ seul ;
- l'énergie est une puissance moyenne intégrée (1 Hz), pas un compteur
  matériel ;
- une campagne multi-graines ne compare que des distributions : deux runs
  appariés au LLM ne sont pas identiques (ordre de batching), donc on
  agrège, on n'apparie pas.
