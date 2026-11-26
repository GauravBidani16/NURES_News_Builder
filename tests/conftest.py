"""Pytest configuration and global fixtures."""

import os
import socket

import pytest

# Set test environment defaults before any module imports
os.environ["APP_ENV"] = "test"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_API_KEY"] = "mock-key-for-tests"
os.environ["WP_PUBLISH_ENABLED"] = "false"
os.environ["WP_POST_STATUS"] = "draft"


@pytest.fixture(autouse=True)
def mock_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock socket.getaddrinfo to resolve example domains to a public IP for tests."""
    import ipaddress

    def mock_getaddrinfo(
        host: str, *_args: object, **_kwargs: object
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        if host in {"localhost", "localhost.localdomain"}:
            return [(2, 1, 6, "", ("127.0.0.1", 80))]
        try:
            ipaddress.ip_address(host)
            return [(2, 1, 6, "", (host, 80))]
        except ValueError:
            return [(2, 1, 6, "", ("93.184.216.34", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)
