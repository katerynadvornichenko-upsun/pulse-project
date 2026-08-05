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


def test_activity_newest_first_with_limit(session: Session) -> None:
    import uuid

    from pulse.models import ActivityEvent

    now = utcnow()
    for hours_ago, message in [(3, "oldest"), (2, "middle"), (1, "newest")]:
        session.add(
            ActivityEvent(
                entity_type="test",
                entity_id=uuid.uuid4(),
                action="created",
                message=message,
                created_at=now - timedelta(hours=hours_ago),
            )
        )
    session.commit()

    recent = service.list_recent_activity(session, limit=2)
    assert [event.message for event in recent] == ["newest", "middle"]


def test_activity_tied_timestamps_are_stable(session: Session) -> None:
    import uuid

    from pulse.models import ActivityEvent

    tied = utcnow()
    for i in range(5):
        session.add(
            ActivityEvent(
                entity_type="test",
                entity_id=uuid.uuid4(),
                action="created",
                message=f"tied-{i}",
                created_at=tied,
            )
        )
    session.commit()

    first = [event.id for event in service.list_recent_activity(session, limit=3)]
    second = [event.id for event in service.list_recent_activity(session, limit=3)]
    assert first == second
    # The two beyond the limit are exactly the ones ranked below the cut.
    full = [event.id for event in service.list_recent_activity(session, limit=5)]
    assert full[:3] == first


def test_activity_over_http_validates_limit(client: TestClient) -> None:
    project = client.post("/api/projects", json={"name": "P"}).json()
    resp = client.get("/api/dashboard/activity")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 1
    assert events[0]["entity_id"] == project["id"]
    assert events[0]["action"] == "created"

    assert client.get("/api/dashboard/activity", params={"limit": 0}).status_code == 422
    assert client.get("/api/dashboard/activity", params={"limit": 101}).status_code == 422
