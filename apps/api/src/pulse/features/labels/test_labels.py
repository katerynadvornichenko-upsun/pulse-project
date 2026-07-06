import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from pulse.features.labels import service
from pulse.features.labels.schemas import LabelCreate, LabelUpdate
from pulse.lib.errors import ConflictError, NotFoundError
from pulse.models import ActivityEvent


def test_create_and_list_labels(session: Session) -> None:
    service.create_label(session, LabelCreate(name="bug", color="#ff0000"))
    service.create_label(session, LabelCreate(name="api"))
    labels = service.list_labels(session)
    assert [label.name for label in labels] == ["api", "bug"]  # sorted by name


def test_duplicate_name_conflicts(session: Session) -> None:
    service.create_label(session, LabelCreate(name="bug"))
    with pytest.raises(ConflictError):
        service.create_label(session, LabelCreate(name="bug"))


def test_duplicate_race_translates_integrity_error(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two concurrent creates can both pass the pre-commit SELECT check.

    Simulate the loser of that race by disabling the check: the DB unique
    index must still surface as ConflictError (409), not IntegrityError (500).
    """
    service.create_label(session, LabelCreate(name="bug"))
    monkeypatch.setattr(service, "_assert_name_free", lambda *a, **kw: None)
    with pytest.raises(ConflictError):
        service.create_label(session, LabelCreate(name="bug"))


def test_rename_to_existing_name_conflicts(session: Session) -> None:
    service.create_label(session, LabelCreate(name="bug"))
    feature = service.create_label(session, LabelCreate(name="feature"))
    with pytest.raises(ConflictError):
        service.update_label(session, feature.id, LabelUpdate(name="bug"))
    # Renaming to its own current name is not a conflict.
    updated = service.update_label(session, feature.id, LabelUpdate(name="feature"))
    assert updated.name == "feature"


def test_delete_missing_label_raises(session: Session) -> None:
    with pytest.raises(NotFoundError):
        service.delete_label(session, uuid.uuid4())


def test_create_records_activity_event(session: Session) -> None:
    label = service.create_label(session, LabelCreate(name="bug"))
    events = session.exec(
        select(ActivityEvent).where(ActivityEvent.entity_type == "label")
    ).all()
    assert len(events) == 1
    assert events[0].entity_id == label.id
    assert events[0].action == "created"


def test_crud_over_http(client: TestClient) -> None:
    resp = client.post("/api/labels", json={"name": "bug", "color": "#ff0000"})
    assert resp.status_code == 201
    label = resp.json()

    assert client.post("/api/labels", json={"name": "bug"}).status_code == 409

    resp = client.patch(f"/api/labels/{label['id']}", json={"color": "#00ff00"})
    assert resp.status_code == 200
    assert resp.json()["color"] == "#00ff00"

    assert client.post("/api/labels", json={"name": "x", "color": "red"}).status_code == 422

    resp = client.delete(f"/api/labels/{label['id']}")
    assert resp.status_code == 204
    assert client.get("/api/labels").json() == []
