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
mural**. C'est le seul axe où la taille se voit dans nos mesures — et il
compte : à décisions égales (§2), le petit coûte un quart.

Le bras hybride ne déclenche aucun appel ici : la fumée et l'annonce sont
des cas que les règles traitent — l'hybride ne paie le LLM que sur
l'ambiguïté, ce qui est le comportement voulu.

---

## Ce que ces chiffres ne disent pas

- ils ne prouvent pas que le LLM est « meilleur » : sur §1 il est pire que
  les règles, sur §2 il est meilleur ;
- ils ne séparent pas grand et petit **en décision** : deux scénarios ont
  échoué à le faire, et c'est consigné comme tâche ouverte, pas contourné ;
- l'énergie est une puissance moyenne intégrée (1 Hz), pas un compteur
  matériel ;
- une campagne multi-graines ne compare que des distributions : deux runs
  appariés au LLM ne sont pas identiques (ordre de batching), donc on
  agrège, on n'apparie pas.
