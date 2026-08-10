from fastapi import APIRouter, status

from pulse.features.feeds import service
from pulse.features.feeds.schemas import FeedSourceCreate, FeedSourceRead
from pulse.lib.db import SessionDep

router = APIRouter(prefix="/feeds", tags=["feeds"])


@router.get("", response_model=list[FeedSourceRead])
def list_feeds(session: SessionDep) -> list[FeedSourceRead]:
    return [FeedSourceRead.model_validate(source) for source in service.list_sources(session)]


@router.post("", response_model=FeedSourceRead, status_code=status.HTTP_201_CREATED)
def create_feed(data: FeedSourceCreate, session: SessionDep) -> FeedSourceRead:
    return FeedSourceRead.model_validate(service.create_source(session, data))
