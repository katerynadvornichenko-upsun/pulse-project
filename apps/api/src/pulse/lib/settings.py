from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, read from environment variables.

    On Upsun, DATABASE_URL, DATABASE_REPLICA_URL, and REDIS_URL are built in
    apps/api/.environment from the service variables of the relationships
    defined in .upsun/config.yaml.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pulse:pulse@localhost:5432/pulse"
    # Read-only replica. Unset (e.g. local dev without a replica) means all
    # reads go to the primary.
    database_replica_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"

    @staticmethod
    def _normalize(url: str) -> str:
        """Normalize the URL scheme so SQLAlchemy uses the psycopg (v3) driver."""
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        return url

    @property
    def sqlalchemy_database_url(self) -> str:
        return self._normalize(self.database_url)

    @property
    def sqlalchemy_database_replica_url(self) -> str:
        """Replica URL for read-only sessions, falling back to the primary."""
        if self.database_replica_url:
            return self._normalize(self.database_replica_url)
        return self.sqlalchemy_database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
