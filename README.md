# Pulse

A single-user task tracker with a dashboard, built as a testbed for deploying
on [Upsun](https://upsun.com) and growing one feature at a time through
dispatched agent workflows. The repo is organized so that a well-scoped
feature can be added, tested, and deployed to a preview environment without
touching unrelated code. See `AGENTS.md` for the conventions.

## Stack

FastAPI + SQLModel + Alembic on Python, React + Vite + Tailwind on
TypeScript, PostgreSQL and Redis, and an ARQ worker for background jobs. The
frontend consumes generated OpenAPI types so the API contract is checked at
compile time.

## Local development

You need Python 3.10+ with [uv](https://docs.astral.sh/uv/), Node 20+, and a
local PostgreSQL and Redis (Docker works fine):

```sh
docker run -d --name pulse-pg -e POSTGRES_USER=pulse -e POSTGRES_PASSWORD=pulse -e POSTGRES_DB=pulse -p 5432:5432 postgres:17
docker run -d --name pulse-redis -p 6379:6379 redis:7
```

Then:

```sh
cp .env.example apps/api/.env
make install        # uv sync + npm install
make migrate        # apply migrations
make dev-api        # FastAPI on http://localhost:8000
make dev-web        # Vite on http://localhost:5173, proxies /api to :8000
```

`make test` runs both test suites. `make gen-types` regenerates the frontend
API types after backend changes.

## Deploying to Upsun

The whole setup lives in `.upsun/config.yaml`: a static `web` app, the `api`
app with a `queue` worker, and PostgreSQL + Redis services. Migrations run in
the deploy hook. Create a project, set the remote, and push:

```sh
upsun project:create
git push upsun main
```

Every branch you push gets its own preview environment with isolated copies
of both services.

## Roadmap

Phase 2 adds issues, statuses, and labels as separate slices. Phase 3 brings
the dashboard and the first real background job. Phase 4 adds external feeds
(GitHub, RSS). Each item is meant to be a single slice-sized pull request.
