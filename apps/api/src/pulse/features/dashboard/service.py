"""Dashboard aggregations.

These queries run on the read replica (ReadSessionDep) in production: they
are read-only, aggregate whole tables, and tolerate a few milliseconds of
replication lag.
"""

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, col, select

from pulse.features.dashboard.schemas import DashboardStats
from pulse.features.issues.service import CLOSED_STATUSES
from pulse.models import ActivityEvent, Issue, Project, utcnow


def list_recent_activity(session: Session, limit: int = 20) -> Sequence[ActivityEvent]:
    """Newest activity events first, for the dashboard timeline.

    `id` breaks ties: rows written in one operation share a `created_at`, and
    without a stable tiebreak the limit boundary would drop or reorder them
    non-deterministically between reads.
    """
    return session.exec(
        select(ActivityEvent)
        .order_by(col(ActivityEvent.created_at).desc(), col(ActivityEvent.id).desc())
        .limit(limit)
    ).all()


def _enum_counts(rows: Sequence[tuple[Any, int]]) -> dict[str, int]:
    """Map (enum, count) rows to {value: count}; tolerates raw-string keys."""
    return {getattr(key, "value", str(key)): count for key, count in rows}


def get_stats(session: Session) -> DashboardStats:
    projects = session.exec(select(func.count()).select_from(Project)).one()
    issues_total = session.exec(select(func.count()).select_from(Issue)).one()

    by_status = session.exec(
        select(Issue.status, func.count()).group_by(col(Issue.status))
    ).all()
    by_priority = session.exec(
        select(Issue.priority, func.count()).group_by(col(Issue.priority))
    ).all()

    now = utcnow()
    overdue = session.exec(
        select(func.count())
        .select_from(Issue)
        .where(col(Issue.due_date) < now)
        .where(col(Issue.status).not_in(CLOSED_STATUSES))
    ).one()

    activity_last_7_days = session.exec(
        select(func.count())
        .select_from(ActivityEvent)
        .where(col(ActivityEvent.created_at) >= now - timedelta(days=7))
    ).one()

    return DashboardStats(
        projects=projects,
        issues_total=issues_total,
        issues_by_status=_enum_counts(by_status),
        issues_by_priority=_enum_counts(by_priority),
        overdue=overdue,
        activity_last_7_days=activity_last_7_days,
    )
