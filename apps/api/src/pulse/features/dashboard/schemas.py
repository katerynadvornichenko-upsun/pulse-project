from pydantic import BaseModel


class DashboardStats(BaseModel):
    projects: int
    issues_total: int
    issues_by_status: dict[str, int]
    issues_by_priority: dict[str, int]
    overdue: int
    activity_last_7_days: int
