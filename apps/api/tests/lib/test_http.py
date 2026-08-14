"""The IP-pinning transport: the layer that closes the DNS-rebinding gap a
pre-flight check alone leaves open."""

import httpx
import pytest

from pulse.lib.http import GuardedTransport, build_guarded_client
from pulse.lib.urls import UnsafeUrlError


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Capture what the underlying transport is asked to send."""
    seen: list[httpx.Request] = []

    def fake_send(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"ok", request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_send)
    return seen


def test_connection_is_pinned_to_the_resolved_address(
    captured: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pulse.lib.http.resolve_public_ip", lambda url: "93.184.216.34")

    GuardedTransport().handle_request(httpx.Request("GET", "https://feeds.example.com/rss"))

    sent = captured[0]
    # Connects to the checked address, not by name — a second DNS answer
    # cannot redirect this request.
    assert sent.url.host == "93.184.216.34"
    # Hostname preserved for virtual hosting and certificate verification.
    assert sent.headers["Host"] == "feeds.example.com"
    assert sent.extensions["sni_hostname"] == "feeds.example.com"


def test_rebinding_to_a_private_address_is_refused(
    captured: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    def resolves_internal(url: str) -> str:
        raise UnsafeUrlError("url resolves to a non-public address (169.254.169.254)")

    monkeypatch.setattr("pulse.lib.http.resolve_public_ip", resolves_internal)

    with pytest.raises(UnsafeUrlError):
        GuardedTransport().handle_request(httpx.Request("GET", "https://rebind.example.com/feed"))
    assert captured == []


def test_unresolvable_host_is_left_alone(
    captured: list[httpx.Request], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is reachable at a name that does not resolve, so the request
    goes out unpinned and fails naturally at connect time."""
    monkeypatch.setattr("pulse.lib.http.resolve_public_ip", lambda url: None)

    GuardedTransport().handle_request(httpx.Request("GET", "https://nonexistent.invalid/feed"))

    assert captured[0].url.host == "nonexistent.invalid"


def test_guarded_client_does_not_auto_follow_redirects() -> None:
    # The job follows redirects by hand so each hop is re-validated.
    client = build_guarded_client(5.0)
    assert client.follow_redirects is False
    assert isinstance(client._transport, GuardedTransport)
    client.close()
