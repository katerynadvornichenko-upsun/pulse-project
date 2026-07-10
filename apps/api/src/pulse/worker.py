"""ARQ worker entrypoint.

Run locally with:  uv run arq pulse.worker.WorkerSettings
On Upsun this runs as the `queue` worker of the api app (see .upsun/config.yaml).

Jobs live in their feature slice (features/<name>/jobs.py) and are only
registered here. Two scheduling paths exist on purpose:

- Worker-internal schedules use ARQ's cron_jobs (stale-issue detection).
- Platform-driven schedules use an Upsun cron that enqueues a job
  (daily rollup via `python -m pulse.jobs.enqueue_rollup`), exercising the
  cron → queue → worker path.
"""

from typing import Any

from arq import cron
from arq.connections import RedisSettings

from pulse.features.dashboard.jobs import daily_rollup
from pulse.features.issues.jobs import detect_stale_issues
from pulse.lib.settings import get_settings


async def ping(ctx: dict[str, Any]) -> str:
    """Smoke-test job: proves the worker consumes from the queue."""
    return "pong"


class WorkerSettings:
    functions = [ping, daily_rollup, detect_stale_issues]
    cron_jobs = [
        # H-style offset baked in: 04:23 UTC daily.
        cron(detect_stale_issues, hour=4, minute=23)
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
