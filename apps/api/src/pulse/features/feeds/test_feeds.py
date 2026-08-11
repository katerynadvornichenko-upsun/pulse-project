import uuid

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from pulse.features.feeds import service
from pulse.features.feeds.schemas import FeedSourceCreate, FeedSourceUpdate
from pulse.lib.errors import ConflictError, NotFoundError
from pulse.models import ActivityEvent, FeedItem, FeedKind, FeedSource


def test_create_and_list_sources(session: Session) -> None:
    service.create_source(
        session, FeedSourceCreate(name="zebra", kind=FeedKind.RSS, url="https://z.example/feed")
    )
    service.create_source(
        session,
        FeedSourceCreate(name="alpha", kind=FeedKind.GITHUB, url="https://github.com/a/b"),
    )
    sources = service.list_sources(session)
    assert [source.name for source in sources] == ["alpha", "zebra"]  # sorted by name


def test_duplicate_url_conflicts(session: Session) -> None:
    service.create_source(
        session, FeedSourceCreate(name="one", kind=FeedKind.RSS, url="https://dup.example/feed")
    )
    with pytest.raises(ConflictError):
        service.create_source(
            session,
            FeedSourceCreate(name="two", kind=FeedKind.RSS, url="https://dup.example/feed"),
        )


def test_duplicate_race_translates_integrity_error(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two concurrent creates can both pass the pre-commit SELECT check.

    Simulate the loser of that race by disabling the check: the DB unique
    index must still surface as ConflictError (409), not IntegrityError (500).
    """
    service.create_source(
        session, FeedSourceCreate(name="one", kind=FeedKind.RSS, url="https://race.example/feed")
    )
    monkeypatch.setattr(service, "_assert_url_free", lambda *a, **kw: None)
    with pytest.raises(ConflictError):
        service.create_source(
            session,
            FeedSourceCreate(name="two", kind=FeedKind.RSS, url="https://race.example/feed"),
        )


def test_create_records_activity_event(session: Session) -> None:
    source = service.create_source(
        session, FeedSourceCreate(name="one", kind=FeedKind.RSS, url="https://ev.example/feed")
    )
    events = session.exec(
        select(ActivityEvent).where(ActivityEvent.entity_type == "feed_source")
    ).all()
    assert len(events) == 1
    assert events[0].entity_id == source.id
    assert events[0].action == "created"


def test_create_and_list_over_http(client: TestClient) -> None:
    resp = client.post(
        "/api/feeds/sources",
        json={"name": "gh", "kind": "github", "url": "https://github.com/o/r"},
    )
    assert resp.status_code == 201
    source = resp.json()
    assert source["kind"] == "github"
    assert source["enabled"] is True

    # Duplicate url is a 409.
    dup = client.post(
        "/api/feeds/sources",
        json={"name": "gh2", "kind": "github", "url": "https://github.com/o/r"},
    )
    assert dup.status_code == 409

    # Unknown kind is a 422 via the enum.
    bad = client.post(
        "/api/feeds/sources",
        json={"name": "x", "kind": "twitter", "url": "https://x.example/feed"},
    )
    assert bad.status_code == 422

    listing = client.get("/api/feeds/sources")
    assert listing.status_code == 200
    assert [item["name"] for item in listing.json()] == ["gh"]


def test_overlong_url_rejected(client: TestClient) -> None:
    # Guards the Postgres unique-index byte limit: the schema caps url length
    # before it can reach an oversized index entry.
    resp = client.post(
        "/api/feeds/sources",
        json={"name": "long", "kind": "rss", "url": "https://x.example/" + "a" * 700},
    )
    assert resp.status_code == 422


def test_update_leaves_omitted_fields_unchanged(session: Session) -> None:
    source = service.create_source(
        session, FeedSourceCreate(name="one", kind=FeedKind.RSS, url="https://u.example/feed")
    )
    updated = service.update_source(session, source.id, FeedSourceUpdate(name="renamed"))
    assert updated.name == "renamed"
    # url, enabled and kind untouched.
    assert updated.url == "https://u.example/feed"
    assert updated.enabled is True
    assert updated.kind == FeedKind.RSS


def test_update_enabled_flag(session: Session) -> None:
    source = service.create_source(
        session, FeedSourceCreate(name="one", kind=FeedKind.RSS, url="https://e.example/feed")
    )
    updated = service.update_source(session, source.id, FeedSourceUpdate(enabled=False))
    assert updated.enabled is False
    assert updated.name == "one"


def test_update_url_to_same_value_is_not_a_conflict(session: Session) -> None:
    source = service.create_source(
        session, FeedSourceCreate(name="one", kind=FeedKind.RSS, url="https://same.example/feed")
    )
    updated = service.update_source(
        session, source.id, FeedSourceUpdate(url="https://same.example/feed", enabled=False)
    )
    assert updated.url == "https://same.example/feed"
    assert updated.enabled is False


def test_update_missing_id_raises_not_found(session: Session) -> None:
    with pytest.raises(NotFoundError):
        service.update_source(session, uuid.uuid4(), FeedSourceUpdate(name="x"))


def test_delete_missing_id_raises_not_found(session: Session) -> None:
    with pytest.raises(NotFoundError):
        service.delete_source(session, uuid.uuid4())


def test_update_records_activity_event(session: Session) -> None:
    source = service.create_source(
        session, FeedSourceCreate(name="one", kind=FeedKind.RSS, url="https://au.example/feed")
    )
    service.update_source(session, source.id, FeedSourceUpdate(name="two"))
    events = session.exec(
        select(ActivityEvent)
        .where(ActivityEvent.entity_type == "feed_source")
        .where(ActivityEvent.action == "updated")
    ).all()
    assert len(events) == 1
    assert events[0].entity_id == source.id


def test_noop_update_records_no_event(session: Session) -> None:
    source = service.create_source(
        session, FeedSourceCreate(name="one", kind=FeedKind.RSS, url="https://noop.example/feed")
    )
    # Empty PATCH body, and one that resets a field to its current value.
    service.update_source(session, source.id, FeedSourceUpdate())
    service.update_source(session, source.id, FeedSourceUpdate(name="one"))
    events = session.exec(
        select(ActivityEvent).where(ActivityEvent.action == "updated")
    ).all()
    assert events == []


def test_delete_records_activity_event(session: Session) -> None:
    source = service.create_source(
        session, FeedSourceCreate(name="one", kind=FeedKind.RSS, url="https://ad.example/feed")
    )
    service.delete_source(session, source.id)
    events = session.exec(
        select(ActivityEvent)
        .where(ActivityEvent.entity_type == "feed_source")
        .where(ActivityEvent.action == "deleted")
    ).all()
    assert len(events) == 1
    assert events[0].entity_id == source.id


def test_delete_cascades_to_items(session: Session) -> None:
    source = service.create_source(
        session, FeedSourceCreate(name="one", kind=FeedKind.RSS, url="https://c.example/feed")
    )
    session.add(
        FeedItem(
            source_id=source.id,
            external_id="ext-1",
            title="Item",
            url="https://c.example/item-1",
        )
    )
    session.commit()
    assert session.exec(select(FeedItem).where(FeedItem.source_id == source.id)).all()

    service.delete_source(session, source.id)

    assert session.get(FeedSource, source.id) is None
    # Removed by the ORM relationship's cascade_delete (models.py). The FK's
    # ondelete="CASCADE" backs this on Postgres but is inert on SQLite, where
    # FK enforcement is off, so this assertion exercises the ORM cascade.
    assert session.exec(select(FeedItem).where(FeedItem.source_id == source.id)).all() == []


def test_update_rename_url_conflict_over_http(client: TestClient) -> None:
    first = client.post(
        "/api/feeds/sources",
        json={"name": "one", "kind": "rss", "url": "https://one.example/feed"},
    ).json()
    client.post(
        "/api/feeds/sources",
        json={"name": "two", "kind": "rss", "url": "https://two.example/feed"},
    )

    # Renaming first's url onto two's url is a 409, and leaves first unchanged.
    resp = client.patch(
        f"/api/feeds/sources/{first['id']}",
        json={"url": "https://two.example/feed"},
    )
    assert resp.status_code == 409

    unchanged = client.get("/api/feeds/sources").json()
    urls = {item["url"] for item in unchanged}
    assert urls == {"https://one.example/feed", "https://two.example/feed"}


def test_update_null_field_rejected_over_http(client: TestClient) -> None:
    source = client.post(
        "/api/feeds/sources",
        json={"name": "one", "kind": "rss", "url": "https://null.example/feed"},
    ).json()
    for field in ("name", "url", "enabled"):
        resp = client.patch(f"/api/feeds/sources/{source['id']}", json={field: None})
        assert resp.status_code == 422, field


def test_update_unknown_field_rejected_over_http(client: TestClient) -> None:
    source = client.post(
        "/api/feeds/sources",
        json={"name": "one", "kind": "rss", "url": "https://extra.example/feed"},
    ).json()
    resp = client.patch(f"/api/feeds/sources/{source['id']}", json={"foo": 1})
    assert resp.status_code == 422


def test_update_missing_id_over_http(client: TestClient) -> None:
    resp = client.patch(f"/api/feeds/sources/{uuid.uuid4()}", json={"name": "x"})
    assert resp.status_code == 404


def test_delete_over_http(client: TestClient) -> None:
    source = client.post(
        "/api/feeds/sources",
        json={"name": "one", "kind": "rss", "url": "https://del.example/feed"},
    ).json()
    resp = client.delete(f"/api/feeds/sources/{source['id']}")
    assert resp.status_code == 204
    assert client.get("/api/feeds/sources").json() == []

    # Deleting an already-gone id is a 404.
    missing = client.delete(f"/api/feeds/sources/{source['id']}")
    assert missing.status_code == 404
