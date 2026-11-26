"""Unit tests for prompt formatting and version management."""

import pytest

from news_post_builder.adapters.llm.prompt_manager import PromptManager
from news_post_builder.core.models import ExtractedArticle


@pytest.fixture
def sample_article() -> ExtractedArticle:
    return ExtractedArticle(
        text="Scientists have uncovered a new energy phenomenon during laboratory experiments.",
        title="Breakthrough in Physics",
        site_name="Science News",
        publish_date="2026-11-20",
        source_url="https://sciencenews.example.com/breakthrough",
    )


def test_format_prompt_includes_metadata_and_body(sample_article: ExtractedArticle) -> None:
    manager = PromptManager()
    prompt = manager.format_prompt(
        article=sample_article,
        version="v1",
        headline_count=3,
        description_count=3,
        max_description_chars=300,
    )
    assert "<ARTICLE_METADATA>" in prompt
    assert "Breakthrough in Physics" in prompt
    assert "<ARTICLE_BODY>" in prompt
    assert "energy phenomenon" in prompt
    assert "suggest exactly 3 distinct headlines" in prompt.lower()


def test_format_prompt_with_previous_options(sample_article: ExtractedArticle) -> None:
    manager = PromptManager()
    prompt = manager.format_prompt(
        article=sample_article,
        version="v1",
        previous_headlines=["Old Headline 1", "Old Headline 2"],
        previous_descriptions=["Old Description 1."],
    )
    assert "<PREVIOUSLY_GENERATED_OPTIONS>" in prompt
    assert "Old Headline 1" in prompt
    assert "Old Description 1." in prompt
    assert "Do NOT repeat" in prompt


def test_missing_prompt_version_raises_error(sample_article: ExtractedArticle) -> None:
    manager = PromptManager()
    with pytest.raises(FileNotFoundError):
        manager.format_prompt(article=sample_article, version="v99")
