-- Local development database bootstrap.
--
-- Creates the role and the two databases the project expects, using the
-- names already fixed by .env.example and docs/backend/DATABASE_SETUP.md:
--
--     role      lostintospace
--     database  lostintospace        (development)
--     database  lostintospace_test   (test suite - never touches dev data)
--
-- NO PASSWORD IS STORED IN THIS FILE. It is passed in as a psql variable at
-- run time, so this script is safe to commit:
--
--   psql -h 127.0.0.1 -U postgres -d postgres \
--        -v app_password="'choose-a-password-here'" \
--        -f database/scripts/setup_local_db.sql
--
-- Note the nested quoting on -v: psql substitutes :app_password literally, so
-- the value must carry its own single quotes.
--
-- Idempotent: safe to re-run. Existing role/databases are left alone (the
-- role's password is NOT reset on re-run, so a working setup can't be broken
-- by running this twice).

\set ON_ERROR_STOP on

-- Role -----------------------------------------------------------------------
-- %L (not %s) so format() applies SQL literal quoting: %s would emit
--   CREATE ROLE ... PASSWORD mypass    -> syntax error
-- whereas %L emits
--   CREATE ROLE ... PASSWORD 'mypass'  -> correct, and safely escaped.
SELECT format('CREATE ROLE lostintospace LOGIN PASSWORD %L', :app_password)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lostintospace')
\gexec

-- Databases ------------------------------------------------------------------
-- CREATE DATABASE cannot run inside a transaction or an IF NOT EXISTS, hence
-- the \gexec pattern: the SELECT emits the DDL only when it's needed, and
-- \gexec executes whatever the query returned.
SELECT 'CREATE DATABASE lostintospace OWNER lostintospace'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'lostintospace')
\gexec

SELECT 'CREATE DATABASE lostintospace_test OWNER lostintospace'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'lostintospace_test')
\gexec

-- Privileges -----------------------------------------------------------------
GRANT ALL PRIVILEGES ON DATABASE lostintospace TO lostintospace;
GRANT ALL PRIVILEGES ON DATABASE lostintospace_test TO lostintospace;

\echo ''
\echo 'Role and databases ready:'
SELECT datname AS database, pg_get_userbyid(datdba) AS owner
FROM pg_database
WHERE datname IN ('lostintospace', 'lostintospace_test')
ORDER BY datname;
