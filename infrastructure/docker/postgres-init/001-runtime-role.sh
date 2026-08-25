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

REVOKE CREATE, TEMPORARY ON DATABASE :"database_name" FROM PUBLIC;
REVOKE ALL PRIVILEGES ON DATABASE :"database_name" FROM darknetra_runtime;
GRANT CONNECT ON DATABASE :"database_name" TO darknetra_runtime;

SELECT format(
  'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA %I FROM darknetra_runtime, PUBLIC',
  nspname
)
FROM pg_namespace
WHERE nspname <> 'public'
  AND nspname <> 'information_schema'
  AND nspname NOT LIKE 'pg\_%' ESCAPE '\'
\gexec
SELECT format(
  'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA %I FROM darknetra_runtime, PUBLIC',
  nspname
)
FROM pg_namespace
WHERE nspname <> 'public'
  AND nspname <> 'information_schema'
  AND nspname NOT LIKE 'pg\_%' ESCAPE '\'
\gexec
SELECT format(
  'REVOKE ALL PRIVILEGES ON ALL ROUTINES IN SCHEMA %I FROM darknetra_runtime, PUBLIC',
  nspname
)
FROM pg_namespace
WHERE nspname <> 'public'
  AND nspname <> 'information_schema'
  AND nspname NOT LIKE 'pg\_%' ESCAPE '\'
\gexec
SELECT format(
  'REVOKE ALL PRIVILEGES ON TYPE %I.%I FROM darknetra_runtime, PUBLIC',
  namespace.nspname,
  type_record.typname
)
FROM pg_type type_record
JOIN pg_namespace namespace ON namespace.oid = type_record.typnamespace
LEFT JOIN pg_class composite_record ON composite_record.oid = type_record.typrelid
WHERE (
    type_record.typtype IN ('d', 'e', 'm', 'r')
    OR (type_record.typtype = 'c' AND composite_record.relkind = 'c')
  )
  AND namespace.nspname <> 'public'
  AND namespace.nspname <> 'information_schema'
  AND namespace.nspname NOT LIKE 'pg\_%' ESCAPE '\'
\gexec
SELECT format(
  'REVOKE ALL PRIVILEGES ON SCHEMA %I FROM darknetra_runtime, PUBLIC',
  nspname
)
FROM pg_namespace
WHERE nspname <> 'public'
  AND nspname <> 'information_schema'
  AND nspname NOT LIKE 'pg\_%' ESCAPE '\'
\gexec

SELECT DISTINCT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I%s REVOKE ALL PRIVILEGES ON %s FROM %s',
  grantor.rolname,
  CASE
    WHEN defaults.defaclnamespace = 0 THEN ''
    ELSE format(' IN SCHEMA %I', namespace.nspname)
  END,
  CASE defaults.defaclobjtype
    WHEN 'r' THEN 'TABLES'
    WHEN 'S' THEN 'SEQUENCES'
    WHEN 'f' THEN 'FUNCTIONS'
    WHEN 'T' THEN 'TYPES'
    WHEN 'n' THEN 'SCHEMAS'
  END,
  CASE WHEN privilege.grantee = 0 THEN 'PUBLIC' ELSE 'darknetra_runtime' END
)
FROM pg_default_acl defaults
JOIN pg_roles grantor ON grantor.oid = defaults.defaclrole
LEFT JOIN pg_namespace namespace ON namespace.oid = defaults.defaclnamespace
CROSS JOIN LATERAL aclexplode(defaults.defaclacl) privilege
JOIN pg_roles runtime_role ON runtime_role.rolname = 'darknetra_runtime'
WHERE (
    privilege.grantee = runtime_role.oid
    OR (
      privilege.grantee = 0
      AND (
        defaults.defaclobjtype = 'n'
        OR (
          namespace.nspname <> 'public'
          AND namespace.nspname <> 'information_schema'
          AND namespace.nspname NOT LIKE 'pg\_%' ESCAPE '\'
        )
      )
    )
  )
  AND defaults.defaclobjtype IN ('r', 'S', 'f', 'T', 'n')
\gexec

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
