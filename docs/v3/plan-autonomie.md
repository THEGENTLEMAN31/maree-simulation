# Plan d'autonomie — mener la v3 à son terme

_Ouvert le 2026-11-22. Ce fichier est le contrat de travail autonome : ce que
je fais, dans quel ordre, ce que je tranche seul, ce qui m'arrête, et comment
on vérifie que c'est fini. Il est mis à jour à chaque porte franchie._

---

## 1. Définition de fini

Le projet est terminé quand **ces onze points sont vrais**, chacun avec une
commande rejouable :

1. **Mission n°1 mesurée après correctifs** : deux agents du même archétype
   divergent par leur mémoire personnelle — chiffre, graines, test.
2. **Mémoire J−3 réellement amorcée** en run (pas seulement testée à l'unité).
3. **Proches (`famille`) réellement assignés** : `CHERCHER_PROCHE` se
   déclenche pour de vrai.
4. **Compteur de croyance non ambigu** : on sait si l'agent visait une porte
   qu'il croyait bloquée *au moment de décider*.
5. **Résultat négatif refait sur ≥ 10 graines** avec test apparié et
   intervalles.
6. **Échantillon multi-mondes** (≥ 5 géométries) recalibré.
7. **Fermeture d'issue en foule** : I6 bouge, réacheminement mesuré.
8. **Démenti tardif (H5)** mesuré.
9. **Deux tiers en foule + courbe ε** : la sobriété cesse d'être une intention.
10. **Contrat client à jour + test WS de bout en bout** (pas de Godot).
11. **`AGENTS.md` v3, rapport réécrit, HANDOFF, cibles `make`** : quelqu'un
    d'autre peut reprendre sans me parler.

« Et plus » : un brouillon d'article court (non publié), et un journal
d'autonomie lisible.

---

## 2. Règles d'autonomie

### Ce que je tranche seul

- toute décision technique : ordre des opérations, définition d'un indicateur,
  granularité du tick, format de journal, nommage ;
- toute décision de méthode : nombre de graines, seuils de calibration,
  protocole d'ablation, choix de modèle — **à condition** de pré-enregistrer
  le critère avant de mesurer ;
- réécrire un rapport quand une mesure le contredit (la mesure gagne) ;
- archiver, renommer, consolider, refactorer, tester, pousser sur `main`.

### Points d'arrêt (je m'arrête et je demande)

1. **Publication hors du dépôt** (article, mail, dépôt externe).
2. **Suppression** de travail existant que je n'ai pas produit (docs, JSON
   archivés, texte de l'utilisateur).
3. **Conclusion présentée comme acquise alors qu'elle ne tient qu'à un
   modèle ou à un monde** — je préfère écrire la réserve.
4. **Doute sur la sécurité des données** (la clé, un fichier personnel).

### Budgets que je m'impose

| ressource | règle |
|---|---|
| GPU | je lis `nvidia-smi` **avant** chaque job ; jamais de `kill` ; si l'utilisateur utilise la carte, je passe au CPU ou au travail sans GPU ; 100 % quand c'est libre |
| disque | code et venv sur `/` (24 Go libres) ; **téléchargements sur `/mnt/data/maree-models`** (121 Go libres) |
| RAM | 27 Go disponibles : un modèle en RAM autorisé pour **une** expérience bornée, pas une campagne |
| quota Gemini | `gemini-3.5-flash-lite` : 15 req/min, **500/jour** → jamais un run complet ; `gemma-4-26b-a4b-it` : vision et analyses ponctuelles ; la clé n'est **jamais** lue ni affichée |
| temps | tout job long écrit son JSON par lot (reprenable) ; commit après chaque porte |

---

## 3. Les phases

Chaque phase finit par une **porte** : je ne passe pas à la suivante si la
condition n'est pas tenue.

### Phase 0 — Instrumentation honnête (bloquants) · porte A

- **P0.1** Journaliser la croyance **au moment de décider** :
  `belief_blocked_at_decision` sur chaque ligne. Le compteur actuel
  (« porte désignée bloquée à t1 ») ne distingue pas « se trompe » de « ne
  croit plus que c'est fermé ».
- **P0.2** Amorcer la mémoire J−3 (`prehistory=True`) dans les runs, et
  l'exposer dans `Simulation`.
- **P0.3** Assigner les proches (`famille`) par paires au spawn, à portée de
  vue, pour que `CHERCHER_PROCHE` existe en run.
- **P0.4** Rejouer la **mission n°1** : jumeaux à mémoire contrôlée sur le
  monde calibré, divergence mesurée (KL + accord + première décision).
- **Porte A** : mission n°1 a un chiffre reproductible ; le compteur de
  croyance est non ambigu ; 397+ tests verts.

### Phase 1 — Solidité statistique · porte B

- **P1.1** 10 graines sur 3 bras (`regles`, `hybride`, `llm_grand`) sur les
  deux scénarios, avec test apparié par graine (Wilcoxon) et intervalles
  bootstrap.
- **P1.2** Échantillon multi-mondes : ≥ 5 géométries de même distribution,
  bande I5 recalibrée, résultats par monde puis agrégés.
- **P1.3** Pré-enregistrement écrit **avant** chaque campagne (critère
  principal, N, sens attendu).
- **Porte B** : chaque affirmation du rapport a un test, un N, un intervalle.

### Phase 2 — Comportements manquants · porte C

- **P2.1** Fermeture d'issue à 60 agents : I6 bouge, réacheminement mesuré.
- **P2.2** Démenti tardif (H5) : la croyance se corrige, l'action engagée non.
- **P2.3** Deux tiers en foule (visiteurs sur petit, habitués sur grand).
- **P2.4** Courbe ε ∈ {0 ; 0,25 ; 0,5} sur un bras.
- **P2.5** Énergie remesurée (le script v3 existe, il n'a pas tourné depuis
  la refonte).
- **P2.6** Ablation des critères d'escalade, un par un.
- **Porte C** : chaque comportement déclaré a un run et un chiffre.

### Phase 3 — L'espace des modèles · porte D

- **P3.1** Bras `decision_head` : tester les candidats (modèle de décision
  local si trouvable, `gemini-decision-1`, ou un petit modèle contraint par
  logprobs). Critère : probabilité calibrée sur un ensemble fermé, sans
  génération de texte.
- **P3.2** Un modèle plus gros en RAM (7–12 B quantifié), **expérience
  bornée** : la conclusion négative tient-elle à la taille ?
- **P3.3** Bras « seuls les gardes parlent » : séparer parole et rumeur.
- **Porte D** : on sait si « le modèle ne trie pas la rumeur » vaut pour la
  taille, la famille, ou seulement pour les petits modèles embarqués.

### Phase 4 — Contrat et intégration · porte E

- **P4.1** `docs/v3/donnees-et-api.md` à jour : `agent.message`,
  `agent.escalation`, `agent.reconsider`, `indicator.crowd`,
  `world.exit_closed`, `target_resolved`, `target_least_bad`.
- **P4.2** Test WS de bout en bout en v3 (connexion, `hello`, snapshot,
  injection, dossier agent, fin propre).
- **P4.3** **Pas de Godot**, pas d'assets : seulement le contrat.
- **Porte E** : un client peut afficher la parole et les indicateurs sans lire
  le moteur.

### Phase 5 — Mémoire et livraison · porte F

- **P5.1** `AGENTS.md` v3 : les leçons à ne pas repayer (calendrier,
  perception figée, croyance avant décision, débit de porte, null exécuté).
- **P5.2** Rapport réécrit avec les résultats de P1–P3, y compris ce qui
  contredit la version du 18 novembre.
- **P5.3** `HANDOFF.md` + cibles `make` (une commande par affirmation).
- **P5.4** Brouillon d'article (dans le dépôt, **non publié**).
- **Porte F** : les onze points de §1 sont vrais et rejouables.

---

## 4. Ordre de bataille (ce que je fais maintenant)

1. P0.1 (journaliser la croyance) — sans ça, tout le reste est ambigu.
2. P0.2 + P0.3 (mémoire J−3, proches) — sinon la mission n°1 est vide.
3. P0.4 (mesurer la divergence) — le chiffre qui manque au rapport.
4. Puis P1 : graines + multi-mondes, en profitant du GPU quand il est libre.

---

## 5. Journal des décisions autonomes

| date | décision | pourquoi | conséquence |
|---|---|---|---|
| 2026-11-22 | Plan d'autonomie ouvert ; priorité aux blocants P0 avant toute nouvelle mesure | deux des trois résultats publiés reposent sur une mission non remesurée et un compteur ambigu | rien n'est publié avant la porte A |
| 2026-11-22 | Modèles cloud classés par usage, pas par préférence : flash-lite pour l'analyse (500/j), gemma-26b pour la vision, `gemini-decision-1` candidat `decision_head` | quotas réels mesurés ; `gemma-4-31b-it` renvoie 503 | aucune campagne ne dépend d'un quota cloud |
| 2026-11-22 | Téléchargements sur `/mnt/data/maree-models`, code sur `/` | `/` à 89 %, `/mnt/data` à 88 % avec 121 Go libres | les gros fichiers ne saturent pas le disque système |
| 2026-11-22 | La préhistoire écrit des **croyances**, pas seulement des reçus | sinon elle n'influence que le prompt du grand modèle et reste décorative pour les règles | mission n°1 mesurable |
| 2026-11-22 | Jumeaux mesurés **sans annonce nommant une porte** | l'ordre officiel écrasait la mémoire personnelle : les deux cohortes prenaient A (accord 1,0), la mémoire ne se voyait pas | divergence 0,00 / ablation 1,00 |
| 2026-11-22 | Le compteur de croyance est journalisé **au moment de décider** (`target_believed_blocked`) | le compteur « désignée à t1 » confondait « se trompe » et « ne croit plus fermé » | à 60 agents : 52 crue-au-moment contre 30 désignée, dont 21 faute de mieux |

---

## 6. Progression

| phase | état | preuve |
|---|---|---|
| 0 — instrumentation | **fait** | 7 tests (`test_prehistoire.py`, `test_mesure.py`) ; mission n°1 : accord **0,00** avec mémoire / **1,00** sans (200 paires), et en foule 60 agents **1,00 / 0,00** (5 graines) ; préhistoire → croyances sourcées datées ; proches à 1,1–1,9 m, lien symétrique, `CHERCHER_PROCHE` en run |
| 1 — statistique | à faire | — |
| 2 — comportements | à faire | — |
| 3 — modèles | à faire | — |
| 4 — contrat | à faire | — |
| 5 — mémoire/livraison | à faire | — |
