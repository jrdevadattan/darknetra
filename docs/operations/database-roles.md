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
including for an existing Compose volume; the one-shot `migrate` service then
receives both URLs because Alembic selects the owner URL. The API and worker
receive only the runtime URL. Deployments outside Compose must preserve the same
split and arrange default privileges for future tables.

Custody history is protected twice: the runtime role lacks UPDATE, DELETE, and
TRUNCATE privileges, and database triggers reject row mutation plus runtime
TRUNCATE. Test or maintenance cleanup must connect with the owner URL and use an
explicitly scoped operation. Never run the API or worker with the owner URL.
