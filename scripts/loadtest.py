"""Read-heavy load generator for autoscaling tests.

Seeds data through the API, then hammers the read endpoints (most of the
load lands on /api/dashboard/stats, which runs aggregate queries on the
PostgreSQL read replica).

Run from apps/api so httpx (a dev dependency) is available:

    cd apps/api
    uv run python ../../scripts/loadtest.py --base-url https://<env-url> --seed 2000
    uv run python ../../scripts/loadtest.py --base-url https://<env-url> \
        --concurrency 50 --duration 600

Stop any time with Ctrl+C. See docs/autoscaling-test.md for the full runbook.
"""

import argparse
import asyncio
import random
import string
import time

import httpx

STATUSES = ["backlog", "todo", "in_progress", "done", "cancelled"]
PRIORITIES = ["low", "medium", "high", "urgent"]


def rand_word(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase, k=n))


async def seed(client: httpx.AsyncClient, issues: int) -> None:
    """Create projects and issues so the aggregate queries have rows to scan."""
    project_ids: list[str] = []
    for i in range(max(3, issues // 500)):
        resp = await client.post(
            "/api/projects", json={"name": f"loadtest-{rand_word()}-{i}"}
        )
        resp.raise_for_status()
        project_ids.append(resp.json()["id"])

    async def create_one(i: int) -> None:
        resp = await client.post(
            "/api/issues",
            json={
                "title": f"issue {i} {rand_word(16)}",
                "description": rand_word(64),
                "project_id": random.choice(project_ids),
                "status": random.choice(STATUSES),
                "priority": random.choice(PRIORITIES),
            },
        )
        resp.raise_for_status()

    batch = 25
    for start in range(0, issues, batch):
        await asyncio.gather(*(create_one(i) for i in range(start, start + batch)))
        if start % 500 == 0:
            print(f"seeded {start}/{issues}")
    print(f"seeded {issues} issues across {len(project_ids)} projects")


async def read_worker(
    client: httpx.AsyncClient, stop_at: float, counts: dict[str, int]
) -> None:
    paths = [
        "/api/dashboard/stats",  # replica-backed aggregates: the main target
        "/api/dashboard/stats",
        "/api/dashboard/stats",
        "/api/issues",
        f"/api/issues?status={random.choice(STATUSES)}",
        "/api/projects",
    ]
    while time.monotonic() < stop_at:
        try:
            resp = await client.get(random.choice(paths))
            counts["ok" if resp.status_code == 200 else "error"] += 1
        except httpx.HTTPError:
            counts["error"] += 1


async def run_load(client: httpx.AsyncClient, concurrency: int, duration: int) -> None:
    counts = {"ok": 0, "error": 0}
    stop_at = time.monotonic() + duration
    workers = [read_worker(client, stop_at, counts) for _ in range(concurrency)]

    async def report() -> None:
        while time.monotonic() < stop_at:
            await asyncio.sleep(10)
            total = counts["ok"] + counts["error"]
            print(f"requests: {total} ok: {counts['ok']} errors: {counts['error']}")

    await asyncio.gather(*workers, report())
    print(f"done. ok: {counts['ok']} errors: {counts['error']}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--seed", type=int, default=0, help="create N issues, then exit")
    parser.add_argument("--concurrency", type=int, default=30)
    parser.add_argument("--duration", type=int, default=300, help="seconds")
    args = parser.parse_args()

    async with httpx.AsyncClient(
        base_url=args.base_url, timeout=30, follow_redirects=True
    ) as client:
        resp = await client.get("/api/health")
        resp.raise_for_status()
        print(f"target healthy: {resp.json()}")
        if args.seed:
            await seed(client, args.seed)
        else:
            await run_load(client, args.concurrency, args.duration)


if __name__ == "__main__":
    asyncio.run(main())
