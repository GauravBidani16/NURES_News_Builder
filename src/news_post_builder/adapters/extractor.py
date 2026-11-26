"""Article extractor adapter using Trafilatura."""

import re

import trafilatura
from trafilatura.metadata import extract_metadata

from news_post_builder.config import Settings, get_settings
from news_post_builder.core.exceptions import (
    InsufficientContentError,
    PaywallOrConsentError,
)
from news_post_builder.core.models import ExtractedArticle
from news_post_builder.core.ports import ArticleExtractor

PAYWALL_PATTERNS = [
    re.compile(r"subscribe to (continue|read)", re.IGNORECASE),
    re.compile(r"you('ve| have) reached (your|the) (free|article) limit", re.IGNORECASE),
    re.compile(r"this content is exclusively for subscribers", re.IGNORECASE),
    re.compile(r"sign in or create an account to continue reading", re.IGNORECASE),
    re.compile(r"enable cookies and reload the page", re.IGNORECASE),
    re.compile(r"please verify you are a human", re.IGNORECASE),
    re.compile(r"cloudflare ray id", re.IGNORECASE),
]


class TrafilaturaExtractor(ArticleExtractor):
    """Extracts article text and metadata using Trafilatura."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _check_paywall(self, text: str, html: str) -> None:
        combined = f"{text}\n{html[:4000]}"
        for pattern in PAYWALL_PATTERNS:
            if pattern.search(combined):
                raise PaywallOrConsentError(
                    f"Paywall or consent wall detected matching '{pattern.pattern}'",
                    user_message=(
                        "This article appears to be behind a paywall, subscription gate, "
                        "or bot challenge. Please paste the article text directly."
                    ),
                )

    def extract(self, html: str, url: str | None = None) -> ExtractedArticle:
        """Extract article metadata and body from raw HTML."""
        if not html or not html.strip():
            raise InsufficientContentError(
                "HTML content is empty.",
                user_message="The article page returned empty content.",
            )

        # Extract structured metadata
        metadata = extract_metadata(html)
        title = metadata.title if metadata else None
        site_name = metadata.sitename if metadata else None
        publish_date = metadata.date if metadata else None

        # Extract main text
        extracted_text = trafilatura.extract(
            html,
            url=url,
            output_format="txt",
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )

        body_text = extracted_text.strip() if extracted_text else ""

        # Check for paywall markers
        self._check_paywall(body_text, html)

        if len(body_text) < self.settings.min_article_chars:
            raise InsufficientContentError(
                f"Extracted article text length ({len(body_text)}) is below "
                f"minimum {self.settings.min_article_chars} characters.",
                user_message=(
                    f"Could not extract enough readable article text ({len(body_text)} "
                    f"characters found, minimum is {self.settings.min_article_chars}). "
                    "The page may require JavaScript or login. Please paste the article text."
                ),
            )

        return ExtractedArticle(
            text=body_text,
            title=title,
            site_name=site_name,
            publish_date=publish_date,
            source_url=url,
            is_pasted=False,
        )

    def extract_from_text(self, text: str) -> ExtractedArticle:
        """Process raw pasted text as an article."""
        cleaned = text.strip()
        if len(cleaned) < self.settings.min_article_chars:
            raise InsufficientContentError(
                f"Pasted text length ({len(cleaned)}) is below "
                f"minimum {self.settings.min_article_chars} characters.",
                user_message=(
                    f"Pasted text is too short ({len(cleaned)} characters). "
                    f"Please paste at least {self.settings.min_article_chars} characters."
                ),
            )

        # Try to infer title from first line if it looks like a headline
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        inferred_title: str | None = None
        if lines and len(lines[0]) < 150:
            inferred_title = lines[0]

        return ExtractedArticle(
            text=cleaned,
            title=inferred_title,
            site_name=None,
            publish_date=None,
            source_url=None,
            is_pasted=True,
        )
