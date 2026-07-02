"""Database schema for Pulse.

This module is the single source of truth for persisted models — the
equivalent of a central schema file. Feature slices import from here and add
routers/services/schemas in their own folder. Schema changes require an
Alembic migration (see AGENTS.md).
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_column() -> Column:  # type: ignore[type-arg]
    return Column(DateTime(timezone=True), nullable=False)


class IssueStatus(str, Enum):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class IssuePriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class User(SQLModel, table=True):
    __tablename__ = "users"  # type: ignore[assignment]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    name: str
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp_column())


class Project(SQLModel, table=True):
    __tablename__ = "projects"  # type: ignore[assignment]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True)
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp_column())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=timestamp_column())

    issues: list["Issue"] = Relationship(back_populates="project", cascade_delete=True)


class IssueLabel(SQLModel, table=True):
    __tablename__ = "issue_labels"  # type: ignore[assignment]

    issue_id: uuid.UUID = Field(foreign_key="issues.id", primary_key=True, ondelete="CASCADE")
    label_id: uuid.UUID = Field(foreign_key="labels.id", primary_key=True, ondelete="CASCADE")


class Label(SQLModel, table=True):
    __tablename__ = "labels"  # type: ignore[assignment]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True, index=True)
    color: str = "#808080"

    issues: list["Issue"] = Relationship(back_populates="labels", link_model=IssueLabel)


class Issue(SQLModel, table=True):
    __tablename__ = "issues"  # type: ignore[assignment]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(index=True)
    description: str = ""
    status: IssueStatus = Field(default=IssueStatus.BACKLOG, index=True)
    priority: IssuePriority = Field(default=IssuePriority.MEDIUM, index=True)
    due_date: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Set when the issue enters done/cancelled, cleared when it reopens.
    # Managed exclusively by the status endpoint (features/issues).
    closed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    project_id: uuid.UUID = Field(foreign_key="projects.id", index=True, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp_column())
    updated_at: datetime = Field(default_factory=utcnow, sa_column=timestamp_column())

    project: Project = Relationship(back_populates="issues")
    labels: list[Label] = Relationship(back_populates="issues", link_model=IssueLabel)


class ActivityEvent(SQLModel, table=True):
    """Append-only feed of things that happened, shown on the dashboard timeline."""

    __tablename__ = "activity_events"  # type: ignore[assignment]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_type: str = Field(index=True)  # e.g. "project", "issue"
    entity_id: uuid.UUID = Field(index=True)
    action: str  # e.g. "created", "updated", "deleted"
    message: str = ""
    created_at: datetime = Field(default_factory=utcnow, sa_column=timestamp_column())
