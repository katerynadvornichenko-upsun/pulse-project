.PHONY: install test lint typecheck migrate gen-types dev-api dev-web dev-worker

install:
	cd apps/api && uv sync
	cd apps/web && npm install

test:
	cd apps/api && uv run pytest
	cd apps/web && npm test

lint:
	cd apps/api && uv run ruff check .
	cd apps/web && npm run lint

typecheck:
	cd apps/api && uv run pyright
	cd apps/web && npm run typecheck

migrate:
	cd apps/api && uv run alembic upgrade head

gen-types:
	cd apps/api && uv run python -m pulse.openapi > ../web/openapi.json
	cd apps/web && npm run gen:types

dev-api:
	cd apps/api && uv run uvicorn pulse.main:app --reload --port 8000

dev-web:
	cd apps/web && npm run dev

dev-worker:
	cd apps/api && uv run arq pulse.worker.WorkerSettings
