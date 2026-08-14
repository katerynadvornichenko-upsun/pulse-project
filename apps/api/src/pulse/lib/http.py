"""HTTP client hardened against SSRF for fetching user-supplied URLs.

Validating a URL before calling httpx is not enough on its own: httpx resolves
the hostname again when it opens the connection, so a short-TTL record can
answer with a public address for the check and a private one for the connect
(DNS rebinding). `GuardedTransport` closes that gap by resolving once,
validating the answer, and then connecting to that exact address — the
hostname is preserved in the Host header and TLS SNI so virtual hosting and
certificate verification still work.
"""

import httpx

from pulse.lib.urls import resolve_public_ip


class GuardedTransport(httpx.HTTPTransport):
    """Transport that pins each request to a validated, globally routable IP."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        hostname = request.url.host
        address = resolve_public_ip(str(request.url))
        if address and address != hostname:
            # Connect to the checked address, but keep the original hostname
            # for routing (Host) and TLS (SNI + certificate verification).
            request.headers.setdefault("Host", request.url.netloc.decode("ascii"))
            request.extensions = {**request.extensions, "sni_hostname": hostname}
            request.url = request.url.copy_with(host=address)
        return super().handle_request(request)


def build_guarded_client(timeout: float) -> httpx.Client:
    """An httpx.Client whose every connection is SSRF-checked and IP-pinned.

    Redirects stay disabled: the fetch job follows them by hand so each hop is
    re-validated (a public URL must not be able to 302 into private space).
    """
    return httpx.Client(
        transport=GuardedTransport(),
        timeout=timeout,
        follow_redirects=False,
    )
