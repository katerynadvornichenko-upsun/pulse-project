import uuid

from sqlmodel import Session, col, select

from pulse.features.issues.schemas import IssueCreate, IssueUpdate
from pulse.lib.errors import NotFoundError
from pulse.models import ActivityEvent, Issue, IssuePriority, IssueStatus, Project, utcnow


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
) -> list[Issue]:
    query = select(Issue).order_by(col(Issue.created_at))
    if project_id is not None:
        query = query.where(Issue.project_id == project_id)
    if status is not None:
        query = query.where(Issue.status == status)
    if priority is not None:
        query = query.where(Issue.priority == priority)
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


def delete_issue(session: Session, issue_id: uuid.UUID) -> None:
    issue = get_issue(session, issue_id)
    _record(session, issue, "deleted")
    session.delete(issue)
    session.commit()
