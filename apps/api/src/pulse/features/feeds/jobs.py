"""Background jobs owned by the feeds slice.

The sync core (`fetch_feeds_sync`) is plain service code, testable with the
`session` fixture and a stubbed HTTP client / fake Redis; the async wrapper at
the bottom is what the ARQ worker registers.

The job walks every enabled FeedSource, pulls its latest activity (RSS via
feedparser, GitHub via the unauthenticated repo events API), upserts the
results as FeedItems keyed by (source_id, external_id) so a refetch never
duplicates rows, and caches the newest items as JSON in Redis for the
dashboard endpoint to read.
"""

import asyncio
import calendar
import contextlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from time import struct_time
from typing import Any
from urllib.parse import urlparse

import httpx
from redis import Redis, RedisError
from sqlalchemy import func
from sqlmodel import Session, col, select

from pulse.lib.db import get_engine
from pulse.lib.redis import get_redis
from pulse.models import ActivityEvent, FeedItem, FeedKind, FeedSource, utcnow

# Redis key the dashboard endpoint (next slice) reads the cached feed from.
CACHE_KEY = "feeds:latest"
# How many of the newest items to cache.
CACHE_LIMIT = 50
# TTL for the cache entry; matches the hourly refresh cadence with headroom so
# a skipped run still serves slightly-stale data rather than nothing.
CACHE_TTL_SECONDS = 60 * 90
# Per-request network timeout for feed fetches.
HTTP_TIMEOUT_SECONDS = 10.0
GITHUB_EVENTS_URL = "https://api.github.com/repos/{owner}/{repo}/events"


@dataclass
class _Entry:
    """Normalised feed entry, independent of source kind."""

    external_id: str
    title: str
    url: str
    summary: str
    published_at: datetime | None


def _from_struct_time(value: struct_time | None) -> datetime | None:
    """Convert a feedparser struct_time (UTC) to an aware datetime."""
    if value is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp (as GitHub returns) to an aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _github_events_url(url: str) -> str:
    """Derive the repo events API URL from a source url like
    https://github.com/{owner}/{repo}."""
    parts = [segment for segment in urlparse(url).path.split("/") if segment]
    if len(parts) < 2:
        raise ValueError(f"cannot derive owner/repo from url '{url}'")
    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    return GITHUB_EVENTS_URL.format(owner=owner, repo=repo)


def _fetch_rss(source: FeedSource, client: httpx.Client) -> list[_Entry]:
    # Imported lazily so the module (and the GitHub path) load even where the
    # optional feedparser dependency is absent.
    import feedparser

    response = client.get(source.url, timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    entries: list[_Entry] = []
    for entry in parsed.entries:
        # Prefer a stable id/guid; fall back to the link so entries without an
        # id still get a deterministic external_id (no churn on refetch).
        external_id = entry.get("id") or entry.get("link")
        if not external_id:
            continue
        published = _from_struct_time(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )
        entries.append(
            _Entry(
                external_id=str(external_id),
                title=entry.get("title", ""),
                url=entry.get("link", ""),
                summary=entry.get("summary", ""),
                published_at=published,
            )
        )
    return entries


def _fetch_github(source: FeedSource, client: httpx.Client) -> list[_Entry]:
    response = client.get(
        _github_events_url(source.url),
        timeout=HTTP_TIMEOUT_SECONDS,
        headers={"Accept": "application/vnd.github+json"},
    )
    response.raise_for_status()
    entries: list[_Entry] = []
    for event in response.json():
        external_id = event.get("id")
        if not external_id:
            continue
        event_type = event.get("type", "Event")
        repo = (event.get("repo") or {}).get("name", "")
        actor = (event.get("actor") or {}).get("login", "")
        entries.append(
            _Entry(
                external_id=str(external_id),
                title=" ".join(part for part in (actor, event_type, repo) if part),
                url=f"https://github.com/{repo}" if repo else source.url,
                summary=event_type,
                published_at=_parse_iso(event.get("created_at")),
            )
        )
    return entries


def _fetch_entries(source: FeedSource, client: httpx.Client) -> list[_Entry]:
    if source.kind == FeedKind.RSS:
        return _fetch_rss(source, client)
    if source.kind == FeedKind.GITHUB:
        return _fetch_github(source, client)
    raise ValueError(f"unsupported feed kind '{source.kind}'")


def _upsert(session: Session, source: FeedSource, entries: list[_Entry]) -> None:
    """Insert new FeedItems and refresh existing ones, keyed by
    (source_id, external_id), stamping fetched_at each time."""
    now = utcnow()
    for entry in entries:
        existing = session.exec(
            select(FeedItem)
            .where(FeedItem.source_id == source.id)
            .where(FeedItem.external_id == entry.external_id)
        ).first()
        if existing is None:
            session.add(
                FeedItem(
                    source_id=source.id,
                    external_id=entry.external_id,
                    title=entry.title,
                    url=entry.url,
                    summary=entry.summary,
                    published_at=entry.published_at,
                    fetched_at=now,
                )
            )
        else:
            existing.title = entry.title
            existing.url = entry.url
            existing.summary = entry.summary
            existing.published_at = entry.published_at
            existing.fetched_at = now
            session.add(existing)


def _serialize(item: FeedItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "source_id": str(item.source_id),
        "external_id": item.external_id,
        "title": item.title,
        "url": item.url,
        "summary": item.summary,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "fetched_at": item.fetched_at.isoformat(),
    }


def _latest_payload(session: Session) -> list[dict[str, Any]]:
    # Newest first: order by publish time, falling back to fetch time for
    # entries whose feed carried no timestamp.
    recency = func.coalesce(col(FeedItem.published_at), col(FeedItem.fetched_at))
    items = session.exec(select(FeedItem).order_by(recency.desc()).limit(CACHE_LIMIT)).all()
    return [_serialize(item) for item in items]


def _write_cache(session: Session, redis_client: Redis) -> list[dict[str, Any]]:
    """Cache the newest items as JSON. Best-effort: a Redis outage must not
    fail the DB-side work the job already committed."""
    payload = _latest_payload(session)
    with contextlib.suppress(RedisError):
        redis_client.set(CACHE_KEY, json.dumps(payload), ex=CACHE_TTL_SECONDS)
    return payload


def fetch_feeds_sync(
    session: Session,
    *,
    client: httpx.Client | None = None,
    redis_client: Redis | None = None,
) -> list[dict[str, Any]]:
    """Fetch every enabled feed source and cache the newest items.

    A source that fails to fetch or parse is recorded as a `fetch_failed`
    ActivityEvent and skipped; it never aborts the run. Returns the payload
    written to the cache (the newest `CACHE_LIMIT` items).
    """
    owns_client = client is None
    client = client or httpx.Client()
    try:
        sources = session.exec(
            select(FeedSource).where(col(FeedSource.enabled).is_(True))
        ).all()
        for source in sources:
            try:
                entries = _fetch_entries(source, client)
                _upsert(session, source, entries)
                session.commit()
            except Exception as exc:  # noqa: BLE001 - isolate per-source failures
                session.rollback()
                session.add(
                    ActivityEvent(
                        entity_type="feed_source",
                        entity_id=source.id,
                        action="fetch_failed",
                        message=f"Failed to fetch feed source '{source.name}': {exc}",
                    )
                )
                session.commit()
    finally:
        if owns_client:
            client.close()

    return _write_cache(session, redis_client or get_redis())


async def fetch_feeds(ctx: dict[str, Any]) -> int:
    """ARQ entrypoint. Returns the number of items cached under feeds:latest."""

    def run() -> int:
        with Session(get_engine()) as session:
            return len(fetch_feeds_sync(session))

    return await asyncio.to_thread(run)
