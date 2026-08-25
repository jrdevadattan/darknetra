#!/bin/sh
set -eu

if [ -z "${DARKNETRA_POSTGRES_RUNTIME_PASSWORD:-}" ]; then
  echo "DARKNETRA_POSTGRES_RUNTIME_PASSWORD must be configured" >&2
  exit 1
fi

psql \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=runtime_password="$DARKNETRA_POSTGRES_RUNTIME_PASSWORD" \
  --set=owner_role="$POSTGRES_USER" \
  --set=database_name="$POSTGRES_DB" <<'SQL'
SELECT format(
  'CREATE ROLE darknetra_runtime LOGIN PASSWORD %L',
  :'runtime_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'darknetra_runtime')
\gexec

ALTER ROLE darknetra_runtime LOGIN PASSWORD :'runtime_password';

GRANT CONNECT ON DATABASE :"database_name" TO darknetra_runtime;
GRANT USAGE ON SCHEMA public TO darknetra_runtime;
REVOKE CREATE ON SCHEMA public FROM darknetra_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO darknetra_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO darknetra_runtime;
SQL
