"""Unit tests for DryRunPublisher and WordPressPublisher."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from news_post_builder.adapters.publishers import DryRunPublisher, WordPressPublisher
from news_post_builder.config import Settings
from news_post_builder.core.exceptions import PublishError
from news_post_builder.core.models import WordPressPostPayload


@pytest.fixture
def sample_payload() -> WordPressPostPayload:
    return WordPressPostPayload(
        title="Test Headline",
        excerpt="Test short excerpt description.",
        content="<p>Test short excerpt description.</p>",
        status="draft",
        categories=[31],
        featured_media=4732,
    )


@pytest.mark.asyncio
async def test_dry_run_publisher_writes_file_and_makes_no_http_calls(
    tmp_path: Path, sample_payload: WordPressPostPayload
) -> None:
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        WP_BASE_URL="https://nudvnures.wpenginepowered.com",
    )
    publisher = DryRunPublisher(data_dir=tmp_path, settings=settings)

    session_id = "test-session-12345"
    result = await publisher.publish(sample_payload, session_id=session_id)

    assert result.is_dry_run is True
    assert result.wp_post_id is None
    assert result.saved_file_path is not None
    assert result.target_endpoint == "https://nudvnures.wpenginepowered.com/wp-json/wp/v2/posts"

    # Verify file was written inside project directory
    saved_file = Path(result.saved_file_path)
    assert saved_file.exists()

    content = json.loads(saved_file.read_text(encoding="utf-8"))
    assert content["session_id"] == session_id
    assert content["target_endpoint"] == "https://nudvnures.wpenginepowered.com/wp-json/wp/v2/posts"
    assert content["payload"]["title"] == "Test Headline"
    assert content["payload"]["categories"] == [31]
    assert content["payload"]["featured_media"] == 4732


@pytest.mark.asyncio
async def test_wordpress_publisher_refuses_when_disabled(
    sample_payload: WordPressPostPayload,
) -> None:
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        WP_PUBLISH_ENABLED=False,
    )
    publisher = WordPressPublisher(settings=settings)

    with pytest.raises(PublishError) as exc_info:
        await publisher.publish(sample_payload, session_id="s1")
    assert "WP_PUBLISH_ENABLED=false" in str(exc_info.value)


@pytest.mark.asyncio
async def test_wordpress_publisher_refuses_when_missing_credentials(
    sample_payload: WordPressPostPayload,
) -> None:
    # Bypass model validator by constructing settings with fake non-empty string, then mutating
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        WP_PUBLISH_ENABLED=False,
    )
    # Force publish enabled without base url
    settings.wp_publish_enabled = True
    settings.wp_base_url = ""

    publisher = WordPressPublisher(settings=settings)
    with pytest.raises(PublishError) as exc_info:
        await publisher.publish(sample_payload, session_id="s1")
    assert "Missing WordPress credentials" in str(exc_info.value)


@pytest.mark.asyncio
async def test_wordpress_publisher_mocked_http_success(
    sample_payload: WordPressPostPayload,
) -> None:
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        WP_PUBLISH_ENABLED=True,
        WP_BASE_URL="https://nudvnures.wpenginepowered.com",
        WP_USERNAME="test_user",
        WP_APP_PASSWORD="test_app_password",
    )

    target_endpoint = "https://nudvnures.wpenginepowered.com/wp-json/wp/v2/posts"

    async with httpx.AsyncClient() as client:
        with respx.mock(using="httpx") as respx_mock:
            # Mock WordPress REST response 201 Created
            mock_route = respx_mock.post(target_endpoint).respond(
                201,
                json={
                    "id": 999,
                    "status": "draft",
                    "title": {"raw": "Test Headline"},
                    "categories": [31],
                    "featured_media": 4732,
                },
            )

            publisher = WordPressPublisher(settings=settings, client=client)
            result = await publisher.publish(sample_payload, session_id="session-success")

            assert result.is_dry_run is False
            assert result.wp_post_id == 999
            assert result.target_endpoint == target_endpoint

            # Assert mock was called with correct auth and payload
            assert mock_route.called
            last_request = mock_route.calls.last.request
            assert "Authorization" in last_request.headers
            assert last_request.headers["Authorization"].startswith("Basic ")
            sent_payload = json.loads(last_request.content.decode("utf-8"))
            assert sent_payload["title"] == "Test Headline"
            assert sent_payload["categories"] == [31]
            assert sent_payload["featured_media"] == 4732
