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
  'CREATE ROLE darknetra_runtime LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB '
  'NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT',
  :'runtime_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'darknetra_runtime')
\gexec

ALTER ROLE darknetra_runtime LOGIN PASSWORD :'runtime_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;

SELECT format('REVOKE %I FROM darknetra_runtime', granted_role.rolname)
FROM pg_auth_members membership
JOIN pg_roles granted_role ON granted_role.oid = membership.roleid
JOIN pg_roles member_role ON member_role.oid = membership.member
WHERE member_role.rolname = 'darknetra_runtime'
\gexec

REASSIGN OWNED BY darknetra_runtime TO :"owner_role";

GRANT CONNECT ON DATABASE :"database_name" TO darknetra_runtime;
GRANT USAGE ON SCHEMA public TO darknetra_runtime;
REVOKE CREATE ON SCHEMA public FROM darknetra_runtime;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM darknetra_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
  TO darknetra_runtime;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM darknetra_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO darknetra_runtime;
SELECT 'REVOKE UPDATE, DELETE, TRUNCATE ON public.custody_events FROM darknetra_runtime'
WHERE to_regclass('public.custody_events') IS NOT NULL
\gexec
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
  REVOKE ALL ON TABLES FROM darknetra_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO darknetra_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
  REVOKE ALL ON SEQUENCES FROM darknetra_runtime;
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_role" IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO darknetra_runtime;
SQL
