"""Unit tests for LLM JSON schema and validation."""

import pytest

from news_post_builder.adapters.llm.schema import (
    clean_json_text,
    count_sentences,
    parse_and_validate_llm_json,
)


def test_clean_json_text_removes_code_fences() -> None:
    wrapped = '```json\n{"headlines": ["H1"], "descriptions": ["D1"]}\n```'
    assert clean_json_text(wrapped) == '{"headlines": ["H1"], "descriptions": ["D1"]}'


def test_count_sentences() -> None:
    assert count_sentences("Single sentence.") == 1
    assert count_sentences("Sentence one. Sentence two.") == 2
    assert count_sentences("First question? Second exclamation!") == 2
    assert count_sentences("One. Two. Three.") == 3
    assert count_sentences("") == 0


def test_valid_llm_json_parsing() -> None:
    raw = """
    {
      "headlines": ["Headline 1", "Headline 2", "Headline 3"],
      "descriptions": [
        "First sentence. Second sentence.",
        "Single sentence description.",
        "Another valid description of proper length."
      ],
      "recommended_headline_index": 1,
      "recommended_description_index": 0
    }
    """
    model, data = parse_and_validate_llm_json(raw, max_chars=300, max_sentences=2)
    assert len(model.headlines) == 3
    assert len(model.descriptions) == 3
    assert model.recommended_headline_index == 1
    assert model.recommended_description_index == 0
    assert "headlines" in data


def test_description_too_many_sentences_fails() -> None:
    raw = """
    {
      "headlines": ["H1", "H2", "H3"],
      "descriptions": [
        "Sentence one. Sentence two. Sentence three.",
        "Valid description."
      ],
      "recommended_headline_index": 0,
      "recommended_description_index": 0
    }
    """
    with pytest.raises(ValueError) as exc_info:
        parse_and_validate_llm_json(raw, max_chars=300, max_sentences=2)
    assert "exceeds max sentence limit" in str(exc_info.value)


def test_description_too_long_chars_fails() -> None:
    raw = """
    {
      "headlines": ["H1", "H2", "H3"],
      "descriptions": [
        "Very long description exceeding the allowed max character limit configured in settings.",
        "Short description."
      ],
      "recommended_headline_index": 0,
      "recommended_description_index": 0
    }
    """
    with pytest.raises(ValueError) as exc_info:
        parse_and_validate_llm_json(raw, max_chars=50, max_sentences=2)
    assert "exceeds max character limit" in str(exc_info.value)


def test_malformed_json_fails() -> None:
    with pytest.raises(ValueError) as exc_info:
        parse_and_validate_llm_json("Not a json string", max_chars=300, max_sentences=2)
    assert "Malformed JSON" in str(exc_info.value)
