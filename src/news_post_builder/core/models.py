"""Core domain models for articles, suggestions, and posts."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class SessionState(StrEnum):
    NEW = "NEW"
    FETCHING = "FETCHING"
    OPTIONS_READY = "OPTIONS_READY"
    FETCH_FAILED = "FETCH_FAILED"
    PREVIEW = "PREVIEW"
    DONE = "DONE"


class ArticleInput(BaseModel):
    """Input provided by the user (either an article URL or raw text)."""

    url: str | None = Field(default=None, description="Article URL")
    text: str | None = Field(default=None, description="Pasted article text")

    def is_url(self) -> bool:
        return bool(self.url and self.url.strip())


class ExtractedArticle(BaseModel):
    """Normalized article metadata and body content extracted from the web or pasted."""

    text: str = Field(description="Cleaned article body text")
    title: str | None = Field(default=None, description="Extracted article title")
    site_name: str | None = Field(default=None, description="Publisher or site name")
    publish_date: str | None = Field(default=None, description="Article publication date")
    source_url: str | None = Field(default=None, description="Source article URL if available")
    is_pasted: bool = Field(default=False, description="Whether content was pasted directly")


class HeadlineOption(BaseModel):
    id: str = Field(description="Unique identifier, e.g. H1, H2")
    text: str = Field(description="Headline text")
    is_recommended: bool = Field(default=False, description="Top 1 recommendation flag")


class DescriptionOption(BaseModel):
    id: str = Field(description="Unique identifier, e.g. D1, D2")
    text: str = Field(description="Description text (1-2 sentences)")
    is_recommended: bool = Field(default=False, description="Top 1 recommendation flag")


class GenerationResult(BaseModel):
    """Result of an LLM generation call."""

    headlines: list[HeadlineOption] = Field(default_factory=list)
    descriptions: list[DescriptionOption] = Field(default_factory=list)
    prompt_version: str = Field(default="v1")
    raw_response: dict[str, Any] | None = Field(default=None)


class PostPreview(BaseModel):
    """Preview of the post to be confirmed by the user."""

    selected_headline: str
    selected_description: str
    category_id: int
    category_slug: str
    source_url: str | None = None
    featured_media_id: int | None = None
    featured_media_url: str | None = None
    status: str = "draft"


class WordPressPostPayload(BaseModel):
    """The exact REST API payload model for POST /wp-json/wp/v2/posts."""

    title: str
    excerpt: str
    content: str
    status: str = "draft"
    categories: list[int] = Field(default_factory=list)
    featured_media: int | None = None


class PublishResult(BaseModel):
    """Result of publishing (either dry-run or live)."""

    is_dry_run: bool
    payload: dict[str, Any]
    target_endpoint: str
    saved_file_path: str | None = None
    wp_post_id: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionData(BaseModel):
    """Full persistent session data for an article transformation pipeline."""

    session_id: str
    state: SessionState = SessionState.NEW
    input_url: str | None = None
    input_text: str | None = None
    extracted_article: ExtractedArticle | None = None
    fetch_error: str | None = None
    accumulated_headlines: list[HeadlineOption] = Field(default_factory=list)
    accumulated_descriptions: list[DescriptionOption] = Field(default_factory=list)
    more_rounds_count: int = 0
    selected_headline: str | None = None
    selected_description: str | None = None
    selected_headline_id: str | None = None
    selected_description_id: str | None = None
    publish_key: str | None = None
    publish_result: PublishResult | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
