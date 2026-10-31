-- A2/B3 — ce que la communication change : messages diffusés, et I1/I2
-- au dernier tick. Le bras « sans communication » doit avoir 0 message,
-- sinon le contrôle négatif ne prouve rien.
WITH dernier AS (
    SELECT run_id, max(t_prod) AS tick
    FROM events WHERE type = 'metrics.indicators' GROUP BY run_id
)
SELECT
    e.run_id,
    count(*) FILTER (WHERE e.type = 'agent.message.sent') AS messages,
    max(CASE WHEN e.type = 'metrics.indicators' AND e.t_prod = d.tick
             THEN CAST(json_extract_string(e.data, '$.I1_consensus') AS DOUBLE) END)
                                                          AS I1_final,
    max(CASE WHEN e.type = 'metrics.indicators' AND e.t_prod = d.tick
             THEN CAST(json_extract_string(e.data, '$.I2_entropy') AS DOUBLE) END)
                                                          AS I2_final
FROM events e
JOIN dernier d USING (run_id)
GROUP BY e.run_id
ORDER BY e.run_id;
