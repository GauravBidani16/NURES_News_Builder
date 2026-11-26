"""Service layer driving session lifecycle and domain operations."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from news_post_builder.config import Settings, get_settings
from news_post_builder.core.exceptions import (
    ExtractionError,
    FetchError,
    NewsBuilderError,
)
from news_post_builder.core.models import (
    ArticleInput,
    ExtractedArticle,
    PostPreview,
    PublishResult,
    SessionData,
    SessionState,
)
from news_post_builder.core.ports import (
    ArticleExtractor,
    ArticleFetcher,
    LLMProvider,
    MediaProvider,
    PayloadBuilder,
    Publisher,
    SessionRepository,
)
from news_post_builder.core.state_machine import transition_session
from news_post_builder.core.task_manager import TaskManager

logger = logging.getLogger(__name__)


class NewsPostService:
    """Channel-agnostic service coordinating input, extraction, generation, and publishing."""

    def __init__(
        self,
        fetcher: ArticleFetcher,
        extractor: ArticleExtractor,
        llm_provider: LLMProvider,
        publisher: Publisher,
        repository: SessionRepository,
        payload_builder: PayloadBuilder,
        settings: Settings | None = None,
        media_provider: MediaProvider | None = None,
        task_manager: TaskManager | None = None,
    ) -> None:
        self.fetcher = fetcher
        self.extractor = extractor
        self.llm_provider = llm_provider
        self.publisher = publisher
        self.repository = repository
        self.payload_builder = payload_builder
        self.settings = settings or get_settings()
        self.media_provider = media_provider
        self.task_manager = task_manager or TaskManager()

    def create_session(self) -> SessionData:
        session = SessionData(session_id=str(uuid.uuid4()), state=SessionState.NEW)
        self.repository.save(session)
        return session

    def get_session(self, session_id: str) -> SessionData:
        session = self.repository.get(session_id)
        if not session:
            raise NewsBuilderError(
                f"Session '{session_id}' not found.",
                user_message="Session not found or expired. Please start a new session.",
            )
        return session

    async def submit(self, session_id: str, input_data: ArticleInput) -> SessionData:
        session = self.get_session(session_id)
        transition_session(session, SessionState.FETCHING)
        session.input_url = input_data.url
        session.input_text = input_data.text
        session.fetch_error = None
        self.repository.save(session)

        current_task = asyncio.current_task()
        if current_task and self.task_manager:
            self.task_manager.register(session_id, current_task)

        try:
            # Step 1: Fetch and Extract
            extracted: ExtractedArticle
            try:
                if input_data.is_url():
                    url = input_data.url or ""
                    html, final_url = await self.fetcher.fetch_html(url)
                    extracted = self.extractor.extract(html, url=final_url)
                elif input_data.text and input_data.text.strip():
                    extracted = self.extractor.extract_from_text(input_data.text)
                else:
                    raise FetchError(
                        "No article URL or text provided.",
                        user_message="Please enter an article URL or paste the article text.",
                    )
            except (FetchError, ExtractionError) as exc:
                logger.warning("Fetch/Extraction failed for session %s: %s", session_id, exc)
                session.fetch_error = exc.user_message
                transition_session(session, SessionState.FETCH_FAILED)
                self.repository.save(session)
                return session

            session.extracted_article = extracted

            # Step 2: Generate Initial Options
            try:
                result = await self.llm_provider.generate_options(
                    article=extracted,
                    headline_count=self.settings.headline_count,
                    description_count=self.settings.description_count,
                )
                session.accumulated_headlines = result.headlines
                session.accumulated_descriptions = result.descriptions
                session.more_rounds_count = 0

                # Step 3: Fetch Media Options
                detect_text = " ".join(
                    filter(
                        None,
                        [
                            session.input_url,
                            extracted.source_url,
                            extracted.title,
                        ],
                    )
                ).lower()
                is_nih = "nih" in detect_text

                if self.media_provider:
                    try:
                        media_options = await self.media_provider.get_featured_media_options(
                            search_pattern="News_Item",
                            limit=5,
                            is_nih=is_nih,
                        )
                        session.media_options = media_options
                        for m in media_options:
                            if m.is_recommended:
                                session.selected_media_id = m.id
                                session.selected_media_url = m.url
                                session.selected_media_title = m.title
                                break
                        if not session.selected_media_id and media_options:
                            session.selected_media_id = media_options[0].id
                            session.selected_media_url = media_options[0].url
                            session.selected_media_title = media_options[0].title
                    except Exception as exc:
                        logger.warning(
                            "Failed to fetch media options for session %s: %s",
                            session_id,
                            exc,
                        )

                transition_session(session, SessionState.OPTIONS_READY)
                self.repository.save(session)
                return session
            except Exception as exc:
                logger.error("LLM Generation failed for session %s: %s", session_id, exc)
                session.fetch_error = (
                    "Failed to generate options from the article text. Please try again."
                )
                transition_session(session, SessionState.FETCH_FAILED)
                self.repository.save(session)
                return session
        except asyncio.CancelledError:
            logger.info("Session %s was cancelled by user.", session_id)
            if session.state != SessionState.CANCELLED:
                transition_session(session, SessionState.CANCELLED)
                self.repository.save(session)
            raise
        finally:
            if self.task_manager:
                self.task_manager.unregister(session_id)

    async def request_more(self, session_id: str, target: str = "both") -> SessionData:
        session = self.get_session(session_id)
        if session.state != SessionState.OPTIONS_READY:
            raise NewsBuilderError(
                f"Cannot request more options in state '{session.state}'",
                user_message="Cannot request more options at this stage.",
            )

        if session.more_rounds_count >= self.settings.max_more_rounds:
            raise NewsBuilderError(
                f"Maximum more options rounds ({self.settings.max_more_rounds}) reached.",
                user_message="Maximum number of option rounds reached for this session.",
            )

        if not session.extracted_article:
            raise NewsBuilderError("No extracted article available for session.")

        current_task = asyncio.current_task()
        if current_task and self.task_manager:
            self.task_manager.register(session_id, current_task)

        try:
            prev_h = [h.text for h in session.accumulated_headlines]
            prev_d = [d.text for d in session.accumulated_descriptions]

            result = await self.llm_provider.generate_options(
                article=session.extracted_article,
                headline_count=self.settings.headline_count,
                description_count=self.settings.description_count,
                previous_headlines=prev_h,
                previous_descriptions=prev_d,
            )

            if target in {"headlines", "both"}:
                session.accumulated_headlines.extend(result.headlines)
            if target in {"descriptions", "both"}:
                session.accumulated_descriptions.extend(result.descriptions)

            session.more_rounds_count += 1
            transition_session(session, SessionState.OPTIONS_READY)
            self.repository.save(session)
            return session
        except asyncio.CancelledError:
            logger.info("Session %s request_more was cancelled by user.", session_id)
            if session.state != SessionState.CANCELLED:
                transition_session(session, SessionState.CANCELLED)
                self.repository.save(session)
            raise
        finally:
            if self.task_manager:
                self.task_manager.unregister(session_id)

    def cancel(self, session_id: str) -> SessionData:
        """Cancel an active session, stopping any in-flight API or LLM calls immediately."""
        session = self.get_session(session_id)
        if self.task_manager:
            self.task_manager.cancel(session_id)
        if session.state not in {SessionState.DONE, SessionState.CANCELLED}:
            transition_session(session, SessionState.CANCELLED)
            self.repository.save(session)
        return session

    def select(
        self,
        session_id: str,
        headline: str,
        description: str,
        headline_id: str | None = None,
        description_id: str | None = None,
        media_id: int | None = None,
    ) -> SessionData:
        session = self.get_session(session_id)
        transition_session(session, SessionState.PREVIEW)
        session.selected_headline = headline.strip()
        session.selected_description = description.strip()
        session.selected_headline_id = headline_id
        session.selected_description_id = description_id

        if media_id is not None:
            session.selected_media_id = media_id
            for m in session.media_options:
                if m.id == media_id:
                    session.selected_media_url = m.url
                    session.selected_media_title = m.title
                    break

        self.repository.save(session)
        return session

    def back_to_options(self, session_id: str) -> SessionData:
        session = self.get_session(session_id)
        transition_session(session, SessionState.OPTIONS_READY)
        self.repository.save(session)
        return session

    def get_preview(self, session_id: str) -> PostPreview:
        session = self.get_session(session_id)
        if not session.selected_headline or not session.selected_description:
            raise NewsBuilderError(
                "Incomplete selection for preview.",
                user_message="Please select both a headline and a description first.",
            )
        category_id = self.settings.wp_news_category_id or 31
        source_url = session.extracted_article.source_url if session.extracted_article else None

        # Determine featured media based on NIH indicator
        detect_text = " ".join(
            filter(
                None,
                [
                    session.input_url,
                    source_url,
                    session.extracted_article.title if session.extracted_article else None,
                ],
            )
        ).lower()

        is_nih = "nih" in detect_text
        if session.selected_media_id and session.selected_media_url:
            featured_id = session.selected_media_id
            featured_url = session.selected_media_url
        else:
            featured_id = (
                self.settings.wp_featured_media_nih_id
                if is_nih
                else self.settings.wp_featured_media_default_id
            )
            featured_url = (
                self.settings.wp_featured_media_nih_url
                if is_nih
                else self.settings.wp_featured_media_default_url
            )

        return PostPreview(
            selected_headline=session.selected_headline,
            selected_description=session.selected_description,
            category_id=category_id,
            category_slug=self.settings.wp_news_category_slug,
            source_url=source_url,
            featured_media_id=featured_id,
            featured_media_url=featured_url,
            status=self.settings.wp_post_status,
        )

    async def confirm(self, session_id: str) -> tuple[SessionData, PublishResult]:
        session = self.get_session(session_id)

        # Idempotency check: if already confirmed and published, return existing result
        if session.state == SessionState.DONE and session.publish_result:
            return session, session.publish_result

        transition_session(session, SessionState.DONE)

        preview = self.get_preview(session_id)
        payload = self.payload_builder.build_payload(preview)

        publish_key = session.publish_key or str(uuid.uuid4())
        session.publish_key = publish_key

        result = await self.publisher.publish(payload, session_id=session_id)
        session.publish_result = result
        session.updated_at = datetime.now(UTC)
        self.repository.save(session)
        return session, result
