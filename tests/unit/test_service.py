"""Unit tests for NewsPostService lifecycle and business logic."""

from pathlib import Path

import httpx
import pytest

from news_post_builder.adapters.extractor import TrafilaturaExtractor
from news_post_builder.adapters.fetcher import HttpxArticleFetcher
from news_post_builder.adapters.llm.mock_provider import MockLLMProvider
from news_post_builder.adapters.media_provider import WordPressMediaProvider
from news_post_builder.adapters.payload_builder import StandardPayloadBuilder
from news_post_builder.adapters.publishers import DryRunPublisher
from news_post_builder.adapters.repository import SQLiteSessionRepository
from news_post_builder.config import Settings
from news_post_builder.core.exceptions import NewsBuilderError
from news_post_builder.core.models import ArticleInput, SessionState
from news_post_builder.core.service import NewsPostService


@pytest.fixture
def test_service(tmp_path: Path) -> NewsPostService:
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        LLM_API_KEY="test_key",
        MAX_MORE_ROUNDS=2,
    )
    db_path = tmp_path / "test.db"
    dry_run_dir = tmp_path / "dry_run"

    fetcher = HttpxArticleFetcher(settings=settings)
    extractor = TrafilaturaExtractor(settings=settings)
    llm = MockLLMProvider()
    publisher = DryRunPublisher(data_dir=dry_run_dir, settings=settings)
    repository = SQLiteSessionRepository(db_path=db_path, settings=settings)
    payload_builder = StandardPayloadBuilder(settings=settings)
    mock_media_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _req: httpx.Response(200, json=[]))
    )
    media_provider = WordPressMediaProvider(settings=settings, client=mock_media_client)

    return NewsPostService(
        fetcher=fetcher,
        extractor=extractor,
        llm_provider=llm,
        publisher=publisher,
        repository=repository,
        payload_builder=payload_builder,
        settings=settings,
        media_provider=media_provider,
    )


@pytest.mark.asyncio
async def test_full_service_lifecycle_with_pasted_text(test_service: NewsPostService) -> None:
    # 1. Create session
    session = test_service.create_session()
    assert session.state == SessionState.NEW

    # 2. Submit pasted text
    article_text = (
        "New Discovery in Battery Storage Systems\n\n"
        "Researchers have developed a novel energy storage system utilizing non-toxic iron "
        "components. The battery operates at room temperature and delivers power for up to "
        "one hundred hours with zero degradation over several thousand test cycles. "
        "Commercial deployments across regional electricity grids are scheduled to begin next year."
    )
    session = await test_service.submit(session.session_id, ArticleInput(text=article_text))
    assert session.state == SessionState.OPTIONS_READY
    assert len(session.accumulated_headlines) == 3
    assert len(session.accumulated_descriptions) == 3

    # 3. Request more options
    session = await test_service.request_more(session.session_id, target="both")
    assert session.state == SessionState.OPTIONS_READY
    assert len(session.accumulated_headlines) == 6
    assert len(session.accumulated_descriptions) == 6
    assert session.more_rounds_count == 1

    # 4. Select options
    session = test_service.select(
        session_id=session.session_id,
        headline="Selected Custom Headline",
        description="Selected 2-sentence description.",
        headline_id="H1",
        description_id="D1",
    )
    assert session.state == SessionState.PREVIEW
    assert session.selected_headline == "Selected Custom Headline"

    # 5. Preview (Non-NIH text gets default media ID 4749)
    preview = test_service.get_preview(session.session_id)
    assert preview.selected_headline == "Selected Custom Headline"
    assert preview.category_id == 31
    assert preview.featured_media_id == 4749

    # Test NIH URL gets NIH media ID 4732
    nih_session = test_service.create_session()
    nih_session.input_url = "https://grants.nih.gov/notice/123"
    nih_session.state = SessionState.OPTIONS_READY
    nih_session.selected_headline = "NIH Notice"
    nih_session.selected_description = "NIH Description."
    test_service.repository.save(nih_session)
    nih_preview = test_service.get_preview(nih_session.session_id)
    assert nih_preview.featured_media_id == 4732

    # 6. Confirm (Dry-Run)
    session, result = await test_service.confirm(session.session_id)
    assert session.state == SessionState.DONE
    assert result.is_dry_run is True
    assert result.payload["title"] == "Selected Custom Headline"
    assert result.saved_file_path is not None

    # 7. Idempotency check: confirming again returns same result
    session2, result2 = await test_service.confirm(session.session_id)
    assert session2.publish_key == session.publish_key
    assert result2.saved_file_path == result.saved_file_path


@pytest.mark.asyncio
async def test_more_rounds_capped(test_service: NewsPostService) -> None:
    session = test_service.create_session()
    article_text = "Headline\n\n" + "Valid article content text here with enough characters. " * 10
    session = await test_service.submit(session.session_id, ArticleInput(text=article_text))

    # Round 1
    session = await test_service.request_more(session.session_id)
    assert session.more_rounds_count == 1

    # Round 2 (max reached)
    session = await test_service.request_more(session.session_id)
    assert session.more_rounds_count == 2

    # Round 3 must raise NewsBuilderError
    with pytest.raises(NewsBuilderError) as exc_info:
        await test_service.request_more(session.session_id)
    assert "Maximum more options rounds" in str(exc_info.value)


@pytest.mark.asyncio
async def test_image_picker_selection_overrides_default(test_service: NewsPostService) -> None:
    session = test_service.create_session()
    article_text = "Article Title\n\n" + "Content for testing image picker selection. " * 10
    session = await test_service.submit(session.session_id, ArticleInput(text=article_text))

    assert len(session.media_options) >= 2
    # Select specific media ID
    session = test_service.select(
        session_id=session.session_id,
        headline="Headline",
        description="Description",
        media_id=4732,
    )
    assert session.selected_media_id == 4732
    preview = test_service.get_preview(session.session_id)
    assert preview.featured_media_id == 4732


def test_cancel_session_stops_and_updates_state(test_service: NewsPostService) -> None:
    session = test_service.create_session()
    assert session.state == SessionState.NEW

    cancelled_session = test_service.cancel(session.session_id)
    assert cancelled_session.state == SessionState.CANCELLED

    fetched = test_service.get_session(session.session_id)
    assert fetched.state == SessionState.CANCELLED
