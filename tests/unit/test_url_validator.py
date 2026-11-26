"""Unit tests for URL validation and SSRF protection."""

import pytest

from news_post_builder.adapters.url_validator import validate_url_and_ip
from news_post_builder.core.exceptions import FetchError, SSRFError


@pytest.mark.parametrize(
    "forbidden_url",
    [
        "http://127.0.0.1/news",
        "http://127.0.1.10:8000/",
        "http://localhost:8000/article",
        "http://10.0.0.5/page",
        "http://172.16.0.10/admin",
        "http://192.168.1.100/",
        "http://169.254.169.254/latest/meta-data/",
        "http://0.0.0.0/",
    ],
)
def test_private_and_loopback_ips_blocked(forbidden_url: str) -> None:
    with pytest.raises(SSRFError) as exc_info:
        validate_url_and_ip(forbidden_url)
    assert "blocked" in str(exc_info.value).lower()


@pytest.mark.parametrize(
    "invalid_scheme_url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file.txt",
        "gopher://example.com/",
        "javascript:alert(1)",
        "data:text/html,<b>hello</b>",
    ],
)
def test_invalid_schemes_blocked(invalid_scheme_url: str) -> None:
    with pytest.raises(FetchError) as exc_info:
        validate_url_and_ip(invalid_scheme_url)
    assert "unsupported scheme" in str(exc_info.value).lower()


def test_empty_url_rejected() -> None:
    with pytest.raises(FetchError):
        validate_url_and_ip("")


def test_public_domain_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock socket.getaddrinfo to return a safe public IP (93.184.216.34 - example.com)
    def mock_getaddrinfo(
        *_args: object, **_kwargs: object
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        return [(2, 1, 6, "", ("93.184.216.34", 80))]

    import socket

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    # Should not raise
    validate_url_and_ip("https://example.com/news/article")
