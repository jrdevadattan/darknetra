# PostgreSQL owner and runtime roles

DARKNETRA uses separate PostgreSQL credentials for schema ownership and normal
application work.

- `DARKNETRA_DATABASE_OWNER_URL` is a migration/maintenance credential. Only
  Alembic and explicitly authorized maintenance tooling may receive it.
- `DARKNETRA_DATABASE_URL` is the API and worker credential. It may read and
  perform ordinary application writes, but it does not own the schema, cannot
  create schema objects, and has only `SELECT`/`INSERT` on `custody_events`.

Compose retains `darknetra` as the migration/schema owner and creates
`darknetra_runtime` as the least-privileged application role. A one-shot
`db-bootstrap` service makes the runtime role and default grants idempotently,
including for an existing Compose volume. Reconciliation removes unintended
role memberships, resets the role to `NOSUPERUSER`, `NOCREATEDB`,
`NOCREATEROLE`, `NOREPLICATION`, `NOBYPASSRLS`, and `INHERIT`, transfers only
objects it owns in the current database back to the configured owner, and
revokes direct database CREATE/TEMP, removes direct privileges across every
non-system schema in the current database, clears poisoned default ACLs, and
rebuilds only the intended public-schema table and sequence grants. Database
TEMPORARY is also revoked from PUBLIC so it cannot be inherited by the runtime
role. The reconciliation does not inspect or change other databases. The
one-shot `migrate` service then
receives both URLs because Alembic selects the owner URL. The API and worker
receive only the runtime URL. Deployments outside Compose must preserve the same
split and arrange default privileges for future tables.

`DARKNETRA_POSTGRES_RUNTIME_PASSWORD` is required by Compose and must be
generated at deployment runtime. PostgreSQL initialization, bootstrap, API,
worker, and migrate all derive the runtime credential from that one value. Do
not put a reusable password in an image, workflow, or committed environment
file.

Custody history is protected twice: the runtime role lacks UPDATE, DELETE, and
TRUNCATE privileges, and database triggers reject row mutation plus runtime
TRUNCATE. Test or maintenance cleanup must connect with the owner URL and use an
explicitly scoped operation. Never run the API or worker with the owner URL.
