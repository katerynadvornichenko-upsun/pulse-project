import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from pulse.features.issues import service
from pulse.features.issues.schemas import IssueCreate, IssueUpdate
from pulse.features.projects.schemas import ProjectCreate
from pulse.features.projects.service import create_project
from pulse.lib.errors import NotFoundError
from pulse.models import ActivityEvent, Issue, IssuePriority, IssueStatus, Project


@pytest.fixture
def project(session: Session) -> Project:
    return create_project(session, ProjectCreate(name="Test project"))


def make_issue(
    session: Session,
    project: Project,
    title: str = "An issue",
    status: IssueStatus = IssueStatus.BACKLOG,
    priority: IssuePriority = IssuePriority.MEDIUM,
) -> Issue:
    return service.create_issue(
        session,
        IssueCreate(title=title, project_id=project.id, status=status, priority=priority),
    )


def test_create_and_get_issue(session: Session, project: Project) -> None:
    issue = make_issue(session, project, title="Fix login")
    fetched = service.get_issue(session, issue.id)
    assert fetched.title == "Fix login"
    assert fetched.status == IssueStatus.BACKLOG
    assert fetched.priority == IssuePriority.MEDIUM
    assert fetched.project_id == project.id


def test_create_issue_missing_project_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        service.create_issue(
            session, IssueCreate(title="Orphan", project_id=uuid.uuid4())
        )


def test_get_missing_issue_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        service.get_issue(session, uuid.uuid4())


def test_create_records_activity_event(session: Session, project: Project) -> None:
    issue = make_issue(session, project)
    events = session.exec(
        select(ActivityEvent).where(ActivityEvent.entity_type == "issue")
    ).all()
    assert len(events) == 1
    assert events[0].entity_id == issue.id
    assert events[0].action == "created"


def test_update_issue(session: Session, project: Project) -> None:
    issue = make_issue(session, project)
    updated = service.update_issue(
        session, issue.id, IssueUpdate(priority=IssuePriority.URGENT)
    )
    assert updated.priority == IssuePriority.URGENT
    assert updated.title == "An issue"


def test_filters(session: Session, project: Project) -> None:
    other = create_project(session, ProjectCreate(name="Other"))
    make_issue(session, project, title="A", status=IssueStatus.TODO)
    make_issue(session, project, title="B", priority=IssuePriority.HIGH)
    make_issue(session, other, title="C", status=IssueStatus.TODO)

    by_project = service.list_issues(session, project_id=project.id)
    assert [i.title for i in by_project] == ["A", "B"]

    by_status = service.list_issues(session, status=IssueStatus.TODO)
    assert [i.title for i in by_status] == ["A", "C"]

    by_priority = service.list_issues(session, priority=IssuePriority.HIGH)
    assert [i.title for i in by_priority] == ["B"]

    combined = service.list_issues(
        session, project_id=project.id, status=IssueStatus.TODO
    )
    assert [i.title for i in combined] == ["A"]


def test_crud_over_http(client: TestClient) -> None:
    project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]

    resp = client.post(
        "/api/issues",
        json={"title": "Ship it", "project_id": project_id, "priority": "high"},
    )
    assert resp.status_code == 201
    issue = resp.json()
    assert issue["status"] == "backlog"
    assert issue["priority"] == "high"

    resp = client.get("/api/issues", params={"project_id": project_id})
    assert resp.status_code == 200
    assert [i["id"] for i in resp.json()] == [issue["id"]]

    resp = client.patch(f"/api/issues/{issue['id']}", json={"title": "Shipped"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Shipped"

    resp = client.delete(f"/api/issues/{issue['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/issues/{issue['id']}").status_code == 404


def test_close_sets_closed_at_and_reopen_clears_it(
    session: Session, project: Project
) -> None:
    issue = make_issue(session, project, status=IssueStatus.IN_PROGRESS)
    assert issue.closed_at is None

    closed = service.change_status(session, issue.id, IssueStatus.DONE)
    assert closed.closed_at is not None
    assert closed.status == IssueStatus.DONE

    reopened = service.change_status(session, issue.id, IssueStatus.TODO)
    assert reopened.closed_at is None
    assert reopened.status == IssueStatus.TODO


def test_status_change_records_transition_message(
    session: Session, project: Project
) -> None:
    issue = make_issue(session, project, title="Fix login", status=IssueStatus.TODO)
    service.change_status(session, issue.id, IssueStatus.IN_PROGRESS)
    event = session.exec(
        select(ActivityEvent).where(ActivityEvent.action == "status_changed")
    ).one()
    assert event.message == "Issue 'Fix login' moved from todo to in_progress"


def test_status_change_missing_issue_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        service.change_status(session, uuid.uuid4(), IssueStatus.DONE)


def test_status_endpoint_over_http(client: TestClient) -> None:
    project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
    issue = client.post(
        "/api/issues", json={"title": "Ship it", "project_id": project_id}
    ).json()

    resp = client.post(f"/api/issues/{issue['id']}/status", json={"status": "done"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
    assert resp.json()["closed_at"] is not None

    resp = client.post(f"/api/issues/{issue['id']}/status", json={"status": "nonsense"})
    assert resp.status_code == 422


def test_patch_no_longer_accepts_status(client: TestClient) -> None:
    project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
    issue = client.post(
        "/api/issues", json={"title": "Stubborn", "project_id": project_id}
    ).json()

    resp = client.patch(f"/api/issues/{issue['id']}", json={"status": "done"})
    assert resp.status_code == 422
    assert client.get(f"/api/issues/{issue['id']}").json()["status"] == "backlog"


def test_patch_null_clears_due_date(client: TestClient) -> None:
    project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
    issue = client.post(
        "/api/issues",
        json={
            "title": "Dated",
            "project_id": project_id,
            "due_date": "2026-07-10T12:00:00Z",
        },
    ).json()
    assert issue["due_date"] is not None

    resp = client.patch(f"/api/issues/{issue['id']}", json={"due_date": None})
    assert resp.status_code == 200
    assert resp.json()["due_date"] is None


def test_patch_null_rejected_for_non_nullable_fields(client: TestClient) -> None:
    project_id = client.post("/api/projects", json={"name": "P"}).json()["id"]
    issue = client.post(
        "/api/issues", json={"title": "Solid", "project_id": project_id}
    ).json()

    resp = client.patch(f"/api/issues/{issue['id']}", json={"title": None})
    assert resp.status_code == 422
    # And the value is untouched.
    assert client.get(f"/api/issues/{issue['id']}").json()["title"] == "Solid"


def test_create_against_missing_project_is_404(client: TestClient) -> None:
    resp = client.post(
        "/api/issues", json={"title": "Orphan", "project_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404


def test_validation_rejects_empty_title(client: TestClient) -> None:
    resp = client.post("/api/issues", json={"title": "", "project_id": str(uuid.uuid4())})
    assert resp.status_code == 422


def test_invalid_status_filter_rejected(client: TestClient) -> None:
    resp = client.get("/api/issues", params={"status": "nonsense"})
    assert resp.status_code == 422
