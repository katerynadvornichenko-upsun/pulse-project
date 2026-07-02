"""ARQ worker entrypoint.

Run locally with:  uv run arq pulse.worker.WorkerSettings
On Upsun this runs as the `queue` worker of the api app (see .upsun/config.yaml).

Real jobs (stale-issue detection, daily rollups, feed fetching) arrive in
later phases. Each job should live in its feature slice and only be
registered here.
"""

from typing import Any

from arq.connections import RedisSettings

from pulse.lib.settings import get_settings


async def ping(ctx: dict[str, Any]) -> str:
    """Smoke-test job: proves the worker consumes from the queue."""
    return "pong"


class WorkerSettings:
    functions = [ping]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
