"""Tests for the feed items read path (GET /api/feeds/items).

The endpoint serves the newest items from the Redis cache when warm and falls
back to the database on a cold cache. Redis is faked in-memory here; the
`client` fixture has no real replica, so the DB fallback runs against the same
test engine (see conftest.py).
"""

import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import cast

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from sqlmodel import Session

from pulse.features.feeds import service
from pulse.features.feeds.schemas import FeedItemRead
from pulse.models import FeedItem, FeedKind, FeedSource


class FakeRedis:
    """Duck-typed stand-in for redis.Redis exposing only .get()."""

    def __init__(self, data: dict[str, str] | None = None) -> None:
        self._data = data or {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)


def as_redis(fake: FakeRedis) -> Redis:
    """Present the test double as the real type the service declares (the
    AGENTS.md convention; see the feeds job tests for the original)."""
    return cast(Redis, fake)


def _add_source(session: Session, name: str) -> FeedSource:
    source = FeedSource(name=name, kind=FeedKind.RSS, url=f"https://{name}.example/feed")
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def _add_item(
    session: Session,
    source: FeedSource,
    *,
    external_id: str,
    title: str,
    published_at: datetime | None,
) -> FeedItem:
    item = FeedItem(
        source_id=source.id,
        external_id=external_id,
        title=title,
        url=f"https://{source.name}.example/{external_id}",
        summary="",
        published_at=published_at,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def _cache_payload(entries: Sequence[Mapping[str, object]]) -> dict[str, str]:
    # Sequence/Mapping (covariant) rather than list/dict (invariant), so
    # callers can pass list[dict[str, str]] without a cast.
    from pulse.features.feeds.jobs import CACHE_KEY

    return {CACHE_KEY: json.dumps(entries)}


def test_warm_cache_is_served_without_touching_the_db(session: Session) -> None:
    # Cache holds an item that does not exist in the DB; if the cache is used,
    # we get it back, proving the DB was not consulted.
    entry = {
        "id": str(uuid.uuid4()),
        "source_id": str(uuid.uuid4()),
        "source_name": "Cached Source",
        "external_id": "c-1",
        "title": "Only in the cache",
        "url": "https://cache.example/1",
        "summary": "",
        "published_at": "2026-01-02T00:00:00+00:00",
        "fetched_at": "2026-01-02T00:00:00+00:00",
    }
    redis = FakeRedis(_cache_payload([entry]))

    items = service.list_latest_items(session, 20, redis_client=as_redis(redis))

    assert [item.title for item in items] == ["Only in the cache"]
    assert items[0].source_name == "Cached Source"


def test_warm_cache_respects_limit(session: Session) -> None:
    entries = [
        {
            "id": str(uuid.uuid4()),
            "source_id": str(uuid.uuid4()),
            "source_name": "S",
            "external_id": f"c-{n}",
            "title": f"item-{n}",
            "url": f"https://cache.example/{n}",
            "summary": "",
            "published_at": f"2026-01-{n + 1:02d}T00:00:00+00:00",
            "fetched_at": f"2026-01-{n + 1:02d}T00:00:00+00:00",
        }
        for n in range(5)
    ]
    redis = FakeRedis(_cache_payload(entries))

    items = service.list_latest_items(session, 2, redis_client=as_redis(redis))

    assert [item.title for item in items] == ["item-0", "item-1"]


def test_cold_cache_falls_back_to_db_ordered_newest_first(session: Session) -> None:
    source = _add_source(session, "src")
    _add_item(
        session,
        source,
        external_id="old",
        title="Older",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    _add_item(
        session,
        source,
        external_id="new",
        title="Newer",
        published_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
    )

    # Empty cache -> DB fallback.
    items = service.list_latest_items(session, 20, redis_client=as_redis(FakeRedis()))

    assert [item.title for item in items] == ["Newer", "Older"]
    assert items[0].source_name == "src"


def test_cold_cache_tiebreaks_on_id_desc(session: Session) -> None:
    source = _add_source(session, "src")
    shared = datetime(2026, 3, 1, tzinfo=timezone.utc)
    a = _add_item(session, source, external_id="a", title="A", published_at=shared)
    b = _add_item(session, source, external_id="b", title="B", published_at=shared)

    items = service.list_latest_items(session, 20, redis_client=as_redis(FakeRedis()))

    expected = sorted([a, b], key=lambda item: item.id, reverse=True)
    assert [item.id for item in items] == [item.id for item in expected]


def test_db_fallback_respects_limit(session: Session) -> None:
    source = _add_source(session, "src")
    for n in range(5):
        _add_item(
            session,
            source,
            external_id=f"e-{n}",
            title=f"item-{n}",
            published_at=datetime(2026, 1, n + 1, tzinfo=timezone.utc),
        )

    items = service.list_latest_items(session, 3, redis_client=as_redis(FakeRedis()))

    assert len(items) == 3
    assert [item.title for item in items] == ["item-4", "item-3", "item-2"]


def _stub_cache(monkeypatch: pytest.MonkeyPatch, redis: FakeRedis) -> None:
    monkeypatch.setattr(service, "get_redis", lambda: redis)


def test_items_over_http_uses_db_on_cold_cache(
    client: TestClient, session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_cache(monkeypatch, FakeRedis())
    source = _add_source(session, "src")
    _add_item(
        session,
        source,
        external_id="e-1",
        title="Hello",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    resp = client.get("/api/feeds/items")
    assert resp.status_code == 200
    body = resp.json()
    assert [item["title"] for item in body] == ["Hello"]
    assert body[0]["source_name"] == "src"


def test_items_over_http_empty_when_no_items(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_cache(monkeypatch, FakeRedis())
    resp = client.get("/api/feeds/items")
    assert resp.status_code == 200
    assert resp.json() == []


def test_items_limit_bounds(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_cache(monkeypatch, FakeRedis())
    # Default and in-range are fine.
    assert client.get("/api/feeds/items").status_code == 200
    assert client.get("/api/feeds/items?limit=100").status_code == 200
    # Out of range is rejected by the Query bounds (ge=1, le=100).
    assert client.get("/api/feeds/items?limit=0").status_code == 422
    assert client.get("/api/feeds/items?limit=101").status_code == 422


# --- Warm and cold paths agree (PR #21 review) --------------------------------


def _warm(session: Session) -> FakeRedis:
    """Build the cache exactly as the warming job does, from current DB rows."""
    from pulse.features.feeds.jobs import CACHE_KEY, _latest_payload

    return FakeRedis({CACHE_KEY: json.dumps(_latest_payload(session))})


def _ids(items: Sequence[FeedItemRead]) -> list[uuid.UUID]:
    return [item.id for item in items]


def test_warm_and_cold_return_the_same_items_including_undated(session: Session) -> None:
    """Both paths share one ordering, so the top-N cannot depend on whether
    the cache happens to be warm. Undated items rank by fetch time on both
    (no reliance on backend NULL placement, which differs on PostgreSQL)."""
    source = _add_source(session, "src")
    for n in range(4):
        _add_item(
            session,
            source,
            external_id=f"dated-{n}",
            title=f"dated-{n}",
            published_at=datetime(2026, 1, n + 1, tzinfo=timezone.utc),
        )
    for n in range(3):
        _add_item(
            session, source, external_id=f"undated-{n}", title=f"undated-{n}", published_at=None
        )

    for limit in (1, 3, 5, 7, 20):
        warm = service.list_latest_items(session, limit, redis_client=as_redis(_warm(session)))
        cold = service.list_latest_items(session, limit, redis_client=as_redis(FakeRedis()))
        assert _ids(warm) == _ids(cold), f"warm/cold diverge at limit={limit}"


def test_warm_cache_serves_every_limit_the_endpoint_accepts(session: Session) -> None:
    """The cache holds as many items as the endpoint's maximum limit, so a
    large request returns the same count warm or cold."""
    from pulse.features.feeds.jobs import CACHE_LIMIT

    source = _add_source(session, "src")
    for n in range(CACHE_LIMIT):
        _add_item(
            session,
            source,
            external_id=f"e-{n}",
            title=f"item-{n}",
            published_at=datetime(2026, 1, 1, tzinfo=timezone.utc).replace(
                minute=n % 60, hour=n // 60
            ),
        )

    warm = service.list_latest_items(session, CACHE_LIMIT, redis_client=as_redis(_warm(session)))
    cold = service.list_latest_items(session, CACHE_LIMIT, redis_client=as_redis(FakeRedis()))
    assert len(warm) == len(cold) == CACHE_LIMIT
    assert _ids(warm) == _ids(cold)


def test_endpoint_limit_bound_matches_the_cache_size(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pulse.features.feeds.jobs import CACHE_LIMIT

    _stub_cache(monkeypatch, FakeRedis())
    assert client.get(f"/api/feeds/items?limit={CACHE_LIMIT}").status_code == 200
    assert client.get(f"/api/feeds/items?limit={CACHE_LIMIT + 1}").status_code == 422


def test_cache_warming_does_not_lazy_load_sources(session: Session) -> None:
    """One query for the whole payload, not one per item (N+1)."""
    from sqlalchemy import event

    from pulse.features.feeds.jobs import _latest_payload

    for n in range(3):
        source = _add_source(session, f"src{n}")
        _add_item(session, source, external_id="e", title=f"t{n}", published_at=None)
    session.expire_all()  # as after the job's per-source commits

    statements: list[str] = []
    engine = session.get_bind()

    def count(conn: object, cursor: object, statement: str, *args: object) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        payload = _latest_payload(session)
    finally:
        event.remove(engine, "before_cursor_execute", count)

    assert len(payload) == 3
    assert {entry["source_name"] for entry in payload} == {"src0", "src1", "src2"}
    assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == 1


# --- Item links are untrusted (stored-XSS guard) -------------------------------


@pytest.mark.parametrize(
    "link",
    [
        "javascript:alert(document.cookie)",
        " JavaScript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "vbscript:msgbox(1)",
        "relative/path",
    ],
)
def test_non_web_item_links_are_blanked(session: Session, link: str) -> None:
    source = _add_source(session, "src")
    item = _add_item(session, source, external_id="x", title="Evil", published_at=None)
    item.url = link
    session.add(item)
    session.commit()

    cold = service.list_latest_items(session, 20, redis_client=as_redis(FakeRedis()))
    # The warm path validates the cached JSON through the same schema.
    warm = service.list_latest_items(session, 20, redis_client=as_redis(_warm(session)))

    assert cold[0].url == "" and warm[0].url == ""


def test_web_item_links_are_kept(session: Session) -> None:
    source = _add_source(session, "src")
    _add_item(session, source, external_id="ok", title="Fine", published_at=None)
    items = service.list_latest_items(session, 20, redis_client=as_redis(FakeRedis()))
    assert items[0].url == "https://src.example/ok"
