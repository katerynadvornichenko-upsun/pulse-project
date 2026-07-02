from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, read from environment variables.

    On Upsun, DATABASE_URL and REDIS_URL are built in apps/api/.environment
    from the service variables of the `postgresql` and `redis` relationships
    defined in .upsun/config.yaml.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://pulse:pulse@localhost:5432/pulse"
    redis_url: str = "redis://localhost:6379/0"

    @property
    def sqlalchemy_database_url(self) -> str:
        """Normalize the URL scheme so SQLAlchemy uses the psycopg (v3) driver."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
