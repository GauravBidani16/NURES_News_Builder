"""LLM Provider factory."""

from news_post_builder.adapters.llm.gemini_provider import GeminiLLMProvider
from news_post_builder.adapters.llm.mock_provider import MockLLMProvider
from news_post_builder.config import Settings, get_settings
from news_post_builder.core.ports import LLMProvider


def get_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Instantiate the configured LLM provider."""
    s = settings or get_settings()

    if s.llm_provider == "gemini":
        return GeminiLLMProvider(settings=s)
    if s.llm_provider == "mock":
        return MockLLMProvider()

    raise ValueError(f"Unsupported LLM provider: {s.llm_provider}")
