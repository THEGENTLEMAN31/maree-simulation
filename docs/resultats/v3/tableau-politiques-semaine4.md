# Politiques — comparaison (semaine 4)

*Banc local (stub LLM) : justesse et résolution par situation.*

| situation | attente | rules | llm (stub) | hybrid |
|---|---|---|---|---|
| calme | rester | rester | évacuer vers une sortie⚠ | rester |
| fumee | évacuer vers une sortie | évacuer vers une sortie | évacuer vers une sortie | évacuer vers une sortie |
| annonce_evac | évacuer vers une sortie | évacuer vers une sortie | évacuer vers une sortie | évacuer vers une sortie |
| annonce_calme | rester | rester | évacuer vers une sortie⚠ | rester |
| proche_a_chercher | chercher un proche | chercher un proche | évacuer vers une sortie⚠ | chercher un proche |
| fumee_proche | évacuer vers une sortie | chercher un proche⚠ | évacuer vers une sortie | chercher un proche⚠ |
| aide_altruiste | aider / guider | chercher un proche⚠ | évacuer vers une sortie⚠ | chercher un proche⚠ |

## Synthèse

**rules** — justesse 71%, résolution 100%
**llm** — justesse 43%, résolution 100%
**hybrid** — justesse 71%, résolution 100%
