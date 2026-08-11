import uuid

from fastapi import APIRouter, status

from pulse.features.feeds import service
from pulse.features.feeds.schemas import FeedSourceCreate, FeedSourceRead, FeedSourceUpdate
from pulse.lib.db import SessionDep

# Sources live under /feeds/sources so fetched items can take /feeds/items
# in part 3 without the bare /feeds path being ambiguous.
router = APIRouter(prefix="/feeds/sources", tags=["feeds"])


@router.get("", response_model=list[FeedSourceRead])
def list_sources(session: SessionDep) -> list[FeedSourceRead]:
    return [FeedSourceRead.model_validate(source) for source in service.list_sources(session)]


@router.post("", response_model=FeedSourceRead, status_code=status.HTTP_201_CREATED)
def create_source(data: FeedSourceCreate, session: SessionDep) -> FeedSourceRead:
    return FeedSourceRead.model_validate(service.create_source(session, data))


@router.patch("/{source_id}", response_model=FeedSourceRead)
def update_source(
    source_id: uuid.UUID, data: FeedSourceUpdate, session: SessionDep
) -> FeedSourceRead:
    return FeedSourceRead.model_validate(service.update_source(session, source_id, data))


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: uuid.UUID, session: SessionDep) -> None:
    service.delete_source(session, source_id)
