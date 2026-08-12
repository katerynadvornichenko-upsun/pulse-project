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
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """A public-looking hostname whose DNS answer is internal (rebinding)."""
    monkeypatch.setattr(
        "pulse.lib.urls.socket.getaddrinfo",
        lambda *a, **kw: [(2, 1, 6, "", ("10.1.2.3", 80))],
    )
    with pytest.raises(UnsafeUrlError):
        assert_public_target("https://sneaky.example.com/feed")


def test_assert_public_target_allows_unresolvable_host(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing can be reached at a name that does not resolve, so leave it to
    the HTTP client to fail naturally."""

    def boom(*a: object, **kw: object) -> None:
        raise OSError("no such host")

    monkeypatch.setattr("pulse.lib.urls.socket.getaddrinfo", boom)
    assert_public_target("https://nonexistent.invalid/feed")
