"""Unit tests for article extraction."""

import pytest

from news_post_builder.adapters.extractor import TrafilaturaExtractor
from news_post_builder.config import Settings
from news_post_builder.core.exceptions import (
    InsufficientContentError,
    PaywallOrConsentError,
)


@pytest.fixture
def extractor() -> TrafilaturaExtractor:
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        MIN_ARTICLE_CHARS=100,
    )
    return TrafilaturaExtractor(settings=settings)


def test_successful_article_extraction(extractor: TrafilaturaExtractor) -> None:
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>New Technological Breakthrough Unveiled</title>
        <meta property="og:site_name" content="Tech Daily" />
      </head>
      <body>
        <nav><a href="/">Home</a><a href="/news">News</a></nav>
        <main>
          <article>
            <h1>New Technological Breakthrough Unveiled</h1>
            <p>Scientists and engineers have announced a major breakthrough in quantum
            computing that could accelerate calculations by orders of magnitude compared
            to existing classical supercomputers.</p>
            <p>The research team demonstrated stability under room temperature conditions,
            opening the door for practical commercial deployment across industries in the
            coming decade.</p>
          </article>
        </main>
        <footer>Copyright 2026 Tech Daily</footer>
      </body>
    </html>
    """
    article = extractor.extract(html, url="https://techdaily.example.com/quantum")
    assert article.title is not None
    assert "Technological Breakthrough" in article.title
    assert "quantum computing" in article.text
    assert "Copyright" not in article.text
    assert article.source_url == "https://techdaily.example.com/quantum"
    assert not article.is_pasted


def test_short_content_raises_insufficient_content_error(extractor: TrafilaturaExtractor) -> None:
    html = "<html><body><p>Too short.</p></body></html>"
    with pytest.raises(InsufficientContentError) as exc_info:
        extractor.extract(html, url="https://example.com/short")
    assert "below minimum" in str(exc_info.value).lower()


def test_paywall_detected_raises_paywall_error(extractor: TrafilaturaExtractor) -> None:
    html = """
    <html>
      <body>
        <h1>Breaking News Story</h1>
        <p>Subscribe to continue reading this exclusive investigation into corporate finances.</p>
      </body>
    </html>
    """
    with pytest.raises(PaywallOrConsentError):
        extractor.extract(html, url="https://example.com/paywalled")


def test_pasted_text_extraction(extractor: TrafilaturaExtractor) -> None:
    text = (
        "Major Discovery in Renewable Energy Storage\n\n"
        "Researchers at the National Energy Institute have successfully developed a new "
        "iron-air battery architecture capable of storing renewable energy for extended periods "
        "at a fraction of current lithium-ion costs. This breakthrough is expected to dramatically "
        "improve grid reliability during extended periods of low wind and solar generation."
    )
    article = extractor.extract_from_text(text)
    assert article.is_pasted is True
    assert article.source_url is None
    assert article.title == "Major Discovery in Renewable Energy Storage"
    assert "battery architecture" in article.text


def test_short_pasted_text_raises_error(extractor: TrafilaturaExtractor) -> None:
    with pytest.raises(InsufficientContentError):
        extractor.extract_from_text("Tiny snippet.")
