-- E5/A5 — qui a fait le travail, sur quel modèle, pour combien de jetons.
-- C'est la requête qui rend un « gain de sobriété » démontrable : un total
-- d'appels sans répartition ne dit rien sur la répartition.
SELECT
    run_id,
    json_extract_string(data, '$.llm.tier')  AS tier,
    json_extract_string(data, '$.llm.model') AS modele,
    count(*)                                 AS appels,
    sum(CAST(json_extract_string(data, '$.llm.tokens_in')  AS INTEGER)) AS jetons_entree,
    sum(CAST(json_extract_string(data, '$.llm.tokens_out') AS INTEGER)) AS jetons_sortie,
    round(avg(CAST(json_extract_string(data, '$.llm.duration_s') AS DOUBLE)), 2) AS duree_moyenne_s
FROM events
WHERE type = 'agent.decision'
  AND json_extract_string(data, '$.kind') = 'llm'
GROUP BY run_id, tier, modele
ORDER BY run_id, appels DESC;
