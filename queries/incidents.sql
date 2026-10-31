-- A4 — les dérives des agents, par cause et par run.
SELECT
    run_id,
    json_extract_string(data, '$.kind') AS cause,
    count(*)                            AS nombre,
    min(t_prod)                         AS premier_tick,
    max(t_prod)                         AS dernier_tick
FROM events
WHERE type = 'agent.incident'
GROUP BY run_id, cause
ORDER BY run_id, nombre DESC;
