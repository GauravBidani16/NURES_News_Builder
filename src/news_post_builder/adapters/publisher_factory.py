"""Publisher factory."""

from news_post_builder.adapters.publishers import DryRunPublisher, WordPressPublisher
from news_post_builder.config import Settings, get_settings
from news_post_builder.core.ports import Publisher


def get_publisher(settings: Settings | None = None) -> Publisher:
    """Return configured publisher (defaults to DryRunPublisher)."""
    s = settings or get_settings()
    if s.wp_publish_enabled:
        return WordPressPublisher(settings=s)
    return DryRunPublisher(settings=s)
