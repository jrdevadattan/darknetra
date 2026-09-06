#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v ON_ERROR_STOP=1 <<'SQL'
\getenv app_password DARKNETRA_DB_APP_PASSWORD
SELECT format('CREATE ROLE darknetra_app LOGIN PASSWORD %L', :'app_password') \gexec
GRANT CONNECT ON DATABASE darknetra TO darknetra_app;
GRANT USAGE ON SCHEMA public TO darknetra_app;
ALTER DEFAULT PRIVILEGES FOR ROLE darknetra_migrate IN SCHEMA public GRANT SELECT, INSERT, UPDATE ON TABLES TO darknetra_app;
ALTER DEFAULT PRIVILEGES FOR ROLE darknetra_migrate IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO darknetra_app;
CREATE DATABASE darknetra_test OWNER darknetra_migrate;
SQL
