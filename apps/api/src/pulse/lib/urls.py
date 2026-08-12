"""URL safety checks for user-supplied feed sources.

Feed URLs are supplied through the API and later fetched by the worker from
inside the private network, so they are an SSRF sink. Three layers guard them:

- `validate_feed_url` is a cheap syntactic check used by the request schemas.
  It runs no DNS (so the API never blocks on a resolver, and validation stays
  deterministic offline).
- `resolve_public_ip` resolves the host, with a timeout, and rejects any
  answer that is not globally routable.
- `pulse.lib.http.build_guarded_client` pins that resolved address at connect
  time. Checking without pinning would leave a DNS-rebinding gap: httpx
  resolves again when it connects, so a short-TTL record can answer public to
  the check and 127.0.0.1 to the connection.
"""

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}
# getaddrinfo takes no timeout argument and can hang on a sick resolver, which
# would stall the whole (serial) feeds run. Bound it by resolving on a worker
# thread and giving up on the result.
DNS_TIMEOUT_SECONDS = 3.0
_resolver_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pulse-dns")


class UnsafeUrlError(ValueError):
    """Raised for a URL that must not be fetched from inside the network."""


def _is_disallowed_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    # is_global excludes private, loopback, link-local (incl. 169.254.169.254),
    # multicast, reserved, and unspecified ranges in one check.
    return not ip.is_global


def validate_feed_url(url: str) -> str:
    """Syntactic check: scheme, presence of a host, no obviously internal
    target. Returns the url unchanged so it can be used in a validator.

    Deliberately does not resolve DNS; that happens at fetch time.
    """
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeUrlError("url must use http or https")
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("url must include a host")
    if hostname.lower() in BLOCKED_HOSTNAMES:
        raise UnsafeUrlError("url must not point at a local address")
    if _is_disallowed_ip(hostname):
        raise UnsafeUrlError("url must not point at a private or reserved address")
    return url


def _getaddrinfo(hostname: str) -> list[tuple]:  # type: ignore[type-arg]
    future = _resolver_pool.submit(socket.getaddrinfo, hostname, None)
    try:
        return list(future.result(timeout=DNS_TIMEOUT_SECONDS))
    except FutureTimeoutError as exc:
        # The worker thread may still be blocked in the resolver; the run
        # moves on regardless.
        raise UnsafeUrlError(f"DNS lookup for '{hostname}' timed out") from exc


def resolve_public_ip(url: str) -> str | None:
    """Validate `url` and resolve it to a single globally routable address.

    Returns the address to connect to, or None when the host does not
    resolve: nothing can be reached at it, so the HTTP client's own
    connection error is the right outcome (and offline tests keep working).

    Raises UnsafeUrlError if the URL is malformed, resolution times out, or
    any answer is private, loopback, link-local, or otherwise non-global.
    Every answer is checked, not just the one returned, so a mixed
    public/private record cannot slip through.
    """
    validate_feed_url(url)
    hostname = urlparse(url).hostname
    assert hostname is not None  # guaranteed by validate_feed_url
    try:
        infos = _getaddrinfo(hostname)
    except OSError:
        return None
    if not infos:
        return None
    addresses = [str(info[4][0]) for info in infos]
    for address in addresses:
        if _is_disallowed_ip(address):
            raise UnsafeUrlError(
                f"url resolves to a non-public address ({address}); refusing to fetch"
            )
    return addresses[0]


def assert_public_target(url: str) -> None:
    """Validate and resolve, discarding the address. Used as an early check
    before a request; `build_guarded_client` performs the authoritative,
    pinned check at connect time."""
    resolve_public_ip(url)
