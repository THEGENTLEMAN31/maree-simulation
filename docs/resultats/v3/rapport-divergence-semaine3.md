# Rapport — expérience des jumeaux (semaine 3)

*Généré de façon déterministe. La KL mesure la divergence des distributions de sortie ; l'accord, la part de paires qui prennent la même sortie. Mémoire `off` = ablation.*

| archétype | scénario | config | mémoire | KL | accord | gauche→A | droite→B |
|---|---|---|---|---:|---:|---:|---:|

| visiteur | fumee_seule | blocages_croises | on | 20.7233 | 0.0 | 0.0 | 0.0 |
| visiteur | fumee_seule | blocages_croises | off | 0.0 | 1.0 | 1.0 | 0.0 |
| visiteur | fumee_seule | inertie_et_reassurance | on | 0.0 | 1.0 | 1.0 | 0.0 |
| visiteur | fumee_seule | inertie_et_reassurance | off | 0.0 | 1.0 | 1.0 | 0.0 |
| visiteur | fumee_seule | deux_herings | on | 20.7233 | 0.0 | 1.0 | 1.0 |
| visiteur | fumee_seule | deux_herings | off | 0.0 | 1.0 | 1.0 | 0.0 |
| visiteur | annonce_puis_fumee | blocages_croises | on | 0.0 | 1.0 | 1.0 | 0.0 |
| visiteur | annonce_puis_fumee | blocages_croises | off | 0.0 | 1.0 | 1.0 | 0.0 |
| visiteur | annonce_puis_fumee | inertie_et_reassurance | on | 0.0 | 1.0 | 1.0 | 0.0 |
| visiteur | annonce_puis_fumee | inertie_et_reassurance | off | 0.0 | 1.0 | 1.0 | 0.0 |
| visiteur | annonce_puis_fumee | deux_herings | on | 0.0 | 1.0 | 1.0 | 0.0 |
| visiteur | annonce_puis_fumee | deux_herings | off | 0.0 | 1.0 | 1.0 | 0.0 |
| habitue | fumee_seule | blocages_croises | on | 0.0 | 1.0 | 1.0 | 0.0 |
| habitue | fumee_seule | blocages_croises | off | 0.0 | 1.0 | 1.0 | 0.0 |
| habitue | fumee_seule | inertie_et_reassurance | on | 20.7233 | 0.0 | 1.0 | 1.0 |
| habitue | fumee_seule | inertie_et_reassurance | off | 0.0 | 1.0 | 1.0 | 0.0 |
| habitue | fumee_seule | deux_herings | on | 20.7233 | 0.0 | 0.0 | 0.0 |
| habitue | fumee_seule | deux_herings | off | 0.0 | 1.0 | 1.0 | 0.0 |
| habitue | annonce_puis_fumee | blocages_croises | on | 0.0 | 1.0 | 1.0 | 0.0 |
| habitue | annonce_puis_fumee | blocages_croises | off | 0.0 | 1.0 | 1.0 | 0.0 |
| habitue | annonce_puis_fumee | inertie_et_reassurance | on | 0.0 | 1.0 | 1.0 | 0.0 |
| habitue | annonce_puis_fumee | inertie_et_reassurance | off | 0.0 | 1.0 | 1.0 | 0.0 |
| habitue | annonce_puis_fumee | deux_herings | on | 0.0 | 1.0 | 1.0 | 0.0 |
| habitue | annonce_puis_fumee | deux_herings | off | 0.0 | 1.0 | 1.0 | 0.0 |

```json
[
 {
  "archetype": "visiteur",
  "scenario": "fumee_seule",
  "config": "blocages_croises",
  "memoire": "on",
  "KL": 20.7233,
  "accord": 0.0,
  "gauche_A": 0.0,
  "droite_B": 0.0
 },
 {
  "archetype": "visiteur",
  "scenario": "fumee_seule",
  "config": "blocages_croises",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "visiteur",
  "scenario": "fumee_seule",
  "config": "inertie_et_reassurance",
  "memoire": "on",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "visiteur",
  "scenario": "fumee_seule",
  "config": "inertie_et_reassurance",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "visiteur",
  "scenario": "fumee_seule",
  "config": "deux_herings",
  "memoire": "on",
  "KL": 20.7233,
  "accord": 0.0,
  "gauche_A": 1.0,
  "droite_B": 1.0
 },
 {
  "archetype": "visiteur",
  "scenario": "fumee_seule",
  "config": "deux_herings",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "visiteur",
  "scenario": "annonce_puis_fumee",
  "config": "blocages_croises",
  "memoire": "on",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "visiteur",
  "scenario": "annonce_puis_fumee",
  "config": "blocages_croises",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "visiteur",
  "scenario": "annonce_puis_fumee",
  "config": "inertie_et_reassurance",
  "memoire": "on",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "visiteur",
  "scenario": "annonce_puis_fumee",
  "config": "inertie_et_reassurance",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "visiteur",
  "scenario": "annonce_puis_fumee",
  "config": "deux_herings",
  "memoire": "on",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "visiteur",
  "scenario": "annonce_puis_fumee",
  "config": "deux_herings",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "fumee_seule",
  "config": "blocages_croises",
  "memoire": "on",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "fumee_seule",
  "config": "blocages_croises",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "fumee_seule",
  "config": "inertie_et_reassurance",
  "memoire": "on",
  "KL": 20.7233,
  "accord": 0.0,
  "gauche_A": 1.0,
  "droite_B": 1.0
 },
 {
  "archetype": "habitue",
  "scenario": "fumee_seule",
  "config": "inertie_et_reassurance",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "fumee_seule",
  "config": "deux_herings",
  "memoire": "on",
  "KL": 20.7233,
  "accord": 0.0,
  "gauche_A": 0.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "fumee_seule",
  "config": "deux_herings",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "annonce_puis_fumee",
  "config": "blocages_croises",
  "memoire": "on",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "annonce_puis_fumee",
  "config": "blocages_croises",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "annonce_puis_fumee",
  "config": "inertie_et_reassurance",
  "memoire": "on",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "annonce_puis_fumee",
  "config": "inertie_et_reassurance",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "annonce_puis_fumee",
  "config": "deux_herings",
  "memoire": "on",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 },
 {
  "archetype": "habitue",
  "scenario": "annonce_puis_fumee",
  "config": "deux_herings",
  "memoire": "off",
  "KL": 0.0,
  "accord": 1.0,
  "gauche_A": 1.0,
  "droite_B": 0.0
 }
]
```
