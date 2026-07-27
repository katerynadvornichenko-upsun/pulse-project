# Working on Pulse

Rules and commands for anyone (human or agent) making changes to this repo.
All paths are relative to the project root.

## Layout

- `apps/api` is the FastAPI backend. Code lives in `apps/api/src/pulse`.
- `apps/web` is the React frontend (Vite, Tailwind, TanStack Query).
- `apps/api/src/pulse/worker.py` is the ARQ queue worker. It ships in the api
  codebase and runs as a separate process on Upsun.
- `.upsun/config.yaml` defines the three runtime surfaces plus PostgreSQL and Redis.

## Commands

Run these from the directory named in each line.

- `apps/api`: `uv sync` to install, `uv run pytest` to test,
  `uv run ruff check .` to lint, `uv run pyright` to typecheck.
- `apps/web`: `npm install`, `npm test`, `npm run lint`, `npm run typecheck`,
  `npm run build`.
- Repo root: `make test` runs both suites, `make gen-types` regenerates the
  frontend API types. See the Makefile for the rest.

A change is mergeable when lint, typecheck, and tests pass in both apps.
CI runs exactly these checks.

## How to add a feature slice

1. Copy `apps/api/src/pulse/features/_template` to
   `apps/api/src/pulse/features/<name>` and follow the README inside it.
2. Keep everything for the slice in that folder: router, service, schemas, tests.
3. Routers are thin. Business logic goes in `service.py`. Services take a
   `Session` argument and never open their own.
4. Raise `pulse.lib.errors.NotFoundError` for missing entities. It maps to 404.
   PATCH semantics are uniform: omitted fields stay unchanged, explicit null
   clears nullable fields, and explicit null on a non-nullable field is a 422
   (enforced by a `field_validator` in the update schema; services dump with
   `model_dump(exclude_unset=True)`).
5. Record an `ActivityEvent` for every create, update, and delete so the
   dashboard timeline stays complete.
6. Register the new router in `apps/api/src/pulse/main.py`. All routes are
   mounted under `/api`.
7. Add frontend code under `apps/web/src` and run `make gen-types` so the
   frontend sees the new endpoints.

## Background jobs

- Jobs live in their feature slice as `features/<name>/jobs.py`: a sync core
  that takes a `Session` (test it with the `session` fixture) plus a thin
  async ARQ entrypoint that opens its own session via `asyncio.to_thread`.
- Register the entrypoint in `apps/api/src/pulse/worker.py` (`functions`,
  and `cron_jobs` if worker-scheduled).
- Two scheduling paths, both deliberate: worker-internal schedules use ARQ
  `cron_jobs`; platform-driven schedules use an Upsun cron that enqueues the
  job (see `pulse/jobs/enqueue_rollup.py` and the `crons` block in
  `.upsun/config.yaml`).
- Run the worker locally with `make dev-worker`.

## Database models and migrations

All persisted models live in `apps/api/src/pulse/models.py`. Do not define
tables anywhere else. To change the schema:

1. Edit `apps/api/src/pulse/models.py`.
2. From `apps/api`, run
   `DATABASE_URL=<your dev db> uv run alembic revision --autogenerate -m "<message>"`.
3. Read the generated file in `apps/api/alembic/versions/` before committing.
   Autogenerate misses renames and some constraint changes.
4. `uv run alembic upgrade head` locally to confirm it applies.

Upsun runs `alembic upgrade head` in the deploy hook, so a merged migration
applies automatically on every environment.

## The API/frontend contract

The frontend consumes generated OpenAPI types, committed at
`apps/web/src/lib/api-types.gen.ts`. If you change any router or schema in the
API, run `make gen-types` and commit the result. Never edit the generated file
by hand. CI fails typecheck if the frontend uses endpoints that do not exist.

## Testing expectations

- Every slice has tests next to its code. Use the `session` and `client`
  fixtures from `apps/api/conftest.py`.
- Tests run on SQLite in memory by default. CI also runs them against
  PostgreSQL via `TEST_DATABASE_URL`, so avoid SQLite-only or Postgres-only
  SQL in application code.
- Frontend tests use Vitest. Stub `fetch`; never call a real API in tests.

## Things that will break if you improvise

- Renaming an Upsun service in `.upsun/config.yaml` destroys its data.
- `apps/api/.environment` maps Upsun relationship variables to `DATABASE_URL`,
  `DATABASE_REPLICA_URL`, and `REDIS_URL`. The app reads only those variables
  via `pulse.lib.settings`.
- The PostgreSQL replica is read-only and replication is asynchronous. Use
  `ReadSessionDep` from `apps/api/src/pulse/lib/db.py` only for reads that
  tolerate slight staleness (dashboard aggregation, reporting, background
  jobs). CRUD endpoints keep using `SessionDep` so clients read their own
  writes. Without a configured replica, `ReadSessionDep` falls back to the
  primary, so local dev needs no extra setup. The service type is
  `postgresql-replica` and its disk starts at 256MB — size it to match the
  primary with `upsun resources:set`.
- Route paths must keep the `/api` prefix. The Vite dev proxy and the Upsun
  router both depend on it.
- `apps/api/uv.lock` and `apps/web/package-lock.json` are the source of truth
  for dependencies. Change them only through `uv` and `npm`.
