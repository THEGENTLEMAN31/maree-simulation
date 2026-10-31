-- Vue commune à toutes les requêtes (F5).
--
-- Le journal est du JSONL, un objet par ligne. On le lit **ligne par
-- ligne**, sans inférence de schéma : `data` change de forme à chaque type
-- d'événement (une décision porte `llm`, un instantané porte 60 agents), et
-- laisser DuckDB déduire un type commun sur cent runs produit des
-- conversions silencieuses. Ici chaque ligne est du texte JSON, et les
-- requêtes extraient ce qu'elles veulent.
--
--   * `delim`/`quote` neutralisés : une ligne = un champ, jamais découpé ;
--   * `ignore_errors` : un run tué en pleine écriture laisse une ligne
--     tronquée. Faire échouer l'analyse des cent autres runs pour une
--     ligne perdue serait le mauvais compromis — elle est ignorée, et le
--     déséquilibre se voit (un run sans `run.ended` dans `queries/runs.sql`).
--
-- Toute requête de ce répertoire suppose cette vue. `maree query` l'inclut
-- automatiquement, ce qui rend les chiffres du rapport reproductibles par
-- une seule commande.
CREATE OR REPLACE VIEW events AS
SELECT
    json_extract_string(line, '$.run_id')                    AS run_id,
    json_extract_string(line, '$.type')                      AS type,
    CAST(json_extract_string(line, '$.t_prod')  AS INTEGER)  AS t_prod,
    CAST(json_extract_string(line, '$.t_trait') AS INTEGER)  AS t_trait,
    CAST(json_extract_string(line, '$.t_real')  AS DOUBLE)   AS t_real,
    json_extract_string(line, '$.causation_id')              AS causation_id,
    json_extract_string(line, '$.correlation_id')            AS correlation_id,
    json_extract(line, '$.data')                             AS data
FROM read_csv(
    'runs/*/events.jsonl',
    columns = {'line': 'VARCHAR'},
    delim = '', quote = '', escape = '',
    header = false, ignore_errors = true
);
