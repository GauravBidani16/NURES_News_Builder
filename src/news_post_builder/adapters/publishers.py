"""WordPress Publisher implementations (DryRunPublisher and WordPressPublisher)."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from news_post_builder.config import Settings, get_settings
from news_post_builder.core.exceptions import PublishError
from news_post_builder.core.models import PublishResult, WordPressPostPayload
from news_post_builder.core.ports import Publisher

logger = logging.getLogger(__name__)


class DryRunPublisher(Publisher):
    """Saves the WordPress post payload to a local JSON file without making any network calls."""

    def __init__(
        self, data_dir: Path | str | None = None, settings: Settings | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.data_dir = Path(data_dir) if data_dir else Path("./data/dry_run")
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def publish(
        self,
        payload: WordPressPostPayload,
        session_id: str,
    ) -> PublishResult:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        safe_session_id = session_id[:8]
        filename = f"{timestamp}_{safe_session_id}.json"
        target_file = self.data_dir / filename

        base_url = (self.settings.wp_base_url or "https://example.com").rstrip("/")
        target_endpoint = f"{base_url}/wp-json/wp/v2/posts"

        payload_dict = payload.model_dump()

        saved_data: dict[str, Any] = {
            "target_endpoint": target_endpoint,
            "session_id": session_id,
            "created_at": datetime.now(UTC).isoformat(),
            "payload": payload_dict,
        }

        target_file.write_text(json.dumps(saved_data, indent=2), encoding="utf-8")

        return PublishResult(
            is_dry_run=True,
            payload=payload_dict,
            target_endpoint=target_endpoint,
            saved_file_path=str(target_file),
            wp_post_id=None,
        )


class WordPressPublisher(Publisher):
    """Sends authenticated POST requests to WordPress REST API over HTTPS."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._custom_client = client

    async def publish(
        self,
        payload: WordPressPostPayload,
        session_id: str,
    ) -> PublishResult:
        logger.info("Publishing session %s to WordPress", session_id)
        if not self.settings.wp_publish_enabled:
            raise PublishError(
                "WordPress publishing is disabled by configuration (WP_PUBLISH_ENABLED=false).",
                user_message="Live publishing is currently disabled.",
            )

        if (
            not self.settings.wp_base_url
            or not self.settings.wp_username
            or not self.settings.wp_app_password
        ):
            raise PublishError(
                "Missing WordPress credentials for live publishing.",
                user_message="WordPress credentials are incomplete.",
            )

        base_url = self.settings.wp_base_url.rstrip("/")
        if not base_url.startswith("https://"):
            raise PublishError(
                "WordPress publishing requires HTTPS.",
                user_message="WordPress publishing is only permitted over secure HTTPS.",
            )

        target_endpoint = f"{base_url}/wp-json/wp/v2/posts"
        payload_dict = payload.model_dump()

        auth = httpx.BasicAuth(
            username=self.settings.wp_username,
            password=self.settings.wp_app_password,
        )

        client = self._custom_client or httpx.AsyncClient(timeout=30.0)
        try:
            response = await client.post(
                target_endpoint,
                auth=auth,
                json=payload_dict,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code not in {200, 201}:
                raise PublishError(
                    f"WordPress publish failed with HTTP {response.status_code}: {response.text}",
                    user_message=f"WordPress responded with an error ({response.status_code}).",
                )
            res_data = response.json()
            wp_post_id = res_data.get("id")
            return PublishResult(
                is_dry_run=False,
                payload=payload_dict,
                target_endpoint=target_endpoint,
                saved_file_path=None,
                wp_post_id=wp_post_id,
            )
        except httpx.RequestError as exc:
            raise PublishError(
                f"Network error publishing to WordPress: {exc}",
                user_message="A network error occurred while sending post to WordPress.",
            ) from exc
        finally:
            if not self._custom_client:
                await client.aclose()
