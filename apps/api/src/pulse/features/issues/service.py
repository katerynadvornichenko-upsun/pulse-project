import uuid

from sqlmodel import Session, col, select

from pulse.features.issues.schemas import IssueCreate, IssueLabelsReplace, IssueUpdate
from pulse.features.labels.service import get_label
from pulse.lib.errors import NotFoundError
from pulse.models import (
    ActivityEvent,
    Issue,
    IssueLabel,
    IssuePriority,
    IssueStatus,
    Project,
    utcnow,
)

CLOSED_STATUSES = {IssueStatus.DONE, IssueStatus.CANCELLED}


def _record(session: Session, issue: Issue, action: str) -> None:
    session.add(
        ActivityEvent(
            entity_type="issue",
            entity_id=issue.id,
            action=action,
            message=f"Issue '{issue.title}' {action}",
        )
    )


def list_issues(
    session: Session,
    project_id: uuid.UUID | None = None,
    status: IssueStatus | None = None,
    priority: IssuePriority | None = None,
    label_id: uuid.UUID | None = None,
) -> list[Issue]:
    query = select(Issue).order_by(col(Issue.created_at))
    if project_id is not None:
        query = query.where(Issue.project_id == project_id)
    if status is not None:
        query = query.where(Issue.status == status)
    if priority is not None:
        query = query.where(Issue.priority == priority)
    if label_id is not None:
        query = query.join(IssueLabel).where(IssueLabel.label_id == label_id)
    return list(session.exec(query).all())


def get_issue(session: Session, issue_id: uuid.UUID) -> Issue:
    issue = session.get(Issue, issue_id)
    if issue is None:
        raise NotFoundError("Issue", issue_id)
    return issue


def create_issue(session: Session, data: IssueCreate) -> Issue:
    if session.get(Project, data.project_id) is None:
        raise NotFoundError("Project", data.project_id)
    issue = Issue(**data.model_dump())
    # Keep the invariant: closed_at is non-null exactly when status is closed,
    # including for issues created directly in a closed status.
    if issue.status in CLOSED_STATUSES:
        issue.closed_at = utcnow()
    session.add(issue)
    _record(session, issue, "created")
    session.commit()
    session.refresh(issue)
    return issue


def update_issue(session: Session, issue_id: uuid.UUID, data: IssueUpdate) -> Issue:
    issue = get_issue(session, issue_id)
    # exclude_unset only: explicit nulls must be applied (they clear nullable
    # fields); the schema already rejects null for non-nullable fields.
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(issue, key, value)
    issue.updated_at = utcnow()
    session.add(issue)
    _record(session, issue, "updated")
    session.commit()
    session.refresh(issue)
    return issue


def change_status(session: Session, issue_id: uuid.UUID, new_status: IssueStatus) -> Issue:
    issue = get_issue(session, issue_id)
    old_status = issue.status
    if new_status == old_status:
        # Idempotent no-op: don't move closed_at forward, bump updated_at,
        # or pollute the timeline with "moved from done to done".
        return issue
    issue.status = new_status
    issue.closed_at = utcnow() if new_status in CLOSED_STATUSES else None
    issue.updated_at = utcnow()
    session.add(issue)
    session.add(
        ActivityEvent(
            entity_type="issue",
            entity_id=issue.id,
            action="status_changed",
            message=f"Issue '{issue.title}' moved from {old_status.value} to {new_status.value}",
        )
    )
    session.commit()
    session.refresh(issue)
    return issue


def replace_issue_labels(
    session: Session, issue_id: uuid.UUID, data: IssueLabelsReplace
) -> Issue:
    issue = get_issue(session, issue_id)
    # Deduplicate while preserving order: a repeated id would otherwise
    # violate the issue_labels composite primary key on commit.
    unique_ids = list(dict.fromkeys(data.label_ids))
    labels = [get_label(session, label_id) for label_id in unique_ids]

    issue.labels = labels
    issue.updated_at = utcnow()
    session.add(issue)
    names = ", ".join(label.name for label in labels) or "none"
    session.add(
        ActivityEvent(
            entity_type="issue",
            entity_id=issue.id,
            action="labels_changed",
            message=f"Issue '{issue.title}' labels set to: {names}",
        )
    )
    session.commit()
    session.refresh(issue)
    return issue


def delete_issue(session: Session, issue_id: uuid.UUID) -> None:
    issue = get_issue(session, issue_id)
    _record(session, issue, "deleted")
    session.delete(issue)
    session.commit()
