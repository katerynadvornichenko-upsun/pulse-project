from datetime import timedelta

from fastapi.testclient import TestClient
from sqlmodel import Session

from pulse.features.dashboard import service
from pulse.features.issues.schemas import IssueCreate
from pulse.features.issues.service import change_status, create_issue
from pulse.features.projects.schemas import ProjectCreate
from pulse.features.projects.service import create_project
from pulse.models import IssuePriority, IssueStatus, utcnow


def test_stats_empty_database(session: Session) -> None:
    stats = service.get_stats(session)
    assert stats.projects == 0
    assert stats.issues_total == 0
    assert stats.issues_by_status == {}
    assert stats.overdue == 0


def test_stats_counts(session: Session) -> None:
    project = create_project(session, ProjectCreate(name="P"))
    yesterday = utcnow() - timedelta(days=1)

    create_issue(session, IssueCreate(title="a", project_id=project.id))
    create_issue(
        session,
        IssueCreate(
            title="overdue",
            project_id=project.id,
            priority=IssuePriority.HIGH,
            due_date=yesterday,
        ),
    )
    done = create_issue(
        session, IssueCreate(title="closed overdue", project_id=project.id, due_date=yesterday)
    )
    change_status(session, done.id, IssueStatus.DONE)

    stats = service.get_stats(session)
    assert stats.projects == 1
    assert stats.issues_total == 3
    assert stats.issues_by_status["backlog"] == 2
    assert stats.issues_by_status["done"] == 1
    assert stats.issues_by_priority["high"] == 1
    # Closed issues don't count as overdue.
    assert stats.overdue == 1
    # 3 creates + 1 status change on issues, 1 project create.
    assert stats.activity_last_7_days == 5


def test_stats_over_http(client: TestClient) -> None:
    resp = client.get("/api/dashboard/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["projects"] == 0
    assert body["issues_total"] == 0
