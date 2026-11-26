"""Unit tests for configuration validation."""

import pytest
from pydantic import ValidationError

from news_post_builder.config import Settings


def test_valid_default_settings_in_test_env() -> None:
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        LLM_API_KEY="",
    )
    assert settings.app_env == "test"
    assert settings.wp_publish_enabled is False
    assert settings.wp_post_status == "draft"
    assert settings.headline_count == 3
    assert settings.description_count == 3


def test_missing_llm_key_in_production_fails() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="production",
            LLM_PROVIDER="gemini",
            LLM_API_KEY="",
        )
    assert "LLM_API_KEY is required" in str(exc_info.value)


def test_invalid_wp_post_status_fails() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="test",
            LLM_PROVIDER="mock",
            WP_POST_STATUS="invalid_status",  # type: ignore[arg-type]
        )
    assert "WP_POST_STATUS" in str(exc_info.value)
    assert "publish" in str(exc_info.value)


def test_wp_publish_enabled_without_credentials_fails() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            APP_ENV="test",
            LLM_PROVIDER="mock",
            WP_PUBLISH_ENABLED=True,
            WP_BASE_URL="",
        )
    assert "required credentials are missing" in str(exc_info.value)
