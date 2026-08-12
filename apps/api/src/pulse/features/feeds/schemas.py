import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pulse.lib.urls import validate_feed_url
from pulse.models import FeedKind


class FeedSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: FeedKind
    # Matches the FeedSource.url column bound (see models.py): the largest
    # length whose unique index stays safe on Postgres.
    url: str = Field(min_length=1, max_length=670)

    @field_validator("url")
    @classmethod
    def url_is_safe(cls, value: str) -> str:
        # The worker fetches this URL from inside the private network; reject
        # non-http(s) schemes and obviously internal targets here (422). The
        # job re-checks with DNS resolution before every request.
        return validate_feed_url(value)


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

    @field_validator("url")
    @classmethod
    def url_is_safe(cls, value: str | None) -> str | None:
        # Same guard as on create: a PATCH must not be able to repoint a
        # source at an internal address.
        return None if value is None else validate_feed_url(value)


class FeedSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: FeedKind
    url: str
    enabled: bool
