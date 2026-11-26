"""Unit tests for WordPressMediaProvider."""

import httpx
import pytest
import respx

from news_post_builder.adapters.media_provider import WordPressMediaProvider
from news_post_builder.config import Settings


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        LLM_API_KEY="test_key",
        WP_BASE_URL="https://test.example.com",
        WP_FEATURED_MEDIA_NIH_ID=4732,
        WP_FEATURED_MEDIA_DEFAULT_ID=4749,
        WP_FEATURED_MEDIA_NIH_URL="https://test.example.com/nih.png",
        WP_FEATURED_MEDIA_DEFAULT_URL="https://test.example.com/default.jpg",
    )


def test_default_media_items(test_settings: Settings) -> None:
    provider = WordPressMediaProvider(settings=test_settings)

    nih_items = provider.get_default_media_items(is_nih=True)
    assert len(nih_items) == 2
    assert nih_items[0].id == 4732
    assert nih_items[0].is_recommended is True
    assert nih_items[1].id == 4749
    assert nih_items[1].is_recommended is False

    default_items = provider.get_default_media_items(is_nih=False)
    assert len(default_items) == 2
    assert default_items[0].id == 4749
    assert default_items[0].is_recommended is True
    assert default_items[1].id == 4732
    assert default_items[1].is_recommended is False


@pytest.mark.asyncio
@respx.mock
async def test_get_featured_media_options_with_wp_results(test_settings: Settings) -> None:
    provider = WordPressMediaProvider(settings=test_settings)

    mock_wp_media = [
        {
            "id": 5001,
            "title": {"rendered": "News_Item_Custom1"},
            "source_url": "/wp-content/uploads/2026/03/custom1.png",
            "media_details": {
                "sizes": {
                    "medium": {"source_url": "/wp-content/uploads/2026/03/custom1-300x200.png"}
                }
            },
        },
        {
            "id": 5002,
            "title": {"rendered": "News_Item_NIH_Research"},
            "source_url": "https://test.example.com/wp-content/uploads/2026/03/nih_res.jpg",
            "media_details": {},
        },
    ]

    respx.get("https://test.example.com/wp-json/wp/v2/media").respond(
        status_code=200, json=mock_wp_media
    )

    items = await provider.get_featured_media_options(
        search_pattern="News_Item", limit=5, is_nih=True
    )
    assert len(items) == 4  # 2 fetched + 2 defaults
    assert items[0].id == 5001
    assert items[0].url == "https://test.example.com/wp-content/uploads/2026/03/custom1.png"
    assert (
        items[0].thumbnail_url
        == "https://test.example.com/wp-content/uploads/2026/03/custom1-300x200.png"
    )
    assert items[1].id == 5002
    assert items[1].is_recommended is True  # is_nih and has 'nih' in title


@pytest.mark.asyncio
@respx.mock
async def test_get_featured_media_options_fallback_on_network_error(
    test_settings: Settings,
) -> None:
    provider = WordPressMediaProvider(settings=test_settings)

    respx.get("https://test.example.com/wp-json/wp/v2/media").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    items = await provider.get_featured_media_options(
        search_pattern="News_Item", limit=5, is_nih=False
    )
    assert len(items) == 2
    assert items[0].id == 4749
    assert items[0].is_recommended is True
    assert items[1].id == 4732
