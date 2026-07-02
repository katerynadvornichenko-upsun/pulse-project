# Preview environment smoke test

Run this after the first successful push, and again whenever
`.upsun/config.yaml` changes. It validates the exact path every dispatched
workflow will rely on. Replace `<env-url>` with the URL `upsun url` prints
(or the one shown at the end of the push output).

## 1. Deployment came up

```sh
upsun environment:info status        # expects: active
upsun activity:list --limit 3        # the push activity ended with result: success
```

If the build failed, `upsun activity:log` on the failed activity shows which
hook broke. The two most likely first-run failures are the runtime versions
(`python:3.12` / `nodejs:20` in `.upsun/config.yaml`) and the uv install in
the api build hook.

## 2. Migrations ran in the deploy hook

```sh
upsun activity:log --type environment.push | grep -A 3 "alembic"
```

Expect `Running upgrade  -> 1abf75f50b75, initial schema`. Then confirm the
tables exist:

```sh
upsun sql 'SELECT tablename FROM pg_tables WHERE schemaname = current_schema()'
```

Expect `users`, `projects`, `issues`, `labels`, `issue_labels`,
`activity_events`, and `alembic_version`.

## 3. API responds through the route

```sh
curl -s https://<env-url>/api/health
```

Expect `{"status":"ok","version":"0.1.0"}`. Then exercise a real write path:

```sh
curl -s -X POST https://<env-url>/api/projects \
  -H 'Content-Type: application/json' \
  -d '{"name": "Smoke test", "description": "created by the checklist"}'
curl -s https://<env-url>/api/projects
```

The POST returns 201 with an id; the GET lists the project. This proves the
api container reaches PostgreSQL through the relationship.

## 4. Web app serves and reaches the API

Open `https://<env-url>/` in a browser. The page shows "API status: ok" and
the smoke-test project in the list. That proves the static build, the SPA
passthru rule, and the `/api` route split all work.

## 5. Worker is consuming the queue

```sh
upsun ssh --app api --worker queue 'ps ax | grep -v grep | grep arq'
```

Expect an `arq pulse.worker.WorkerSettings` process. To prove it talks to
Redis end to end, enqueue the ping job from the api container:

```sh
upsun ssh --app api '.venv/bin/python -c "
import asyncio
from arq import create_pool
from pulse.worker import WorkerSettings

async def main():
    pool = await create_pool(WorkerSettings.redis_settings)
    job = await pool.enqueue_job(\"ping\")
    print(await job.result(timeout=10))

asyncio.run(main())
"'
```

Expect `pong`.

## 6. Branch isolation

```sh
git checkout -b smoke/preview-isolation
git push upsun smoke/preview-isolation
upsun environment:activate smoke/preview-isolation
```

On the new environment's URL, `GET /api/projects` returns data inherited from
the parent at branch time; create a project there and confirm it does not
appear on the parent environment. Delete the branch environment afterwards:

```sh
upsun environment:delete smoke/preview-isolation
```

## 7. Clean up

Delete the smoke-test project via the API or leave it; nothing else in the
checklist writes data. If every step passed, the repo is ready for the first
dispatched issue in `docs/backlog.md`.
