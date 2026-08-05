from fastapi import APIRouter, Query

from pulse.features.dashboard import service
from pulse.features.dashboard.schemas import ActivityEventRead, DashboardStats
from pulse.lib.db import ReadSessionDep

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def stats(session: ReadSessionDep) -> DashboardStats:
    """Aggregated counts for the dashboard home. Served from the read
    replica; may lag the primary by a few milliseconds."""
    return service.get_stats(session)


@router.get("/activity", response_model=list[ActivityEventRead])
def activity(
    session: ReadSessionDep, limit: int = Query(default=20, ge=1, le=100)
) -> list[ActivityEventRead]:
    """Recent activity events, newest first. Replica-served like /stats."""
    return [
        ActivityEventRead.model_validate(event)
        for event in service.list_recent_activity(session, limit)
    ]
