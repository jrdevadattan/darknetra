.PHONY: dev test build

dev:
	cd frontend && npm run dev

test:
	cd frontend && npm test && npm run typecheck

build:
	cd frontend && npm run build
