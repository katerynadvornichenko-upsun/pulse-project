import pytest

from pulse.lib.urls import UnsafeUrlError, assert_public_target, validate_feed_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/feed.xml",
        "http://example.com:8080/feed",
        "https://github.com/owner/repo",
    ],
)
def test_public_urls_accepted(url: str) -> None:
    assert validate_feed_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "gopher://example.com/",
        "ftp://example.com/feed",
        "https://",
        "http://localhost:6379/",
        "http://127.0.0.1:5432/feed",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.0.5/internal",
        "http://192.168.1.10/feed",
        "http://[::1]/feed",
        "http://metadata.google.internal/computeMetadata/v1/",
    ],
)
def test_unsafe_urls_rejected(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_feed_url(url)


def test_assert_public_target_rejects_host_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public-looking hostname whose DNS answer is internal (rebinding)."""
    monkeypatch.setattr(
        "pulse.lib.urls.socket.getaddrinfo",
        lambda *a, **kw: [(2, 1, 6, "", ("10.1.2.3", 80))],
    )
    with pytest.raises(UnsafeUrlError):
        assert_public_target("https://sneaky.example.com/feed")


def test_assert_public_target_allows_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing can be reached at a name that does not resolve, so leave it to
    the HTTP client to fail naturally."""

    def boom(*a: object, **kw: object) -> None:
        raise OSError("no such host")

    monkeypatch.setattr("pulse.lib.urls.socket.getaddrinfo", boom)
    assert_public_target("https://nonexistent.invalid/feed")


def test_slow_resolver_times_out_instead_of_hanging(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung resolver must not stall the whole serial feeds run."""
    import time

    def slow(*a: object, **kw: object) -> list:
        time.sleep(5)
        return []

    monkeypatch.setattr("pulse.lib.urls.socket.getaddrinfo", slow)
    monkeypatch.setattr("pulse.lib.urls.DNS_TIMEOUT_SECONDS", 0.1)

    started = time.monotonic()
    with pytest.raises(UnsafeUrlError, match="timed out"):
        assert_public_target("https://slow.example.com/feed")
    assert time.monotonic() - started < 2


def test_mixed_public_and_private_answers_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every answer is checked, so a record mixing a public and an internal
    address cannot slip through on ordering."""
    monkeypatch.setattr(
        "pulse.lib.urls.socket.getaddrinfo",
        lambda *a, **kw: [
            (2, 1, 6, "", ("93.184.216.34", 80)),
            (2, 1, 6, "", ("127.0.0.1", 80)),
        ],
    )
    with pytest.raises(UnsafeUrlError):
        assert_public_target("https://mixed.example.com/feed")
