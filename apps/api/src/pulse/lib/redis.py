"""Redis client helper.

A single lazily-created client, built from the same REDIS_URL that the ARQ
worker uses (see lib/settings.py). Used by background jobs to cache computed
payloads and, later, by request-path readers.
"""

from functools import lru_cache

from redis import Redis

from pulse.lib.settings import get_settings


@lru_cache
def get_redis() -> Redis:
    """Return a process-wide Redis client.

    `decode_responses=True` so callers read/write `str` (JSON) rather than
    raw bytes. The connection is established lazily on first command.
    """
    return Redis.from_url(get_settings().redis_url, decode_responses=True)
