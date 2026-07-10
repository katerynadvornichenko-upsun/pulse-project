"""Enqueue the daily dashboard rollup.

Invoked by the Upsun cron (see .upsun/config.yaml):
    .venv/bin/python -m pulse.jobs.enqueue_rollup

The cron only enqueues; the queue worker executes the job. That keeps cron
commands instant and puts the real work where the retry/backoff machinery is.
"""

import asyncio

from arq import create_pool

from pulse.worker import WorkerSettings


async def main() -> None:
    pool = await create_pool(WorkerSettings.redis_settings)
    job = await pool.enqueue_job("daily_rollup")
    print(f"enqueued daily_rollup: {job.job_id if job else 'already queued'}")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
