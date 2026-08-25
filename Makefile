DARKNETRA_POSTGRES_RUNTIME_PASSWORD ?= $(shell python -c "import secrets; print(secrets.token_urlsafe(32))")
export DARKNETRA_POSTGRES_RUNTIME_PASSWORD

.PHONY: bootstrap dev test check build smoke

bootstrap:
	corepack enable
	pnpm install
	uv sync --dev

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

test:
	uv run pytest -q
	pnpm test

check:
	uv run ruff check .
	uv run pytest -q
	pnpm check

build:
	pnpm build
	docker compose -f docker-compose.yml -f docker-compose.dev.yml build

smoke:
	bash scripts/smoke.sh
