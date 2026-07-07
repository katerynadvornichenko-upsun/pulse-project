from fastapi import APIRouter

from pulse.features.dashboard import service
from pulse.features.dashboard.schemas import DashboardStats
from pulse.lib.db import ReadSessionDep

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def stats(session: ReadSessionDep) -> DashboardStats:
    """Aggregated counts for the dashboard home. Served from the read
    replica; may lag the primary by a few milliseconds."""
    return service.get_stats(session)
