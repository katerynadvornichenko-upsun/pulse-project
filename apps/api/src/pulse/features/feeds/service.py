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
    supplied = data.model_dump(exclude_unset=True)
    # Keep only fields whose value actually differs, so an empty PATCH body or
    # one that resets fields to their current values is a no-op (no timeline
    # event, no write).
    changes = {key: value for key, value in supplied.items() if getattr(source, key) != value}
    if not changes:
        return source

    if "url" in changes:
        _assert_url_free(session, changes["url"])
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
    # Child FeedItems are removed by the ORM relationship's cascade_delete
    # (models.py), which issues the child DELETEs itself. The FK's
    # ondelete="CASCADE" backs this at the DB level on Postgres, but is a
    # no-op on the SQLite test backend (FK enforcement is off there), so the
    # ORM cascade is what the tests actually exercise.
    session.delete(source)
    session.commit()
