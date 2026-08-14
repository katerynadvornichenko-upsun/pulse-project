"""Tests for the feeds fetch worker job.

HTTP is stubbed with a tiny fake httpx client and Redis with an in-memory
fake. The job itself performs no DNS: resolution and IP pinning live in
GuardedTransport, which the injected fake client bypasses. The `no_dns`
fixture below enforces that, so the suite is genuinely hermetic rather than
quietly depending on how the host resolver answers example.com names.

Covers idempotent upsert on refetch, per-source failure isolation, redirect
handling, and cache content.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import cast

import httpx
import pytest
from redis import Redis
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
    """Stands in for httpx.Response, including the redirect surface the job
    inspects (`is_redirect`, `headers["location"]`, `url.join`)."""

    def __init__(
        self,
        *,
        content: bytes = b"",
        json_data=None,
        status_code: int = 200,
        location: str | None = None,
        request_url: str = "https://feeds.example.com/rss",
    ):
        self.content = content
        self._json = json_data
        self.status_code = status_code
        self.headers = {"location": location} if location else {}
        self.url = httpx.URL(request_url)

    @property
    def is_redirect(self) -> bool:
        return 300 <= self.status_code < 400 and "location" in self.headers

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


def as_client(fake: FakeClient) -> httpx.Client:
    """Present a test double as the real type the job's signature declares.

    The fakes implement only the surface the job uses; casting here keeps the
    production signatures honest instead of widening them for tests.
    """
    return cast(httpx.Client, fake)


def as_redis(fake: FakeRedis) -> Redis:
    return cast(Redis, fake)


@pytest.fixture(autouse=True)
def no_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if this suite ever reaches for the feed resolver.

    A real lookup would make these tests depend on the host's DNS: a resolver
    mapping example.com names to a private address would turn them red with
    UnsafeUrlError, and a slow one would add DNS_TIMEOUT_SECONDS per hop.

    Patches pulse's own resolution helper, not socket.getaddrinfo: the latter
    is a shared global, so blocking it would also break unrelated consumers
    that legitimately resolve (psycopg dialing localhost when the suite runs
    against PostgreSQL, as CI does).
    """

    def forbidden(hostname: str) -> list[tuple]:  # type: ignore[type-arg]
        raise AssertionError(f"feeds job tests must not resolve feed hostnames (got '{hostname}')")

    monkeypatch.setattr("pulse.lib.urls._getaddrinfo", forbidden)


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

    jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(FakeRedis())
    )
    assert len(_all_items(session)) == 3

    # Same stubbed response a second time: rows are matched by
    # (source_id, external_id) and updated in place, never re-inserted.
    jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(FakeRedis())
    )
    items = _all_items(session)
    assert len(items) == 3
    assert all(item.source_id == source.id for item in items)


def test_rss_refetch_produces_no_duplicates(session: Session) -> None:
    pytest.importorskip("feedparser")
    _add_source(session, "rss", FeedKind.RSS, RSS_URL)
    routes = {RSS_URL: FakeResponse(content=RSS_XML)}

    jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(FakeRedis())
    )
    first = _all_items(session)
    assert {item.external_id for item in first} == {"guid-1", "guid-2"}

    jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(FakeRedis())
    )
    assert len(_all_items(session)) == 2


def test_failing_source_does_not_abort_the_others(session: Session) -> None:
    good = _add_source(session, "good", FeedKind.GITHUB, GITHUB_URL)
    bad = _add_source(session, "bad", FeedKind.GITHUB, BAD_GITHUB_URL)
    routes = {
        GITHUB_EVENTS_URL: FakeResponse(json_data=_events(2)),
        BAD_GITHUB_EVENTS_URL: FakeResponse(status_code=500),
    }

    jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(FakeRedis())
    )

    items = _all_items(session)
    assert len(items) == 2
    assert {item.source_id for item in items} == {good.id}

    failures = list(
        session.exec(select(ActivityEvent).where(col(ActivityEvent.action) == "fetch_failed")).all()
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
    jobs.fetch_feeds_sync(session, client=as_client(client), redis_client=as_redis(FakeRedis()))

    assert _all_items(session) == []
    assert client.requested == []


def test_cache_holds_the_newest_items_with_ttl(session: Session) -> None:
    _add_source(session, "gh", FeedKind.GITHUB, GITHUB_URL)
    routes = {GITHUB_EVENTS_URL: FakeResponse(json_data=_events(60))}
    redis = FakeRedis()

    payload = jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(redis)
    )

    # All 60 upserted, but only the newest CACHE_LIMIT are cached.
    assert len(_all_items(session)) == 60
    assert len(payload) == jobs.CACHE_LIMIT

    raw = redis.get(jobs.CACHE_KEY)
    assert raw is not None
    cached = json.loads(raw)
    assert len(cached) == jobs.CACHE_LIMIT
    assert redis.ttls[jobs.CACHE_KEY] == jobs.CACHE_TTL_SECONDS

    # Newest first, and the oldest 10 events fell off the end.
    published = [entry["published_at"] for entry in cached]
    assert published == sorted(published, reverse=True)
    assert cached[0]["external_id"] == "e59"
    assert all(entry["external_id"] != "e0" for entry in cached)


RSS_UNDATED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Undated</title>
    <item>
      <title>No date</title>
      <link>https://example.com/undated</link>
      <guid>undated-1</guid>
      <description>No pubDate at all</description>
    </item>
  </channel>
</rss>
"""


def test_undated_items_do_not_re_bubble_on_refetch(session: Session) -> None:
    """fetched_at is first-seen only, so an undated entry keeps its place
    instead of floating above genuinely newer items every run."""
    _add_source(session, "undated", FeedKind.RSS, RSS_URL)
    routes = {RSS_URL: FakeResponse(content=RSS_UNDATED_XML)}

    jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(FakeRedis())
    )
    first_seen = _all_items(session)[0].fetched_at

    jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(FakeRedis())
    )
    item = _all_items(session)[0]
    assert item.fetched_at == first_seen


def test_successful_fetch_stamps_the_source(session: Session) -> None:
    source = _add_source(session, "gh", FeedKind.GITHUB, GITHUB_URL)
    assert source.last_fetched_at is None

    routes = {GITHUB_EVENTS_URL: FakeResponse(json_data=_events(1))}
    jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(FakeRedis())
    )

    session.refresh(source)
    assert source.last_fetched_at is not None


def test_failed_fetch_does_not_stamp_the_source(session: Session) -> None:
    source = _add_source(session, "bad", FeedKind.GITHUB, BAD_GITHUB_URL)
    routes = {BAD_GITHUB_EVENTS_URL: FakeResponse(status_code=500)}

    jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(FakeRedis())
    )

    session.refresh(source)
    assert source.last_fetched_at is None


def test_redirect_hops_are_followed_and_revalidated(session: Session) -> None:
    _add_source(session, "rss", FeedKind.RSS, RSS_URL)
    final = "https://elsewhere.example.com/real.xml"
    client = FakeClient(
        {
            RSS_URL: FakeResponse(status_code=302, location=final, request_url=RSS_URL),
            final: FakeResponse(content=RSS_XML),
        }
    )

    jobs.fetch_feeds_sync(session, client=as_client(client), redis_client=as_redis(FakeRedis()))

    assert client.requested == [RSS_URL, final]
    assert len(_all_items(session)) == 2


def test_redirect_into_private_space_is_refused(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A public URL must not be able to 302 the worker into the private
    network: the hop is validated before it is requested."""
    _add_source(session, "rss", FeedKind.RSS, RSS_URL)
    internal = "http://169.254.169.254/latest/meta-data/"
    client = FakeClient(
        {
            RSS_URL: FakeResponse(status_code=302, location=internal, request_url=RSS_URL),
            internal: FakeResponse(content=b"secrets"),
        }
    )

    jobs.fetch_feeds_sync(session, client=as_client(client), redis_client=as_redis(FakeRedis()))

    # The internal hop was never requested, and the source is marked failed.
    assert client.requested == [RSS_URL]
    assert _all_items(session) == []
    failures = session.exec(
        select(ActivityEvent).where(col(ActivityEvent.action) == "fetch_failed")
    ).all()
    assert len(failures) == 1


def test_unhandled_3xx_is_a_failure_not_an_empty_success(session: Session) -> None:
    """A 300/305/306, or a 3xx without Location, must not read as a clean
    poll: raise_for_status ignores 3xx, so the body would parse as zero
    entries and the source would be stamped as successfully fetched."""
    source = _add_source(session, "rss", FeedKind.RSS, RSS_URL)
    client = FakeClient({RSS_URL: FakeResponse(status_code=300, request_url=RSS_URL)})

    jobs.fetch_feeds_sync(session, client=as_client(client), redis_client=as_redis(FakeRedis()))

    session.refresh(source)
    assert source.last_fetched_at is None
    failures = session.exec(
        select(ActivityEvent).where(col(ActivityEvent.action) == "fetch_failed")
    ).all()
    assert len(failures) == 1
    assert "300" in failures[0].message


def test_github_object_payload_reports_a_shape_mismatch(session: Session) -> None:
    """The events API answers with an object on error; the message should say
    so rather than surfacing an AttributeError from iterating string keys."""
    _add_source(session, "gh", FeedKind.GITHUB, GITHUB_URL)
    routes = {GITHUB_EVENTS_URL: FakeResponse(json_data={"message": "API rate limit exceeded"})}

    jobs.fetch_feeds_sync(
        session, client=as_client(FakeClient(routes)), redis_client=as_redis(FakeRedis())
    )

    failure = session.exec(
        select(ActivityEvent).where(col(ActivityEvent.action) == "fetch_failed")
    ).one()
    assert "expected a JSON array" in failure.message
    assert "rate limit" in failure.message
    assert "AttributeError" not in failure.message


def test_relative_redirect_keeps_the_original_hostname(session: Session) -> None:
    """The guarded transport rewrites the request URL to the pinned IP, so
    response.url carries an address. A relative Location must still resolve
    against the hostname we asked for, or the next hop loses vhost routing."""
    _add_source(session, "rss", FeedKind.RSS, RSS_URL)
    expected_hop = "https://feeds.example.com/real.xml"
    client = FakeClient(
        {
            # request_url mimics the pinned rewrite the transport performs.
            RSS_URL: FakeResponse(
                status_code=302,
                location="/real.xml",
                request_url="https://93.184.216.34/rss",
            ),
            expected_hop: FakeResponse(content=RSS_XML),
        }
    )

    jobs.fetch_feeds_sync(session, client=as_client(client), redis_client=as_redis(FakeRedis()))

    assert client.requested == [RSS_URL, expected_hop]
    assert len(_all_items(session)) == 2


def test_over_redirecting_is_not_reported_as_an_ssrf_rejection(session: Session) -> None:
    _add_source(session, "rss", FeedKind.RSS, RSS_URL)
    # A loop: every hop redirects back to the same place.
    client = FakeClient(
        {RSS_URL: FakeResponse(status_code=302, location=RSS_URL, request_url=RSS_URL)}
    )

    jobs.fetch_feeds_sync(session, client=as_client(client), redis_client=as_redis(FakeRedis()))

    failure = session.exec(
        select(ActivityEvent).where(col(ActivityEvent.action) == "fetch_failed")
    ).one()
    assert "too many redirects" in failure.message
