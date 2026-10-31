-- A1 — la préhistoire se voit-elle dans les décisions ?
-- Part des décisions LLM dont le prompt contient un repère daté « J-… ».
SELECT
    run_id,
    count(*) FILTER (
        WHERE json_extract_string(data, '$.llm.prompt') LIKE '%J-%'
    ) AS decisions_avec_prehistoire,
    count(*) AS decisions_llm,
    round(
        100.0 * count(*) FILTER (
            WHERE json_extract_string(data, '$.llm.prompt') LIKE '%J-%'
        ) / NULLIF(count(*), 0),
        1
    ) AS pourcent
FROM events
WHERE type = 'agent.decision'
  AND json_extract_string(data, '$.kind') = 'llm'
GROUP BY run_id
ORDER BY run_id;
