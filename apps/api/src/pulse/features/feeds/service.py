from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from pulse.features.feeds.schemas import FeedSourceCreate
from pulse.lib.errors import ConflictError
from pulse.models import ActivityEvent, FeedSource


def _record(session: Session, source: FeedSource, action: str) -> None:
    session.add(
        ActivityEvent(
            entity_type="feed_source",
            entity_id=source.id,
            action=action,
            message=f"Feed source '{source.name}' {action}",
        )
    )


def _assert_url_free(session: Session, url: str) -> None:
    existing = session.exec(select(FeedSource).where(FeedSource.url == url)).first()
    if existing is not None:
        raise ConflictError(f"Feed source with url '{url}' already exists")


def _commit_or_conflict(session: Session, url: str) -> None:
    """Commit, translating a unique-constraint violation into a 409.

    The pre-commit check in _assert_url_free gives a friendly error in the
    common case, but two concurrent requests can both pass it. The DB unique
    index on feed_sources.url is the real guarantee; this keeps the race from
    surfacing as a 500.
    """
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(f"Feed source with url '{url}' already exists") from exc


def list_sources(session: Session) -> list[FeedSource]:
    return list(session.exec(select(FeedSource).order_by(col(FeedSource.name))).all())


def create_source(session: Session, data: FeedSourceCreate) -> FeedSource:
    _assert_url_free(session, data.url)
    source = FeedSource(name=data.name, kind=data.kind, url=data.url)
    session.add(source)
    _record(session, source, "created")
    _commit_or_conflict(session, data.url)
    session.refresh(source)
    return source
