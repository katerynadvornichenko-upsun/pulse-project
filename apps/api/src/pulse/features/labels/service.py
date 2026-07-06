import uuid

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from pulse.features.labels.schemas import LabelCreate, LabelUpdate
from pulse.lib.errors import ConflictError, NotFoundError
from pulse.models import ActivityEvent, Label


def _record(session: Session, label: Label, action: str) -> None:
    session.add(
        ActivityEvent(
            entity_type="label",
            entity_id=label.id,
            action=action,
            message=f"Label '{label.name}' {action}",
        )
    )


def _assert_name_free(session: Session, name: str, exclude_id: uuid.UUID | None = None) -> None:
    existing = session.exec(select(Label).where(Label.name == name)).first()
    if existing is not None and existing.id != exclude_id:
        raise ConflictError(f"Label '{name}' already exists")


def _commit_or_conflict(session: Session, name: str) -> None:
    """Commit, translating a unique-constraint violation into a 409.

    The pre-commit check in _assert_name_free gives a friendly error in the
    common case, but two concurrent requests can both pass it. The DB unique
    index on labels.name is the real guarantee; this keeps the race from
    surfacing as a 500.
    """
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(f"Label '{name}' already exists") from exc


def list_labels(session: Session) -> list[Label]:
    return list(session.exec(select(Label).order_by(col(Label.name))).all())


def get_label(session: Session, label_id: uuid.UUID) -> Label:
    label = session.get(Label, label_id)
    if label is None:
        raise NotFoundError("Label", label_id)
    return label


def create_label(session: Session, data: LabelCreate) -> Label:
    _assert_name_free(session, data.name)
    label = Label(name=data.name, color=data.color)
    session.add(label)
    _record(session, label, "created")
    _commit_or_conflict(session, data.name)
    session.refresh(label)
    return label


def update_label(session: Session, label_id: uuid.UUID, data: LabelUpdate) -> Label:
    label = get_label(session, label_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        _assert_name_free(session, changes["name"], exclude_id=label.id)
    for key, value in changes.items():
        setattr(label, key, value)
    session.add(label)
    _record(session, label, "updated")
    _commit_or_conflict(session, label.name)
    session.refresh(label)
    return label


def delete_label(session: Session, label_id: uuid.UUID) -> None:
    label = get_label(session, label_id)
    _record(session, label, "deleted")
    session.delete(label)
    session.commit()
