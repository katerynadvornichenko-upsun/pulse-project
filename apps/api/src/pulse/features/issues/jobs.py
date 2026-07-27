"""Background jobs owned by the issues slice.

The sync core is plain service code (testable with the `session` fixture);
the async wrapper at the bottom is what the ARQ worker registers.
"""

import asyncio
from datetime import timedelta
from typing import Any

from sqlmodel import Session, col, select

from pulse.features.issues.service import CLOSED_STATUSES
from pulse.lib.db import get_engine
from pulse.models import ActivityEvent, Issue, utcnow

STALE_AFTER_DAYS = 14


def detect_stale_issues_sync(
    session: Session, stale_after_days: int = STALE_AFTER_DAYS
) -> list[Issue]:
    """Flag open issues untouched for `stale_after_days` days.

    Records one `went_stale` ActivityEvent per issue per staleness period:
    an issue already flagged since its last update is not flagged again, but
    an issue that was touched and went stale again gets a fresh event.
    Returns the newly flagged issues.
    """
    cutoff = utcnow() - timedelta(days=stale_after_days)
    candidates = session.exec(
        select(Issue)
        .where(col(Issue.status).not_in(CLOSED_STATUSES))
        .where(col(Issue.updated_at) < cutoff)
    ).all()

    newly_flagged: list[Issue] = []
    for issue in candidates:
        already_flagged = session.exec(
            select(ActivityEvent)
            .where(ActivityEvent.entity_id == issue.id)
            .where(ActivityEvent.action == "went_stale")
            .where(col(ActivityEvent.created_at) >= issue.updated_at)
        ).first()
        if already_flagged:
            continue
        session.add(
            ActivityEvent(
                entity_type="issue",
                entity_id=issue.id,
                action="went_stale",
                message=(
                    f"Issue '{issue.title}' has had no activity for "
                    f"{stale_after_days}+ days"
                ),
            )
        )
        newly_flagged.append(issue)

    session.commit()
    return newly_flagged


async def detect_stale_issues(ctx: dict[str, Any]) -> int:
    """ARQ entrypoint. Returns the number of newly flagged issues."""

    def run() -> int:
        with Session(get_engine()) as session:
            return len(detect_stale_issues_sync(session))

    return await asyncio.to_thread(run)
