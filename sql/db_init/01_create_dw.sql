-- Analytics Data Warehouse database (created once, on first container start).
-- \gexec executes the returned statement only when the database is missing.
SELECT 'CREATE DATABASE music_dw'
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = 'music_dw'
)
\gexec
