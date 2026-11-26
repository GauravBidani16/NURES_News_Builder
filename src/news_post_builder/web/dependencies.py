"""FastAPI dependency injection utilities."""

from fastapi import Request

from news_post_builder.adapters.extractor import TrafilaturaExtractor
from news_post_builder.adapters.fetcher import HttpxArticleFetcher
from news_post_builder.adapters.llm.factory import get_llm_provider
from news_post_builder.adapters.media_provider import WordPressMediaProvider
from news_post_builder.adapters.payload_builder import StandardPayloadBuilder
from news_post_builder.adapters.publisher_factory import get_publisher
from news_post_builder.adapters.repository import SQLiteSessionRepository
from news_post_builder.config import Settings, get_settings
from news_post_builder.core.service import NewsPostService


def get_service(request: Request) -> NewsPostService:
    """Dependency provider for NewsPostService."""
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()

    fetcher = HttpxArticleFetcher(settings=settings)
    extractor = TrafilaturaExtractor(settings=settings)
    llm_provider = get_llm_provider(settings=settings)
    publisher = get_publisher(settings=settings)
    repository = SQLiteSessionRepository(settings=settings)
    payload_builder = StandardPayloadBuilder(settings=settings)
    media_provider = WordPressMediaProvider(settings=settings)
    task_manager = getattr(request.app.state, "task_manager", None)

    return NewsPostService(
        fetcher=fetcher,
        extractor=extractor,
        llm_provider=llm_provider,
        publisher=publisher,
        repository=repository,
        payload_builder=payload_builder,
        settings=settings,
        media_provider=media_provider,
        task_manager=task_manager,
    )
