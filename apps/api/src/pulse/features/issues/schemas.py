import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pulse.models import IssuePriority, IssueStatus


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    status: IssueStatus = IssueStatus.BACKLOG
    priority: IssuePriority = IssuePriority.MEDIUM
    due_date: datetime | None = None
    project_id: uuid.UUID


class IssueUpdate(BaseModel):
    """PATCH body. Omitted fields stay unchanged. An explicit null is only
    accepted for nullable fields (due_date, where it clears the value)."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status: IssueStatus | None = None
    priority: IssuePriority | None = None
    due_date: datetime | None = None

    @field_validator("title", "description", "status", "priority")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field does not accept null")
        return value


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
