-- Airflow keeps its own bookkeeping in its own database.
--
-- On the same Postgres instance, because running a second one for a teaching
-- project is a support burden nobody needs. In a separate database, because an
-- orchestrator's metadata is not business data and must never end up joinable
-- to it by accident.
SELECT 'CREATE DATABASE airflow'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow')\gexec
