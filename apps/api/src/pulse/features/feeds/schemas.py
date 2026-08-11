import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pulse.models import FeedKind


class FeedSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: FeedKind
    # Matches the FeedSource.url column bound (see models.py): the largest
    # length whose unique index stays safe on Postgres.
    url: str = Field(min_length=1, max_length=670)


class FeedSourceUpdate(BaseModel):
    """PATCH body. Omitted fields stay unchanged. No field accepts null.

    `kind` is deliberately absent and, like any unknown field, rejected via
    extra="forbid": a source's kind is fixed at creation.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, min_length=1, max_length=670)
    enabled: bool | None = None

    @field_validator("name", "url", "enabled")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field does not accept null")
        return value


class FeedSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: FeedKind
    url: str
    enabled: bool
