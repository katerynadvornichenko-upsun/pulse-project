"""Settings URL normalization: SQLAlchemy must use the psycopg (v3) driver."""

from pulse.lib.settings import Settings


def test_postgresql_url_normalized_to_psycopg() -> None:
    settings = Settings(database_url="postgresql://a:b@primary:5432/main")
    assert settings.sqlalchemy_database_url == "postgresql+psycopg://a:b@primary:5432/main"


def test_postgres_url_normalized_to_psycopg() -> None:
    settings = Settings(database_url="postgres://a:b@primary:5432/main")
    assert settings.sqlalchemy_database_url == "postgresql+psycopg://a:b@primary:5432/main"
