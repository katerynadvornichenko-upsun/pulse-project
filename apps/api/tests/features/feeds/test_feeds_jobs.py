"""Tests for the feeds fetch worker job.

HTTP is stubbed with a tiny fake httpx client and Redis with an in-memory
fake, so the suite is deterministic and offline. Covers idempotent upsert on
refetch, per-source failure isolation, and cache content.
"""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlmodel import Session, col, select

from pulse.features.feeds import jobs
from pulse.models import ActivityEvent, FeedItem, FeedKind, FeedSource

RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example</title>
    <item>
      <title>First post</title>
      <link>https://example.com/1</link>
      <guid>guid-1</guid>
      <description>Body one</description>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Second post</title>
      <link>https://example.com/2</link>
      <guid>guid-2</guid>
      <description>Body two</description>
      <pubDate>Tue, 02 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

RSS_URL = "https://feeds.example.com/rss"
GITHUB_URL = "https://github.com/octo/repo"
GITHUB_EVENTS_URL = "https://api.github.com/repos/octo/repo/events"
BAD_GITHUB_URL = "https://github.com/bad/repo"
BAD_GITHUB_EVENTS_URL = "https://api.github.com/repos/bad/repo/events"


def _events(count: int, prefix: str = "e") -> list[dict]:
    """Build GitHub-events-API-shaped payload with strictly increasing dates."""
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "id": f"{prefix}{i}",
            "type": "PushEvent",
            "repo": {"name": "octo/repo"},
            "actor": {"login": "octo"},
            "created_at": (base + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        for i in range(count)
    ]


class FakeResponse:
    def __init__(self, *, content: bytes = b"", json_data=None, status_code: int = 200):
        self.content = content
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeClient:
    """Serves canned responses keyed by requested URL."""

    def __init__(self, routes: dict[str, FakeResponse]):
        self.routes = routes
        self.requested: list[str] = []

    def get(self, url: str, **_: object) -> FakeResponse:
        self.requested.append(url)
        return self.routes[url]

    def close(self) -> None:
        pass


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        self.ttls[key] = ex

    def get(self, key: str) -> str | None:
        return self.store.get(key)


def _add_source(session: Session, name: str, kind: FeedKind, url: str) -> FeedSource:
    source = FeedSource(name=name, kind=kind, url=url)
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def _all_items(session: Session) -> list[FeedItem]:
    return list(session.exec(select(FeedItem)).all())


def test_github_refetch_produces_no_duplicates(session: Session) -> None:
    source = _add_source(session, "gh", FeedKind.GITHUB, GITHUB_URL)
    routes = {GITHUB_EVENTS_URL: FakeResponse(json_data=_events(3))}

    jobs.fetch_feeds_sync(session, client=FakeClient(routes), redis_client=FakeRedis())
    assert len(_all_items(session)) == 3

    # Same stubbed response a second time: rows are matched by
    # (source_id, external_id) and updated in place, never re-inserted.
    jobs.fetch_feeds_sync(session, client=FakeClient(routes), redis_client=FakeRedis())
    items = _all_items(session)
    assert len(items) == 3
    assert all(item.source_id == source.id for item in items)


def test_rss_refetch_produces_no_duplicates(session: Session) -> None:
    pytest.importorskip("feedparser")
    _add_source(session, "rss", FeedKind.RSS, RSS_URL)
    routes = {RSS_URL: FakeResponse(content=RSS_XML)}

    jobs.fetch_feeds_sync(session, client=FakeClient(routes), redis_client=FakeRedis())
    first = _all_items(session)
    assert {item.external_id for item in first} == {"guid-1", "guid-2"}

    jobs.fetch_feeds_sync(session, client=FakeClient(routes), redis_client=FakeRedis())
    assert len(_all_items(session)) == 2


def test_failing_source_does_not_abort_the_others(session: Session) -> None:
    good = _add_source(session, "good", FeedKind.GITHUB, GITHUB_URL)
    bad = _add_source(session, "bad", FeedKind.GITHUB, BAD_GITHUB_URL)
    routes = {
        GITHUB_EVENTS_URL: FakeResponse(json_data=_events(2)),
        BAD_GITHUB_EVENTS_URL: FakeResponse(status_code=500),
    }

    jobs.fetch_feeds_sync(session, client=FakeClient(routes), redis_client=FakeRedis())

    items = _all_items(session)
    assert len(items) == 2
    assert {item.source_id for item in items} == {good.id}

    failures = list(
        session.exec(
            select(ActivityEvent).where(col(ActivityEvent.action) == "fetch_failed")
        ).all()
    )
    assert len(failures) == 1
    assert failures[0].entity_id == bad.id
    assert failures[0].entity_type == "feed_source"


def test_disabled_sources_are_skipped(session: Session) -> None:
    source = _add_source(session, "off", FeedKind.GITHUB, GITHUB_URL)
    source.enabled = False
    session.add(source)
    session.commit()

    client = FakeClient({GITHUB_EVENTS_URL: FakeResponse(json_data=_events(2))})
    jobs.fetch_feeds_sync(session, client=client, redis_client=FakeRedis())

    assert _all_items(session) == []
    assert client.requested == []


def test_cache_holds_the_newest_items_with_ttl(session: Session) -> None:
    _add_source(session, "gh", FeedKind.GITHUB, GITHUB_URL)
    routes = {GITHUB_EVENTS_URL: FakeResponse(json_data=_events(60))}
    redis = FakeRedis()

    payload = jobs.fetch_feeds_sync(session, client=FakeClient(routes), redis_client=redis)

    # All 60 upserted, but only the newest CACHE_LIMIT are cached.
    assert len(_all_items(session)) == 60
    assert len(payload) == jobs.CACHE_LIMIT

    cached = json.loads(redis.get(jobs.CACHE_KEY))
    assert len(cached) == jobs.CACHE_LIMIT
    assert redis.ttls[jobs.CACHE_KEY] == jobs.CACHE_TTL_SECONDS

    # Newest first, and the oldest 10 events fell off the end.
    published = [entry["published_at"] for entry in cached]
    assert published == sorted(published, reverse=True)
    assert cached[0]["external_id"] == "e59"
    assert all(entry["external_id"] != "e0" for entry in cached)
