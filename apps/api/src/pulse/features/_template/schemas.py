"""Request/response schemas for this slice. Keep them separate from DB models."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ThingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ThingUpdate(BaseModel):
    """PATCH semantics (see AGENTS.md): omitted fields stay unchanged, explicit
    null is only accepted for nullable fields, where it clears the value.
    Reject null on non-nullable fields with a field_validator, and dump with
    model_dump(exclude_unset=True) in the service."""

    name: str | None = Field(default=None, min_length=1, max_length=200)


class ThingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
