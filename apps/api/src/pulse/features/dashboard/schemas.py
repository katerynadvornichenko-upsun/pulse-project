import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DashboardStats(BaseModel):
    projects: int
    issues_total: int
    issues_by_status: dict[str, int]
    issues_by_priority: dict[str, int]
    overdue: int
    activity_last_7_days: int


class ActivityEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    message: str
    created_at: datetime
