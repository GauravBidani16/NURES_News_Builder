"""FastAPI application factory and routes."""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from news_post_builder.config import Settings, get_settings

logger = logging.getLogger("news_post_builder")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, Any]:
    settings: Settings = getattr(app.state, "settings", None) or get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting News Post Builder in %s mode", settings.app_env)
    yield
    logger.info("Shutting down News Post Builder")


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(
        title="News Post Builder",
        version="0.1.0",
        description="Turns a news article into a ready-to-publish WordPress post.",
        lifespan=lifespan,
    )
    if settings is not None:
        app.state.settings = settings

    @app.get("/health")
    async def health_check() -> JSONResponse:
        current_settings: Settings = getattr(app.state, "settings", None) or get_settings()
        return JSONResponse(
            {
                "status": "ok",
                "app_env": current_settings.app_env,
                "version": "0.1.0",
                "llm_provider": current_settings.llm_provider,
                "wp_publish_enabled": current_settings.wp_publish_enabled,
            }
        )

    return app


app = create_app()
