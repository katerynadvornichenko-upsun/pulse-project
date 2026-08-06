"""Model-level tests for the feed schema.

These exercise the ORM/DDL directly (no routes/services exist yet), so they
also serve as a smoke test that the FeedSource/FeedItem tables and the
(source_id, external_id) unique constraint are wired correctly.
"""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from pulse.models import FeedItem, FeedKind, FeedSource


def test_create_source_and_items(session: Session) -> None:
    source = FeedSource(name="Example", kind=FeedKind.RSS, url="https://example.com/feed")
    session.add(source)
    session.commit()
    session.refresh(source)

    # enabled defaults to true and created_at is populated on insert.
    assert source.enabled is True
    assert source.created_at is not None

    first = FeedItem(source_id=source.id, external_id="a", title="First", url="https://x/a")
    second = FeedItem(source_id=source.id, external_id="b", title="Second", url="https://x/b")
    session.add(first)
    session.add(second)
    session.commit()

    items = session.exec(select(FeedItem).where(FeedItem.source_id == source.id)).all()
    assert {item.external_id for item in items} == {"a", "b"}


def test_duplicate_source_external_rejected(session: Session) -> None:
    source = FeedSource(name="GitHub", kind=FeedKind.GITHUB, url="https://api.github.com")
    session.add(source)
    session.commit()
    session.refresh(source)

    session.add(FeedItem(source_id=source.id, external_id="dup", title="One", url="https://x/1"))
    session.commit()

    # The same (source_id, external_id) pair must violate the unique constraint
    # so refetches can upsert rather than duplicate.
    session.add(FeedItem(source_id=source.id, external_id="dup", title="Two", url="https://x/2"))
    with pytest.raises(IntegrityError):
        session.commit()
