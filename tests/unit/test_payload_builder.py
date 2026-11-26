"""Unit tests for the WordPress payload builder."""

from news_post_builder.adapters.payload_builder import StandardPayloadBuilder
from news_post_builder.config import Settings
from news_post_builder.core.models import PostPreview


def test_payload_builder_with_source_url() -> None:
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        WP_POST_STATUS="draft",
        WP_NEWS_CATEGORY_ID=31,
    )
    builder = StandardPayloadBuilder(settings=settings)

    desc = (
        "The NIH is operating under a continuing resolution through December 11, 2026. "
        "Prior fiscal policies remain in effect."
    )
    preview = PostPreview(
        selected_headline="NIH Continuing Resolution Extended",
        selected_description=desc,
        category_id=31,
        category_slug="news",
        source_url="https://grants.nih.gov/notice/123",
        featured_media_id=4732,
        status="draft",
    )

    payload = builder.build_payload(preview)

    assert payload.title == "NIH Continuing Resolution Extended"
    assert payload.excerpt == preview.selected_description
    assert payload.status == "draft"
    assert payload.categories == [31]
    assert payload.featured_media == 4732

    # Check content HTML structure matches screenshot design
    assert "<p>" in payload.content
    assert preview.selected_description in payload.content
    assert "Get more details here:" in payload.content
    assert '<a href="https://grants.nih.gov/notice/123"' in payload.content
    assert "NIH Continuing Resolution Extended</a>" in payload.content


def test_payload_builder_without_source_url_pasted_text() -> None:
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        WP_POST_STATUS="draft",
        WP_NEWS_CATEGORY_ID=31,
    )
    builder = StandardPayloadBuilder(settings=settings)

    preview = PostPreview(
        selected_headline="General Tech News",
        selected_description="A major breakthrough occurred in clean energy today.",
        category_id=31,
        category_slug="news",
        source_url=None,
        featured_media_id=4749,
        status="draft",
    )

    payload = builder.build_payload(preview)

    assert payload.title == "General Tech News"
    assert payload.excerpt == "A major breakthrough occurred in clean energy today."
    assert payload.content == "<p>A major breakthrough occurred in clean energy today.</p>"
    assert "Get more details here" not in payload.content
    assert payload.featured_media == 4749
