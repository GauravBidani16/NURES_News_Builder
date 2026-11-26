"""Unit tests for Gemini LLM Provider with mock client."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from news_post_builder.adapters.llm.gemini_provider import GeminiLLMProvider
from news_post_builder.config import Settings
from news_post_builder.core.exceptions import LLMError
from news_post_builder.core.models import ExtractedArticle


@pytest.fixture
def sample_article() -> ExtractedArticle:
    return ExtractedArticle(
        text="A revolutionary new solar panel technology achieves 40% efficiency.",
        title="Solar Record",
        site_name="Clean Energy",
        source_url="https://cleanenergy.example.com/solar",
    )


@pytest.fixture
def mock_genai_client() -> MagicMock:
    client = MagicMock()
    client.aio = MagicMock()
    client.aio.models = MagicMock()
    return client


@pytest.mark.asyncio
async def test_successful_gemini_generation(
    mock_genai_client: MagicMock, sample_article: ExtractedArticle
) -> None:
    valid_json = """
    {
      "headlines": [
        "Solar Efficiency Hits 40%",
        "New Breakthrough in Solar Cells",
        "Clean Energy Milestone"
      ],
      "descriptions": [
        "A new solar cell reaches 40% efficiency. Commercial rollouts start next year.",
        "Engineers break the efficiency barrier with tandem panels.",
        "Next-generation solar technology promises more energy per square foot."
      ],
      "recommended_headline_index": 0,
      "recommended_description_index": 0
    }
    """
    mock_response = MagicMock()
    mock_response.text = valid_json
    mock_genai_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    settings = Settings(APP_ENV="test", LLM_PROVIDER="mock", LLM_API_KEY="test_key")
    provider = GeminiLLMProvider(settings=settings, client=mock_genai_client)

    result = await provider.generate_options(sample_article, headline_count=3, description_count=3)

    assert len(result.headlines) == 3
    assert len(result.descriptions) == 3
    assert result.headlines[0].id == "H1"
    assert result.headlines[0].is_recommended is True
    assert result.descriptions[0].is_recommended is True
    assert mock_genai_client.aio.models.generate_content.call_count == 1


@pytest.mark.asyncio
async def test_retry_on_invalid_json(
    mock_genai_client: MagicMock, sample_article: ExtractedArticle
) -> None:
    bad_response = MagicMock(text="Not valid json")
    good_json = """
    {
      "headlines": ["Headline 1", "Headline 2", "Headline 3"],
      "descriptions": ["Description 1.", "Description 2.", "Description 3."],
      "recommended_headline_index": 0,
      "recommended_description_index": 0
    }
    """
    good_response = MagicMock(text=good_json)

    # First call returns bad json, second call returns good json
    mock_genai_client.aio.models.generate_content = AsyncMock(
        side_effect=[bad_response, good_response]
    )

    settings = Settings(APP_ENV="test", LLM_PROVIDER="mock", LLM_API_KEY="test_key")
    provider = GeminiLLMProvider(settings=settings, client=mock_genai_client)

    result = await provider.generate_options(sample_article)
    assert len(result.headlines) == 3
    assert mock_genai_client.aio.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_double_invalid_json_raises_llm_error(
    mock_genai_client: MagicMock, sample_article: ExtractedArticle
) -> None:
    bad_response = MagicMock(text="Broken JSON")
    mock_genai_client.aio.models.generate_content = AsyncMock(return_value=bad_response)

    settings = Settings(APP_ENV="test", LLM_PROVIDER="mock", LLM_API_KEY="test_key")
    provider = GeminiLLMProvider(settings=settings, client=mock_genai_client)

    with pytest.raises(LLMError) as exc_info:
        await provider.generate_options(sample_article)
    assert "invalid output after retry" in str(exc_info.value)
    assert mock_genai_client.aio.models.generate_content.call_count == 2
