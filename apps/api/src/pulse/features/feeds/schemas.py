import uuid

from pydantic import BaseModel, ConfigDict, Field

from pulse.models import FeedKind


class FeedSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: FeedKind
    # Matches the FeedSource.url column bound (see models.py): the largest
    # length whose unique index stays safe on Postgres.
    url: str = Field(min_length=1, max_length=670)


class FeedSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: FeedKind
    url: str
    enabled: bool
