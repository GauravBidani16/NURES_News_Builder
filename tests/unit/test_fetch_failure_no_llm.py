"""Unit tests verifying that fetch or extraction failures NEVER invoke the LLM.

Rule from specification:
"The fetch-failure path never calls the LLM (assert with a mock)."
"""

from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from news_post_builder.adapters.extractor import TrafilaturaExtractor
from news_post_builder.adapters.fetcher import HttpxArticleFetcher
from news_post_builder.adapters.llm.mock_provider import MockLLMProvider
from news_post_builder.config import Settings
from news_post_builder.core.exceptions import FetchError, InsufficientContentError


@pytest.mark.asyncio
async def test_fetch_failure_never_calls_llm() -> None:
    mock_llm = MockLLMProvider()
    mock_llm.generate_options = AsyncMock()  # type: ignore[method-assign]

    async with httpx.AsyncClient() as client:
        with respx.mock(using="httpx") as respx_mock:
            # 404 response on fetch
            respx_mock.get("https://news.example.com/not-found").respond(404)

            fetcher = HttpxArticleFetcher(client=client)
            extractor = TrafilaturaExtractor()

            # Attempt fetching
            try:
                html, final_url = await fetcher.fetch_html("https://news.example.com/not-found")
                article = extractor.extract(html, url=final_url)
                await mock_llm.generate_options(article)
            except FetchError:
                pass

            # Assert LLM was NEVER called
            assert mock_llm.call_count == 0
            mock_llm.generate_options.assert_not_called()


@pytest.mark.asyncio
async def test_extraction_failure_never_calls_llm() -> None:
    mock_llm = MockLLMProvider()
    mock_llm.generate_options = AsyncMock()  # type: ignore[method-assign]

    settings = Settings(APP_ENV="test", LLM_PROVIDER="mock", MIN_ARTICLE_CHARS=300)
    extractor = TrafilaturaExtractor(settings=settings)

    # HTML with insufficient body (<300 chars)
    tiny_html = "<html><body><p>Tiny text.</p></body></html>"

    try:
        article = extractor.extract(tiny_html, url="https://example.com/tiny")
        await mock_llm.generate_options(article)
    except InsufficientContentError:
        pass

    # Assert LLM was NEVER called
    assert mock_llm.call_count == 0
    mock_llm.generate_options.assert_not_called()
