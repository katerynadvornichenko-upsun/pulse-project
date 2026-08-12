"""URL safety checks for user-supplied feed sources.

Feed URLs are supplied through the API and later fetched by the worker from
inside the private network, so they are an SSRF sink. Two layers guard them:

- `validate_feed_url` is a cheap syntactic check used by the request schemas.
  It runs no DNS (so the API never blocks on a resolver, and validation stays
  deterministic offline).
- `assert_public_target` resolves the host and is called by the fetch job
  immediately before each request, including every redirect hop.
"""

import ipaddress
import socket
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
}


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

    Deliberately does not resolve DNS; `assert_public_target` does that at
    fetch time, when it also protects against records that changed since.
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


def assert_public_target(url: str) -> None:
    """Resolve the host and reject private, loopback, or link-local targets.

    Called immediately before each request (and each redirect hop). A host
    that fails to resolve is left alone: nothing can be reached at it, so the
    HTTP client's own connection error is the right outcome.
    """
    validate_feed_url(url)
    hostname = urlparse(url).hostname
    assert hostname is not None  # guaranteed by validate_feed_url
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return
    for info in infos:
        address = info[4][0]
        if _is_disallowed_ip(str(address)):
            raise UnsafeUrlError(
                f"url resolves to a non-public address ({address}); refusing to fetch"
            )
