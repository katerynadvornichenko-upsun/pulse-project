from datetime import timedelta

import pytest
from sqlmodel import Session, col, select

from pulse.features.issues.jobs import detect_stale_issues_sync
from pulse.features.issues.schemas import IssueCreate
from pulse.features.issues.service import change_status, create_issue
from pulse.features.projects.schemas import ProjectCreate
from pulse.features.projects.service import create_project
from pulse.models import ActivityEvent, Issue, IssueStatus, Project, utcnow


@pytest.fixture
def project(session: Session) -> Project:
    return create_project(session, ProjectCreate(name="P"))


def _age(session: Session, issue: Issue, days: int) -> None:
    """Backdate updated_at, bypassing the service layer on purpose."""
    issue.updated_at = utcnow() - timedelta(days=days)
    session.add(issue)
    session.commit()


def _stale_events(session: Session) -> list[ActivityEvent]:
    return list(
        session.exec(
            select(ActivityEvent).where(col(ActivityEvent.action) == "went_stale")
        ).all()
    )


def test_flags_old_open_issues_once(session: Session, project: Project) -> None:
    issue = create_issue(session, IssueCreate(title="Dusty", project_id=project.id))
    _age(session, issue, 20)

    first = detect_stale_issues_sync(session)
    assert [flagged.id for flagged in first] == [issue.id]
    assert len(_stale_events(session)) == 1

    # Second run: already flagged since its last update, no duplicate event.
    assert detect_stale_issues_sync(session) == []
    assert len(_stale_events(session)) == 1


def test_ignores_fresh_and_closed_issues(session: Session, project: Project) -> None:
    create_issue(session, IssueCreate(title="Fresh", project_id=project.id))
    closed = create_issue(session, IssueCreate(title="Closed", project_id=project.id))
    change_status(session, closed.id, IssueStatus.DONE)
    _age(session, closed, 30)

    assert detect_stale_issues_sync(session) == []
    assert _stale_events(session) == []


def test_reflags_after_new_activity_goes_stale_again(
    session: Session, project: Project
) -> None:
    issue = create_issue(session, IssueCreate(title="Recurring", project_id=project.id))
    _age(session, issue, 40)
    detect_stale_issues_sync(session)

    # Model real chronology: the flag happened 16 days ago, the issue was
    # touched 15 days ago (after the flag), and has now rotted again.
    event = _stale_events(session)[0]
    event.created_at = utcnow() - timedelta(days=16)
    session.add(event)
    _age(session, issue, 15)

    second = detect_stale_issues_sync(session)
    assert [flagged.id for flagged in second] == [issue.id]
    assert len(_stale_events(session)) == 2
