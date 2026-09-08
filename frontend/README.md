# DARKNETRA frontend

Next.js / React / AI Elements client for the existing FastAPI contract. Run commands below inside `frontend/` unless stated otherwise.

## Local

Use Node.js 22 or newer (Docker uses Node 24). Start the backend using the repository setup instructions, then:

```sh
npm ci
npm run dev
```

Open **http://localhost:3000**. The default proxy target is `http://127.0.0.1:8000`. To change it, set `DARKNETRA_API_BASE_URL` in `frontend/.env.local`. It is a server-only runtime setting. Configure backend `DARKNETRA_WEB_ORIGIN` to exactly match the browser origin; localhost and 127.0.0.1 are different origins.

Use your existing investigator account. Local setup stores the generated administrator and demo investigator passwords in the repository's private `.env`. Never put these values in frontend source or NEXT_PUBLIC variables.

## Docker

From the repository root, after backend setup has generated `.env`:

```sh
docker compose --env-file .env -f infra/docker-compose.yml up -d --build web
```

The standalone web image uses `npm ci`, the frozen OpenAPI schema, bundled fonts, and a non-root runtime. The API target is supplied at container startup, so the image can be reused across environments. This Compose configuration is a local loopback deployment.

## Checks

```sh
npm run typecheck
npm test
npm run build
npm audit
npx playwright install chromium
```

For browser integration checks, run the web server and a seeded local backend in deterministic mode, with the OFFLINE model unavailable. Set `DARKNETRA_E2E_USERNAME` and `DARKNETRA_E2E_PASSWORD` to a local investigator account, then run `npm run test:e2e`. Tests fail explicitly when credentials are missing. `PLAYWRIGHT_BASE_URL` optionally changes the web origin; keep it aligned with backend CSRF configuration. Tests create labelled SYNTHETIC records and do not delete immutable evidence. Screenshots live in ignored `test-results/`.

The private-chat scenario checks persistence and an honest provider-unavailable state; the case scenario verifies a cited deterministic response. A third scenario covers real session refresh, a synthetic temporary refresh outage, and session expiry. These checks do not activate or verify Claude, NIM, Tor, or a local model.

`npm run api:types` regenerates `lib/generated/api.d.ts`. It also runs during install/build/typecheck; generated declarations are intentionally ignored. Typechecking also runs Next.js route type generation, so it works before the first development-server run. Official registry sources are committed under `components/ai-elements` and `components/ui`. Application integration lives under `components/workspace`.

See the root `frontend.md` for feature coverage, event semantics, and backend limitations.
