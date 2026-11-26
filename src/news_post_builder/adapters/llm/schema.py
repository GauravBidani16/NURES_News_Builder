"""Validation schemas and helper utilities for LLM output."""

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


def clean_json_text(text: str) -> str:
    """Strip markdown code block wrappers from raw LLM output if present."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
    return cleaned.strip()


def count_sentences(text: str) -> int:
    """Count sentences in a string accurately, handling periods, exclamation, and question marks."""
    stripped = text.strip()
    if not stripped:
        return 0
    # Split on sentence-ending punctuation followed by whitespace or end of string
    chunks = [s.strip() for s in re.split(r"[.!?]+(?:\s+|$)", stripped) if s.strip()]
    return len(chunks)


class LLMRawOutput(BaseModel):
    """Pydantic model validating structured JSON output returned by the LLM."""

    headlines: list[str] = Field(description="Generated headline options")
    descriptions: list[str] = Field(description="Generated description options (1-2 lines each)")
    recommended_headline_index: int = Field(
        default=0, description="0-indexed top headline recommendation"
    )
    recommended_description_index: int = Field(
        default=0, description="0-indexed top description recommendation"
    )

    @field_validator("headlines")
    @classmethod
    def validate_headlines(cls, v: list[str]) -> list[str]:
        cleaned = [h.strip() for h in v if h and h.strip()]
        if not cleaned:
            raise ValueError("Headlines list cannot be empty.")
        return cleaned

    @field_validator("descriptions")
    @classmethod
    def validate_descriptions(cls, v: list[str]) -> list[str]:
        cleaned = [d.strip() for d in v if d and d.strip()]
        if not cleaned:
            raise ValueError("Descriptions list cannot be empty.")
        return cleaned

    def validate_constraints(self, max_chars: int, max_sentences: int = 2) -> None:
        """Enforce strict sentence count and character length constraints on descriptions."""
        for i, desc in enumerate(self.descriptions):
            if len(desc) > max_chars:
                raise ValueError(
                    f"Description {i + 1} exceeds max character limit: "
                    f"{len(desc)} > {max_chars} chars."
                )
            num_sentences = count_sentences(desc)
            if num_sentences > max_sentences:
                raise ValueError(
                    f"Description {i + 1} exceeds max sentence limit: "
                    f"{num_sentences} > {max_sentences} sentences."
                )

        # Validate recommendation indices
        if not (0 <= self.recommended_headline_index < len(self.headlines)):
            self.recommended_headline_index = 0
        if not (0 <= self.recommended_description_index < len(self.descriptions)):
            self.recommended_description_index = 0


def parse_and_validate_llm_json(
    raw_text: str, max_chars: int = 300, max_sentences: int = 2
) -> tuple[LLMRawOutput, dict[str, Any]]:
    """Parse JSON string and validate constraints.

    Returns:
        Tuple of (validated_model, raw_dict).

    Raises:
        ValueError: If JSON is invalid or constraints are violated.
    """
    cleaned = clean_json_text(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON output from LLM: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object from LLM, got {type(data).__name__}")

    output_model = LLMRawOutput.model_validate(data)
    output_model.validate_constraints(max_chars=max_chars, max_sentences=max_sentences)
    return output_model, data
