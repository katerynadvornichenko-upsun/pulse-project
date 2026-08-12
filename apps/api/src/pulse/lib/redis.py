"""Redis client helper.

A single lazily-created client, built from the same REDIS_URL that the ARQ
worker uses (see lib/settings.py). Used by background jobs to cache computed
payloads and, later, by request-path readers.
"""

from functools import lru_cache

from redis import Redis

from pulse.lib.settings import get_settings

# Bounded so an unreachable or unresponsive Redis fails fast instead of
# blocking on the OS default. Callers treat the cache as best-effort, which
# only holds if a dead host raises promptly (redis.TimeoutError is a
# RedisError, so existing suppression covers it).
CONNECT_TIMEOUT_SECONDS = 2.0
COMMAND_TIMEOUT_SECONDS = 2.0


@lru_cache
def get_redis() -> Redis:
    """Return a process-wide Redis client.

    `decode_responses=True` so callers read/write `str` (JSON) rather than
    raw bytes. The connection is established lazily on first command.
    """
    return Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
        socket_timeout=COMMAND_TIMEOUT_SECONDS,
    )
