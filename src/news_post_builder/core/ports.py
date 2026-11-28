"""Core ports (interfaces) defining boundary contracts.

No framework, HTTP client, or SDK imports are allowed here.
"""

from typing import Protocol

from news_post_builder.core.models import (
    ExtractedArticle,
    GenerationResult,
    MediaItem,
    PostPreview,
    PublishResult,
    SessionData,
    WordPressPostPayload,
)


class ArticleFetcher(Protocol):
    """Port for fetching raw HTML content from an article URL."""

    async def fetch_html(self, url: str) -> tuple[str, str]:
        """Fetch HTML content from a URL safely.

        Returns:
            Tuple of (html_body, final_resolved_url).

        Raises:
            FetchError: On any network, timeout, SSRF, or status error.
        """
        ...


class ArticleExtractor(Protocol):
    """Port for extracting structured article content and metadata."""

    def extract(self, html: str, url: str | None = None) -> ExtractedArticle:
        """Extract article metadata and body from raw HTML.

        Raises:
            ExtractionError: If content is insufficient, paywalled, or unparseable.
        """
        ...

    def extract_from_text(self, text: str) -> ExtractedArticle:
        """Create ExtractedArticle from raw pasted text.

        Raises:
            ExtractionError: If text is shorter than minimum required length.
        """
        ...


class LLMProvider(Protocol):
    """Port for generating headline and description options."""

    async def generate_options(
        self,
        article: ExtractedArticle,
        headline_count: int = 3,
        description_count: int = 3,
        previous_headlines: list[str] | None = None,
        previous_descriptions: list[str] | None = None,
    ) -> GenerationResult:
        """Generate suggestions for headlines and descriptions.

        Raises:
            LLMError: If LLM call fails, times out, or returns invalid data.
        """
        ...


class Publisher(Protocol):
    """Port for publishing post payloads to WordPress (dry-run or live)."""

    async def publish(
        self,
        payload: WordPressPostPayload,
        session_id: str,
    ) -> PublishResult:
        """Publish post or execute dry-run saving.

        Raises:
            PublishError: If publishing fails.
        """
        ...


class PayloadBuilder(Protocol):
    """Port for constructing WordPress post payloads from preview data."""

    def build_payload(self, preview: PostPreview) -> WordPressPostPayload:
        """Construct WordPress REST payload from preview."""
        ...


class SessionRepository(Protocol):
    """Port for persisting and retrieving session state."""

    def get(self, session_id: str) -> SessionData | None:
        """Retrieve a session by its ID."""
        ...

    def save(self, session: SessionData) -> None:
        """Save or update a session."""
        ...

    def get_by_prefix(self, prefix: str) -> SessionData | None:
        """Retrieve a session whose ID starts with the given prefix."""
        ...

    def get_latest(self) -> SessionData | None:
        """Retrieve the most recently updated session."""
        ...


class MediaProvider(Protocol):
    """Port for searching and retrieving featured media options from WordPress."""

    async def get_featured_media_options(
        self,
        search_pattern: str = "News_Item",
        limit: int = 5,
        is_nih: bool = False,
    ) -> list[MediaItem]:
        """Fetch media options matching search_pattern, with defaults included."""
        ...
