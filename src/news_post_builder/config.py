"""Configuration management using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ValidPostStatus = Literal["publish", "future", "draft", "pending", "private"]
LLMProviderType = Literal["gemini", "anthropic", "mock"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App Settings
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    database_url: str = Field(default="sqlite:///./data/app.db", alias="DATABASE_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # LLM Settings
    llm_provider: LLMProviderType = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-3.5-flash-lite", alias="LLM_MODEL")
    llm_fallback_models: str = Field(
        default="gemini-2.5-flash,gemini-2.5-flash-lite",
        alias="LLM_FALLBACK_MODELS",
    )
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_timeout_seconds: int = Field(default=60, alias="LLM_TIMEOUT_SECONDS")
    llm_max_retries: int = Field(default=3, alias="LLM_MAX_RETRIES")
    headline_count: int = Field(default=3, alias="HEADLINE_COUNT")
    description_count: int = Field(default=3, alias="DESCRIPTION_COUNT")
    description_max_chars: int = Field(default=300, alias="DESCRIPTION_MAX_CHARS")
    max_more_rounds: int = Field(default=5, alias="MAX_MORE_ROUNDS")
    prompt_version: str = Field(default="v1", alias="PROMPT_VERSION")

    # Fetching Settings
    fetch_timeout_seconds: int = Field(default=15, alias="FETCH_TIMEOUT_SECONDS")
    fetch_max_bytes: int = Field(default=5_000_000, alias="FETCH_MAX_BYTES")
    fetch_user_agent: str = Field(
        default="NewsPostBuilder/1.0 (+https://example.com/bot)",
        alias="FETCH_USER_AGENT",
    )
    min_article_chars: int = Field(default=300, alias="MIN_ARTICLE_CHARS")

    # WordPress Settings
    wp_base_url: str = Field(default="", alias="WP_BASE_URL")
    wp_username: str = Field(default="", alias="WP_USERNAME")
    wp_app_password: str = Field(default="", alias="WP_APP_PASSWORD")
    wp_news_category_slug: str = Field(default="news", alias="WP_NEWS_CATEGORY_SLUG")
    wp_news_category_id: int | None = Field(default=None, alias="WP_NEWS_CATEGORY_ID")
    wp_post_status: ValidPostStatus = Field(default="draft", alias="WP_POST_STATUS")
    wp_publish_enabled: bool = Field(default=False, alias="WP_PUBLISH_ENABLED")
    wp_content_map: Literal["both", "content", "excerpt"] = Field(
        default="both", alias="WP_CONTENT_MAP"
    )

    # Featured Media Settings
    wp_featured_media_nih_id: int = Field(default=4732, alias="WP_FEATURED_MEDIA_NIH_ID")
    wp_featured_media_default_id: int = Field(default=4749, alias="WP_FEATURED_MEDIA_DEFAULT_ID")
    wp_featured_media_nih_url: str = Field(
        default="https://nudvnures.wpenginepowered.com/wp-content/uploads/2026/02/nih_logo.png",
        alias="WP_FEATURED_MEDIA_NIH_URL",
    )
    wp_featured_media_default_url: str = Field(
        default="https://nudvnures.wpenginepowered.com/wp-content/uploads/2026/03/martin-martz-7ELYu7jeEwo-unsplash.jpg",
        alias="WP_FEATURED_MEDIA_DEFAULT_URL",
    )

    # Teams Outgoing Webhook Settings
    teams_webhook_secret: str = Field(default="", alias="TEAMS_WEBHOOK_SECRET")
    app_base_url: str = Field(default="http://127.0.0.1:8000", alias="APP_BASE_URL")

    @property
    def fallback_models_list(self) -> list[str]:
        raw = self.llm_fallback_models.strip()
        if not raw:
            return []
        if raw.startswith("[") and raw.endswith("]"):
            import json

            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(m).strip() for m in parsed if str(m).strip()]
            except Exception:
                pass
        return [m.strip() for m in raw.split(",") if m.strip()]

    @field_validator("wp_app_password")
    @classmethod
    def clean_wp_app_password(cls, v: str) -> str:
        return v.replace(" ", "").strip()

    @field_validator("wp_post_status")
    @classmethod
    def validate_wp_post_status(cls, v: str) -> str:
        valid_statuses = {"publish", "future", "draft", "pending", "private"}
        if v not in valid_statuses:
            allowed = sorted(valid_statuses)
            raise ValueError(f"Invalid WP_POST_STATUS '{v}'. Must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def validate_rules(self) -> "Settings":
        # Check LLM key requirement when not in testing mode and not using mock provider
        if self.app_env != "test" and self.llm_provider != "mock" and not self.llm_api_key.strip():
            raise ValueError(
                "LLM_API_KEY is required and cannot be empty when APP_ENV != 'test' "
                "and LLM_PROVIDER != 'mock'."
            )

        # Check WordPress credentials if publishing is enabled
        if self.wp_publish_enabled:
            missing_wp: list[str] = []
            if not self.wp_base_url.strip():
                missing_wp.append("WP_BASE_URL")
            if not self.wp_username.strip():
                missing_wp.append("WP_USERNAME")
            if not self.wp_app_password.strip():
                missing_wp.append("WP_APP_PASSWORD")
            if missing_wp:
                joined = ", ".join(missing_wp)
                raise ValueError(
                    f"WP_PUBLISH_ENABLED is true but required credentials are missing: {joined}"
                )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
