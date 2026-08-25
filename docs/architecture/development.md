# DARKNETRA development environment

## Required local tools

- Node.js 24.x
- pnpm 10.15.0 through Corepack
- Python 3.12.x
- uv 0.12.4
- Docker with Compose v2

## Bootstrap

```bash
corepack enable
corepack prepare pnpm@10.15.0 --activate
pnpm install --frozen-lockfile
uv sync --all-packages --dev --frozen
```

## Native API

```bash
uv run uvicorn --app-dir apps/api darknetra_api.main:app --reload
```

The API listens on `http://127.0.0.1:8000`. Live health is `/api/v1/health/live`; readiness is `/api/v1/health/ready`.

## Native web

In another terminal:

```bash
DARKNETRA_API_BASE_URL=http://127.0.0.1:8000 \
NEXT_PUBLIC_DARKNETRA_API_BASE_URL=http://127.0.0.1:8000 \
pnpm --filter @darknetra/web dev
```

Open `http://127.0.0.1:3000/dashboard`.

## Docker workflow

Copy the example environment and generate the required runtime-role credential
before the first Compose command:

```bash
cp .env.example .env
export DARKNETRA_POSTGRES_RUNTIME_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

PowerShell users can set the same process-local value with:

```powershell
Copy-Item .env.example .env
$env:DARKNETRA_POSTGRES_RUNTIME_PASSWORD = python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Reuse that value for startup, inspection, and teardown; never print or commit it.

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d --wait
```

The base Compose file uses an internal application bridge. The development overlay publishes only loopback ports `3000` and `8000`.

Stop the stack with:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v --remove-orphans
```

Run the deterministic container smoke test with:

```bash
bash scripts/smoke.sh
```

## Plan 01 verification

```bash
uv run ruff check .
uv run pytest -q
pnpm --filter @darknetra/web lint
pnpm --filter @darknetra/web typecheck
pnpm --filter @darknetra/web test
pnpm --filter @darknetra/web build
pnpm --filter @darknetra/web exec playwright install chromium
pnpm --filter @darknetra/web test:e2e
docker compose -f docker-compose.yml -f docker-compose.dev.yml config >/dev/null
bash scripts/smoke.sh
```

## Plan 01 limitations

- Persistent authentication, users, case membership, PostgreSQL, and server-enforced RBAC begin in Plan 02.
- Case and overview records are controlled synthetic or research-archive fixtures and are labeled as such.
- Evidence, extraction, correlation, graph, trend, and report pages are truthful interface boundaries until their dedicated plans.
- Tor, cloud LLMs, GPU access, and external intelligence services are not required for startup or verification.
