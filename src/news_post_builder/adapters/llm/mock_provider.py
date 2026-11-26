"""Deterministic mock LLM provider for unit and offline integration testing."""

from typing import Any

from news_post_builder.core.exceptions import LLMError
from news_post_builder.core.models import (
    DescriptionOption,
    ExtractedArticle,
    GenerationResult,
    HeadlineOption,
)
from news_post_builder.core.ports import LLMProvider


class MockLLMProvider(LLMProvider):
    """Mock provider with call tracking and configurable responses."""

    def __init__(
        self,
        should_fail: bool = False,
        fail_error: LLMError | None = None,
        headlines: list[str] | None = None,
        descriptions: list[str] | None = None,
        recommended_h_idx: int = 0,
        recommended_d_idx: int = 0,
    ) -> None:
        self.should_fail = should_fail
        self.fail_error = fail_error or LLMError("Simulated LLM failure")
        self.canned_headlines = headlines or [
            "Mock Headline 1: Significant Scientific Discovery",
            "Mock Headline 2: Technology Advancement Unveiled",
            "Mock Headline 3: Research Shows Promising Progress",
        ]
        self.canned_descriptions = descriptions or [
            (
                "Researchers announced major progress in energy storage today. "
                "The new architecture promises improved stability."
            ),
            (
                "A newly developed technology promises higher efficiency. "
                "Commercial applications are expected soon."
            ),
            (
                "Scientists demonstrate room-temperature stability for quantum calculations. "
                "Testing is ongoing across institutions."
            ),
        ]
        self.recommended_h_idx = recommended_h_idx
        self.recommended_d_idx = recommended_d_idx

        # Call tracking
        self.call_count = 0
        self.calls: list[dict[str, Any]] = []

    async def generate_options(
        self,
        article: ExtractedArticle,
        headline_count: int = 3,
        description_count: int = 3,
        previous_headlines: list[str] | None = None,
        previous_descriptions: list[str] | None = None,
    ) -> GenerationResult:
        self.call_count += 1
        self.calls.append(
            {
                "article": article,
                "headline_count": headline_count,
                "description_count": description_count,
                "previous_headlines": previous_headlines,
                "previous_descriptions": previous_descriptions,
            }
        )

        if self.should_fail:
            raise self.fail_error

        start_h = len(previous_headlines) if previous_headlines else 0
        start_d = len(previous_descriptions) if previous_descriptions else 0

        # Create unique text if this is a "more options" round
        suffix = f" (Round {self.call_count})" if self.call_count > 1 else ""

        headlines = [
            HeadlineOption(
                id=f"H{start_h + i + 1}",
                text=f"{h}{suffix}",
                is_recommended=(i == self.recommended_h_idx),
            )
            for i, h in enumerate(self.canned_headlines[:headline_count])
        ]

        descriptions = [
            DescriptionOption(
                id=f"D{start_d + i + 1}",
                text=f"{d}{suffix}",
                is_recommended=(i == self.recommended_d_idx),
            )
            for i, d in enumerate(self.canned_descriptions[:description_count])
        ]

        return GenerationResult(
            headlines=headlines,
            descriptions=descriptions,
            prompt_version="v1",
            raw_response={"mock": True, "call_count": self.call_count},
        )
