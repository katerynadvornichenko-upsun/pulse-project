"""Background jobs owned by the dashboard slice."""

import asyncio
import uuid
from typing import Any

from sqlmodel import Session

from pulse.features.dashboard.service import get_stats
from pulse.lib.db import get_engine
from pulse.models import ActivityEvent


def daily_rollup_sync(session: Session) -> ActivityEvent:
    """Snapshot the day's aggregate numbers into the activity timeline.

    Runs on the primary (it writes); the read-replica guidance applies to
    request-path reads, not to a once-a-day job.
    """
    stats = get_stats(session)
    open_count = stats.issues_total - sum(
        stats.issues_by_status.get(status, 0) for status in ("done", "cancelled")
    )
    event = ActivityEvent(
        entity_type="dashboard",
        entity_id=uuid.uuid4(),
        action="rollup",
        message=(
            f"Daily rollup: {stats.projects} projects, {stats.issues_total} issues "
            f"({open_count} open, {stats.overdue} overdue), "
            f"{stats.activity_last_7_days} events in the last 7 days"
        ),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


async def daily_rollup(ctx: dict[str, Any]) -> str:
    """ARQ entrypoint. Returns the rollup message for the job result log."""

    def run() -> str:
        with Session(get_engine()) as session:
            return daily_rollup_sync(session).message

    return await asyncio.to_thread(run)
