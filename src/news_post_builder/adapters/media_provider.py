"""WordPress media provider adapter for discovering and selecting featured images."""

import logging

import httpx

from news_post_builder.config import Settings, get_settings
from news_post_builder.core.models import MediaItem
from news_post_builder.core.ports import MediaProvider

logger = logging.getLogger(__name__)


class WordPressMediaProvider(MediaProvider):
    """Fetches media items from WordPress REST API matching search pattern, with defaults."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._custom_client = client

    def get_default_media_items(self, is_nih: bool = False) -> list[MediaItem]:
        """Return the pre-configured default media items."""
        nih_item = MediaItem(
            id=self.settings.wp_featured_media_nih_id,
            title="News_Item_NIH (NIH Logo)",
            url=self.settings.wp_featured_media_nih_url,
            thumbnail_url=self.settings.wp_featured_media_nih_url,
            is_recommended=is_nih,
            tag="NIH",
        )
        default_item = MediaItem(
            id=self.settings.wp_featured_media_default_id,
            title="News_Item_Default (Clinical Research)",
            url=self.settings.wp_featured_media_default_url,
            thumbnail_url=self.settings.wp_featured_media_default_url,
            is_recommended=not is_nih,
            tag="Default",
        )
        if is_nih:
            return [nih_item, default_item]
        return [default_item, nih_item]

    async def get_featured_media_options(
        self,
        search_pattern: str = "News_Item",
        limit: int = 5,
        is_nih: bool = False,
    ) -> list[MediaItem]:
        """Fetch media matching search_pattern, supplementing or falling back to defaults."""
        defaults = self.get_default_media_items(is_nih=is_nih)
        base_url = self.settings.wp_base_url.rstrip("/")
        endpoint = f"{base_url}/wp-json/wp/v2/media"
        params = {
            "search": search_pattern,
            "media_type": "image",
            "per_page": limit,
        }

        fetched_items: list[MediaItem] = []
        headers = {
            "User-Agent": (
                self.settings.fetch_user_agent
                or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
        }
        try:
            if self._custom_client:
                resp = await self._custom_client.get(endpoint, params=params, headers=headers)
                data = resp.json() if resp.status_code == 200 else []
            else:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(endpoint, params=params, headers=headers)
                    data = resp.json() if resp.status_code == 200 else []

            if isinstance(data, list):
                for item in data:
                    media_id = item.get("id")
                    if not media_id or not isinstance(media_id, int):
                        continue
                    title = item.get("title", {}).get("rendered", f"Media {media_id}")
                    source_url = item.get("source_url") or item.get("guid", {}).get("rendered", "")
                    if source_url and source_url.startswith("/"):
                        source_url = f"{base_url}{source_url}"

                    sizes = item.get("media_details", {}).get("sizes", {})
                    thumb_url = (
                        sizes.get("medium", {}).get("source_url")
                        or sizes.get("thumbnail", {}).get("source_url")
                        or source_url
                    )
                    if thumb_url and thumb_url.startswith("/"):
                        thumb_url = f"{base_url}{thumb_url}"

                    title_lower = title.lower()
                    tag = "NIH" if "nih" in title_lower else "News"
                    is_rec = (is_nih and "nih" in title_lower) or (
                        not is_nih and "default" in title_lower
                    )

                    fetched_items.append(
                        MediaItem(
                            id=media_id,
                            title=title,
                            url=source_url,
                            thumbnail_url=thumb_url,
                            is_recommended=is_rec,
                            tag=tag,
                        )
                    )
        except Exception as exc:
            logger.info("WordPress media search bypassed or offline, using defaults: %s", exc)

        # Merge fetched items with defaults, ensuring no duplicate IDs
        seen_ids: set[int] = set()
        merged: list[MediaItem] = []

        # If fetched items exist, add them first
        for item in fetched_items:
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                merged.append(item)

        # Add defaults if not already present
        for default_item in defaults:
            if default_item.id not in seen_ids:
                seen_ids.add(default_item.id)
                merged.append(default_item)

        # Truncate to limit
        result = merged[:limit]

        # Ensure at least one item is marked recommended
        if not any(item.is_recommended for item in result) and result:
            result[0].is_recommended = True

        return result
