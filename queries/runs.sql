-- F5 — une ligne par run : ce que le rapport affiche en tête de tableau.
-- `maree query runs` redonne exactement ces valeurs sur le même dépôt.
SELECT
    run_id,
    count(*) FILTER (WHERE type = 'metrics.indicators')  AS ticks,
    count(*) FILTER (WHERE type = 'run.ended')           AS termine,
    -- Le CAST est **à l'intérieur** du max : sans lui, DuckDB compare des
    -- chaînes et « 90.0 » gagne contre « 220.0 ». Erreur silencieuse
    -- attrapée en comparant au rapport (le maximum n'était pas le dernier).
    max(CASE WHEN type = 'metrics.indicators'
             THEN CAST(json_extract_string(data, '$.I3_evacuated') AS DOUBLE) END)
                                                         AS I3_evacues,
    max(CASE WHEN type = 'metrics.indicators'
             THEN CAST(json_extract_string(data, '$.I7_delay_seconds') AS DOUBLE) END)
                                                         AS I7_secondes,
    count(*) FILTER (WHERE type = 'agent.decision')      AS decisions,
    count(*) FILTER (WHERE type = 'agent.decision'
                     AND json_extract_string(data, '$.kind') = 'llm') AS decisions_llm,
    count(*) FILTER (WHERE type = 'agent.incident')      AS incidents,
    round(max(t_real), 1)                                AS mural_s
FROM events
GROUP BY run_id
ORDER BY run_id;
