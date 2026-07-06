"""The replica read path has no route consumer until the Phase 3 dashboard,
so these tests keep it from rotting: URL normalization, the fallback rule,
and that a ReadSessionDep session actually executes queries.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlmodel import Session

from pulse.lib import db
from pulse.lib.settings import Settings, get_settings


def test_replica_url_normalized_to_psycopg() -> None:
    settings = Settings(
        database_url="postgresql://a:b@primary:5432/main",
        database_replica_url="postgresql://a:b@replica:5432/main",
    )
    assert settings.sqlalchemy_database_replica_url == (
        "postgresql+psycopg://a:b@replica:5432/main"
    )
    # The primary URL is untouched by the replica setting.
    assert settings.sqlalchemy_database_url == "postgresql+psycopg://a:b@primary:5432/main"


def test_replica_url_falls_back_to_primary_when_unset() -> None:
    settings = Settings(
        database_url="postgresql://a:b@primary:5432/main", database_replica_url=None
    )
    assert settings.sqlalchemy_database_replica_url == settings.sqlalchemy_database_url


def test_empty_replica_url_also_falls_back() -> None:
    # Guards the .environment case where the relationship vars are absent and
    # the constructed URL degenerates to something falsy/blank.
    settings = Settings(
        database_url="postgresql://a:b@primary:5432/main", database_replica_url=""
    )
    assert settings.sqlalchemy_database_replica_url == settings.sqlalchemy_database_url


@pytest.fixture
def clean_engine_caches(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.delenv("DATABASE_REPLICA_URL", raising=False)
    get_settings.cache_clear()
    db.get_engine.cache_clear()
    db.get_read_engine.cache_clear()
    yield
    get_settings.cache_clear()
    db.get_engine.cache_clear()
    db.get_read_engine.cache_clear()


def test_read_session_executes_against_fallback(clean_engine_caches: None) -> None:
    # Iterate to exhaustion so the dependency's cleanup runs like FastAPI's.
    ran = False
    for session in db.get_read_session():
        assert isinstance(session, Session)
        assert session.exec(text("select 1")).one() == (1,)  # type: ignore[call-overload]
        ran = True
    assert ran
