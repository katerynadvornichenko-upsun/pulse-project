import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pulse.models import IssuePriority, IssueStatus


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    status: IssueStatus = IssueStatus.BACKLOG
    priority: IssuePriority = IssuePriority.MEDIUM
    due_date: datetime | None = None
    project_id: uuid.UUID


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status: IssueStatus | None = None
    priority: IssuePriority | None = None
    due_date: datetime | None = None


class IssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    status: IssueStatus
    priority: IssuePriority
    due_date: datetime | None
    project_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
