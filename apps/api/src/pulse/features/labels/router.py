import uuid

from fastapi import APIRouter, status

from pulse.features.labels import service
from pulse.features.labels.schemas import LabelCreate, LabelRead, LabelUpdate
from pulse.lib.db import SessionDep

router = APIRouter(prefix="/labels", tags=["labels"])


@router.get("", response_model=list[LabelRead])
def list_labels(session: SessionDep) -> list[LabelRead]:
    return [LabelRead.model_validate(label) for label in service.list_labels(session)]


@router.post("", response_model=LabelRead, status_code=status.HTTP_201_CREATED)
def create_label(data: LabelCreate, session: SessionDep) -> LabelRead:
    return LabelRead.model_validate(service.create_label(session, data))


@router.patch("/{label_id}", response_model=LabelRead)
def update_label(label_id: uuid.UUID, data: LabelUpdate, session: SessionDep) -> LabelRead:
    return LabelRead.model_validate(service.update_label(session, label_id, data))


@router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(label_id: uuid.UUID, session: SessionDep) -> None:
    service.delete_label(session, label_id)
