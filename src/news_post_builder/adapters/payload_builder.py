"""Pure WordPress payload builder."""

from news_post_builder.config import Settings, get_settings
from news_post_builder.core.models import PostPreview, WordPressPostPayload
from news_post_builder.core.ports import PayloadBuilder


class StandardPayloadBuilder(PayloadBuilder):
    """Constructs WordPress post payloads formatted to match site editorial layout."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def build_payload(self, preview: PostPreview) -> WordPressPostPayload:
        category_id = (
            preview.category_id
            if preview.category_id
            else (self.settings.wp_news_category_id or 31)
        )

        # Build content HTML matching verified news layout
        description_p = f"<p>{preview.selected_description.strip()}</p>"

        if preview.source_url and preview.source_url.strip():
            # Source link anchor text uses original title or fallback
            anchor_text = preview.selected_headline.strip()
            source_link_html = (
                f"<p>Get more details here:<br>"
                f'<a href="{preview.source_url.strip()}" target="_blank" '
                f'rel="noopener noreferrer">{anchor_text}</a></p>'
            )
            content_html = f"{description_p}\n{source_link_html}"
        else:
            content_html = description_p

        return WordPressPostPayload(
            title=preview.selected_headline.strip(),
            excerpt=preview.selected_description.strip(),
            content=content_html,
            status=self.settings.wp_post_status,
            categories=[category_id],
            featured_media=preview.featured_media_id,
        )
