from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from pulse.lib.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().sqlalchemy_database_url)


@lru_cache
def get_read_engine() -> Engine:
    """Engine for the read-only replica; the primary when no replica is set.

    Only use for reads that tolerate a few milliseconds of replication lag
    (dashboard aggregation, reporting). CRUD reads stay on the primary.
    """
    return create_engine(get_settings().sqlalchemy_database_replica_url)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    with Session(get_engine()) as session:
        yield session


def get_read_session() -> Iterator[Session]:
    """FastAPI dependency yielding a read-only (replica) session."""
    with Session(get_read_engine()) as session:
        yield session


# Use this in route signatures: `def route(session: SessionDep) -> ...`
SessionDep = Annotated[Session, Depends(get_session)]
# Replica-backed session for lag-tolerant reads.
ReadSessionDep = Annotated[Session, Depends(get_read_session)]
