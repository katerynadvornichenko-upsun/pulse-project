import uuid

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from pulse.features.feeds.schemas import FeedSourceCreate, FeedSourceUpdate
from pulse.lib.errors import ConflictError, NotFoundError
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


def get_source(session: Session, source_id: uuid.UUID) -> FeedSource:
    source = session.get(FeedSource, source_id)
    if source is None:
        raise NotFoundError("FeedSource", source_id)
    return source


def create_source(session: Session, data: FeedSourceCreate) -> FeedSource:
    _assert_url_free(session, data.url)
    source = FeedSource(name=data.name, kind=data.kind, url=data.url)
    session.add(source)
    _record(session, source, "created")
    _commit_or_conflict(session, data.url)
    session.refresh(source)
    return source


def update_source(session: Session, source_id: uuid.UUID, data: FeedSourceUpdate) -> FeedSource:
    source = get_source(session, source_id)
    # exclude_unset only: see AGENTS.md, PATCH semantics. The schema rejects
    # null for every field.
    changes = data.model_dump(exclude_unset=True)
    new_url = changes.get("url")
    # Renaming url onto another source is a 409; renaming to the current value
    # is a no-op that must not conflict with the row being updated.
    if new_url is not None and new_url != source.url:
        _assert_url_free(session, new_url)
    for key, value in changes.items():
        setattr(source, key, value)
    session.add(source)
    _record(session, source, "updated")
    _commit_or_conflict(session, source.url)
    session.refresh(source)
    return source


def delete_source(session: Session, source_id: uuid.UUID) -> None:
    source = get_source(session, source_id)
    _record(session, source, "deleted")
    # Child FeedItems go with it via the ondelete="CASCADE" FK (see models.py).
    session.delete(source)
    session.commit()
