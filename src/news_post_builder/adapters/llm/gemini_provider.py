"""Gemini LLM Provider implementation using google-genai SDK."""

import asyncio
import logging
import random

from google import genai
from google.genai import types
from google.genai.errors import APIError

from news_post_builder.adapters.llm.prompt_manager import PromptManager
from news_post_builder.adapters.llm.schema import (
    LLMRawOutput,
    parse_and_validate_llm_json,
)
from news_post_builder.config import Settings, get_settings
from news_post_builder.core.exceptions import LLMError
from news_post_builder.core.models import (
    DescriptionOption,
    ExtractedArticle,
    GenerationResult,
    HeadlineOption,
)
from news_post_builder.core.ports import LLMProvider

logger = logging.getLogger(__name__)


class GeminiLLMProvider(LLMProvider):
    """Generates options using Google Gemini models."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: genai.Client | None = None,
        prompt_manager: PromptManager | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.prompt_manager = prompt_manager or PromptManager()
        self.client = client or genai.Client(
            api_key=self.settings.llm_api_key,
            http_options={"api_version": "v1beta"},
        )

    async def _call_api_with_backoff(self, model_name: str, prompt: str) -> str:
        """Call Gemini API with exponential backoff on 429/5xx errors."""
        retries = self.settings.llm_max_retries
        base_delay = 1.0

        for attempt in range(retries + 1):
            try:
                config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=LLMRawOutput,
                    temperature=0.4,
                )
                response = await self.client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                if not response.text:
                    raise LLMError(f"Model '{model_name}' returned empty response text.")
                return response.text
            except APIError as exc:
                status_code = getattr(exc, "code", None)
                # Retry on rate limit (429) or transient server errors (5xx)
                if status_code in {429, 500, 502, 503, 504} and attempt < retries:
                    jitter = random.uniform(0.1, 0.5)
                    delay = (base_delay * (2**attempt)) + jitter
                    logger.warning(
                        "Gemini API error %s on model %s (attempt %d/%d); retrying in %.2fs: %s",
                        status_code,
                        model_name,
                        attempt + 1,
                        retries,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise LLMError(
                    f"Gemini API error ({status_code}) on {model_name}: {exc}",
                    user_message="The AI generation service encountered an error. Please retry.",
                ) from exc
            except Exception as exc:
                if attempt < retries and "rate" in str(exc).lower():
                    await asyncio.sleep(base_delay * (2**attempt))
                    continue
                raise LLMError(
                    f"Unexpected error communicating with Gemini model {model_name}: {exc}",
                    user_message="Failed to generate options from the AI service.",
                ) from exc

        raise LLMError(f"Exceeded maximum retries calling Gemini API with {model_name}.")

    async def _generate_with_model(
        self,
        model_name: str,
        prompt: str,
        headline_count: int,
        description_count: int,
        previous_headlines: list[str] | None,
        previous_descriptions: list[str] | None,
    ) -> GenerationResult:
        # Attempt 1
        raw_text = await self._call_api_with_backoff(model_name, prompt)
        try:
            output_model, raw_data = parse_and_validate_llm_json(
                raw_text,
                max_chars=self.settings.description_max_chars,
                max_sentences=2,
            )
        except ValueError as first_err:
            logger.warning(
                "First LLM output parsing failed for %s: %s. Retrying once...",
                model_name,
                first_err,
            )
            # Corrective retry prompt
            retry_prompt = (
                f"{prompt}\n\n"
                f"CORRECTIVE INSTRUCTION: Your previous output failed: {first_err}. "
                f"Return strictly valid JSON. Every description must be at most 2 sentences "
                f"and under {self.settings.description_max_chars} characters."
            )
            raw_text = await self._call_api_with_backoff(model_name, retry_prompt)
            try:
                output_model, raw_data = parse_and_validate_llm_json(
                    raw_text,
                    max_chars=self.settings.description_max_chars,
                    max_sentences=2,
                )
            except ValueError as second_err:
                raise LLMError(
                    f"Model {model_name} returned invalid output after retry: {second_err}",
                    user_message="The AI response could not be validated. Please try again.",
                ) from second_err

        # Map to domain models with recommendations
        start_h_idx = len(previous_headlines) if previous_headlines else 0
        start_d_idx = len(previous_descriptions) if previous_descriptions else 0

        headlines = [
            HeadlineOption(
                id=f"H{start_h_idx + i + 1}",
                text=h,
                is_recommended=(i == output_model.recommended_headline_index),
            )
            for i, h in enumerate(output_model.headlines[:headline_count])
        ]

        descriptions = [
            DescriptionOption(
                id=f"D{start_d_idx + i + 1}",
                text=d,
                is_recommended=(i == output_model.recommended_description_index),
            )
            for i, d in enumerate(output_model.descriptions[:description_count])
        ]

        raw_data["model_used"] = model_name

        return GenerationResult(
            headlines=headlines,
            descriptions=descriptions,
            prompt_version=self.settings.prompt_version,
            raw_response=raw_data,
        )

    async def generate_options(
        self,
        article: ExtractedArticle,
        headline_count: int = 3,
        description_count: int = 3,
        previous_headlines: list[str] | None = None,
        previous_descriptions: list[str] | None = None,
    ) -> GenerationResult:
        """Generate headline and description options with fallback model redundancy."""
        prompt = self.prompt_manager.format_prompt(
            article=article,
            version=self.settings.prompt_version,
            headline_count=headline_count,
            description_count=description_count,
            max_description_chars=self.settings.description_max_chars,
            previous_headlines=previous_headlines,
            previous_descriptions=previous_descriptions,
        )

        models_to_try = [self.settings.llm_model]
        for fallback_model in self.settings.fallback_models_list:
            if fallback_model not in models_to_try:
                models_to_try.append(fallback_model)

        last_error: Exception | None = None

        for model_name in models_to_try:
            try:
                return await self._generate_with_model(
                    model_name=model_name,
                    prompt=prompt,
                    headline_count=headline_count,
                    description_count=description_count,
                    previous_headlines=previous_headlines,
                    previous_descriptions=previous_descriptions,
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Model '%s' failed (%s). Attempting next fallback model...",
                    model_name,
                    exc,
                )

        raise LLMError(
            f"All configured LLM models failed. Last error: {last_error}",
            user_message="All available AI models failed to generate options. Please try again.",
        )
