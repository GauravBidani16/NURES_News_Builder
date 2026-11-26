"""Unit tests for HTTP fetching."""

import httpx
import pytest
import respx

from news_post_builder.adapters.fetcher import HttpxArticleFetcher
from news_post_builder.config import Settings
from news_post_builder.core.exceptions import (
    FetchSizeExceededError,
    FetchTimeoutError,
    HttpStatusError,
    NonHtmlContentError,
    SSRFError,
)


@pytest.fixture(autouse=True)
def mock_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock socket.getaddrinfo to resolve example domains to a public IP."""
    import socket

    def mock_getaddrinfo(
        host: str, *_args: object, **_kwargs: object
    ) -> list[tuple[int, int, int, str, tuple[str, int]]]:
        if host in {"127.0.0.1", "localhost", "169.254.169.254", "10.0.0.1"}:
            return [(2, 1, 6, "", (host, 80))]
        return [(2, 1, 6, "", ("93.184.216.34", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)


@pytest.mark.asyncio
async def test_successful_html_fetch() -> None:
    target_url = "https://news.example.com/article"
    html_content = "<html><body><h1>News Story</h1><p>Article body text here...</p></body></html>"

    async with httpx.AsyncClient() as client:
        with respx.mock(using="httpx") as respx_mock:
            respx_mock.get(target_url).respond(
                200,
                headers={"Content-Type": "text/html; charset=utf-8"},
                text=html_content,
            )

            fetcher = HttpxArticleFetcher(client=client)
            content, final_url = await fetcher.fetch_html(target_url)

            assert content == html_content
            assert final_url == target_url


@pytest.mark.asyncio
async def test_safe_redirect() -> None:
    start_url = "https://news.example.com/short"
    redirect_url = "https://news.example.com/full-story"
    html_content = "<html><body><p>Final content</p></body></html>"

    async with httpx.AsyncClient() as client:
        with respx.mock(using="httpx") as respx_mock:
            respx_mock.get(start_url).respond(
                301,
                headers={"Location": redirect_url},
            )
            respx_mock.get(redirect_url).respond(
                200,
                headers={"Content-Type": "text/html"},
                text=html_content,
            )

            fetcher = HttpxArticleFetcher(client=client)
            content, final_url = await fetcher.fetch_html(start_url)

            assert content == html_content
            assert final_url == redirect_url


@pytest.mark.asyncio
async def test_redirect_to_ssrf_blocked() -> None:
    start_url = "https://news.example.com/redirect-to-internal"
    malicious_target = "http://127.0.0.1/admin"

    async with httpx.AsyncClient() as client:
        with respx.mock(using="httpx") as respx_mock:
            respx_mock.get(start_url).respond(
                302,
                headers={"Location": malicious_target},
            )

            fetcher = HttpxArticleFetcher(client=client)
            with pytest.raises(SSRFError):
                await fetcher.fetch_html(start_url)


@pytest.mark.asyncio
async def test_http_error_status() -> None:
    url = "https://news.example.com/not-found"

    async with httpx.AsyncClient() as client:
        with respx.mock(using="httpx") as respx_mock:
            respx_mock.get(url).respond(404)

            fetcher = HttpxArticleFetcher(client=client)
            with pytest.raises(HttpStatusError) as exc_info:
                await fetcher.fetch_html(url)
            assert "404" in str(exc_info.value)


@pytest.mark.asyncio
async def test_non_html_content_type() -> None:
    url = "https://news.example.com/doc.pdf"

    async with httpx.AsyncClient() as client:
        with respx.mock(using="httpx") as respx_mock:
            respx_mock.get(url).respond(
                200,
                headers={"Content-Type": "application/pdf"},
                content=b"%PDF-1.4...",
            )

            fetcher = HttpxArticleFetcher(client=client)
            with pytest.raises(NonHtmlContentError):
                await fetcher.fetch_html(url)


@pytest.mark.asyncio
async def test_max_size_exceeded() -> None:
    url = "https://news.example.com/huge"
    large_html = "A" * 2000

    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        FETCH_MAX_BYTES=1000,
    )

    async with httpx.AsyncClient() as client:
        with respx.mock(using="httpx") as respx_mock:
            respx_mock.get(url).respond(
                200,
                headers={"Content-Type": "text/html"},
                text=large_html,
            )

            fetcher = HttpxArticleFetcher(settings=settings, client=client)
            with pytest.raises(FetchSizeExceededError):
                await fetcher.fetch_html(url)


@pytest.mark.asyncio
async def test_fetch_timeout() -> None:
    url = "https://news.example.com/slow"

    async with httpx.AsyncClient() as client:
        with respx.mock(using="httpx") as respx_mock:
            respx_mock.get(url).mock(side_effect=httpx.ReadTimeout("Timeout"))

            fetcher = HttpxArticleFetcher(client=client)
            with pytest.raises(FetchTimeoutError):
                await fetcher.fetch_html(url)
