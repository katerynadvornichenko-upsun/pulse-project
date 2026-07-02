import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from pulse.features.projects import service
from pulse.features.projects.schemas import ProjectCreate
from pulse.lib.errors import NotFoundError
from pulse.models import ActivityEvent


def test_create_and_get_project(session: Session) -> None:
    project = service.create_project(session, ProjectCreate(name="Pulse", description="d"))
    fetched = service.get_project(session, project.id)
    assert fetched.name == "Pulse"
    assert fetched.description == "d"


def test_create_records_activity_event(session: Session) -> None:
    project = service.create_project(session, ProjectCreate(name="Pulse"))
    events = session.exec(select(ActivityEvent)).all()
    assert len(events) == 1
    assert events[0].entity_id == project.id
    assert events[0].action == "created"


def test_get_missing_project_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        service.get_project(session, uuid.uuid4())


def test_crud_over_http(client: TestClient) -> None:
    # create
    resp = client.post("/api/projects", json={"name": "Alpha", "description": "first"})
    assert resp.status_code == 201
    project = resp.json()

    # list
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert [p["id"] for p in resp.json()] == [project["id"]]

    # update
    resp = client.patch(f"/api/projects/{project['id']}", json={"name": "Beta"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Beta"
    assert resp.json()["description"] == "first"

    # delete
    resp = client.delete(f"/api/projects/{project['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_validation_rejects_empty_name(client: TestClient) -> None:
    resp = client.post("/api/projects", json={"name": ""})
    assert resp.status_code == 422
