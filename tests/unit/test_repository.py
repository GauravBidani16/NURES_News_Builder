"""Unit tests for SQLite session repository."""

import tempfile
from pathlib import Path

from news_post_builder.adapters.repository import SQLiteSessionRepository
from news_post_builder.core.models import HeadlineOption, SessionData, SessionState


def test_sqlite_repository_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test.db"
        repo = SQLiteSessionRepository(db_path=db_file)

        session = SessionData(
            session_id="session-123",
            state=SessionState.OPTIONS_READY,
            input_url="https://example.com/news",
            accumulated_headlines=[
                HeadlineOption(id="H1", text="Headline One", is_recommended=True)
            ],
        )

        repo.save(session)

        retrieved = repo.get("session-123")
        assert retrieved is not None
        assert retrieved.session_id == "session-123"
        assert retrieved.state == SessionState.OPTIONS_READY
        assert retrieved.input_url == "https://example.com/news"
        assert len(retrieved.accumulated_headlines) == 1
        assert retrieved.accumulated_headlines[0].text == "Headline One"
        assert retrieved.accumulated_headlines[0].is_recommended is True


def test_get_non_existent_session_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = Path(tmpdir) / "test.db"
        repo = SQLiteSessionRepository(db_path=db_file)
        assert repo.get("missing-id") is None
