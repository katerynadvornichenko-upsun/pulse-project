import uuid

from fastapi import APIRouter, status

from pulse.features.issues import service
from pulse.features.issues.schemas import (
    IssueCreate,
    IssueRead,
    IssueStatusChange,
    IssueUpdate,
)
from pulse.lib.db import SessionDep
from pulse.models import IssuePriority, IssueStatus

router = APIRouter(prefix="/issues", tags=["issues"])


@router.get("", response_model=list[IssueRead])
def list_issues(
    session: SessionDep,
    project_id: uuid.UUID | None = None,
    status: IssueStatus | None = None,
    priority: IssuePriority | None = None,
) -> list[IssueRead]:
    issues = service.list_issues(session, project_id=project_id, status=status, priority=priority)
    return [IssueRead.model_validate(i) for i in issues]


@router.post("", response_model=IssueRead, status_code=status.HTTP_201_CREATED)
def create_issue(data: IssueCreate, session: SessionDep) -> IssueRead:
    return IssueRead.model_validate(service.create_issue(session, data))


@router.get("/{issue_id}", response_model=IssueRead)
def get_issue(issue_id: uuid.UUID, session: SessionDep) -> IssueRead:
    return IssueRead.model_validate(service.get_issue(session, issue_id))


@router.patch("/{issue_id}", response_model=IssueRead)
def update_issue(issue_id: uuid.UUID, data: IssueUpdate, session: SessionDep) -> IssueRead:
    return IssueRead.model_validate(service.update_issue(session, issue_id, data))


@router.post("/{issue_id}/status", response_model=IssueRead)
def change_status(
    issue_id: uuid.UUID, data: IssueStatusChange, session: SessionDep
) -> IssueRead:
    return IssueRead.model_validate(service.change_status(session, issue_id, data.status))


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issue(issue_id: uuid.UUID, session: SessionDep) -> None:
    service.delete_issue(session, issue_id)
