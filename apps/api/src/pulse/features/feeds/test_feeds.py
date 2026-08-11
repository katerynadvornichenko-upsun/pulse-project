import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from pulse.features.feeds import service
from pulse.features.feeds.schemas import FeedSourceCreate
from pulse.lib.errors import ConflictError
from pulse.models import ActivityEvent, FeedKind


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
