import uuid

from fastapi import APIRouter, Query, status

from pulse.features.feeds import service
from pulse.features.feeds.schemas import (
    FeedItemRead,
    FeedSourceCreate,
    FeedSourceRead,
    FeedSourceUpdate,
)
from pulse.lib.db import ReadSessionDep, SessionDep

# Sources live under /feeds/sources so fetched items can take /feeds/items
# without the bare /feeds path being ambiguous.
router = APIRouter(prefix="/feeds", tags=["feeds"])


@router.get("/sources", response_model=list[FeedSourceRead])
def list_sources(session: SessionDep) -> list[FeedSourceRead]:
    return [FeedSourceRead.model_validate(source) for source in service.list_sources(session)]


@router.post("/sources", response_model=FeedSourceRead, status_code=status.HTTP_201_CREATED)
def create_source(data: FeedSourceCreate, session: SessionDep) -> FeedSourceRead:
    return FeedSourceRead.model_validate(service.create_source(session, data))


@router.patch("/sources/{source_id}", response_model=FeedSourceRead)
def update_source(
    source_id: uuid.UUID, data: FeedSourceUpdate, session: SessionDep
) -> FeedSourceRead:
    return FeedSourceRead.model_validate(service.update_source(session, source_id, data))


@router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_source(source_id: uuid.UUID, session: SessionDep) -> None:
    service.delete_source(session, source_id)


@router.get("/items", response_model=list[FeedItemRead])
def list_items(
    session: ReadSessionDep, limit: int = Query(default=20, ge=1, le=100)
) -> list[FeedItemRead]:
    """Newest feed items first. Served from the Redis cache when warm, falling
    back to the read replica on a cold cache."""
    return service.list_latest_items(session, limit)
