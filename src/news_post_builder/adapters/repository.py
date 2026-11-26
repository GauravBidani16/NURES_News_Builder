"""SQLite session repository implementation."""

import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from news_post_builder.config import Settings, get_settings
from news_post_builder.core.models import SessionData
from news_post_builder.core.ports import SessionRepository


class SQLiteSessionRepository(SessionRepository):
    """Stores session data in a local SQLite database."""

    def __init__(self, db_path: str | Path | None = None, settings: Settings | None = None) -> None:
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            s = settings or get_settings()
            parsed = urlparse(s.database_url)
            # Handle sqlite:///./data/app.db
            path_str = parsed.path
            if path_str.startswith("/."):
                path_str = path_str[1:]
            self.db_path = Path(path_str)

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()

    def get(self, session_id: str) -> SessionData | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data_json FROM sessions WHERE session_id = ?;",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            return SessionData.model_validate(data)

    def save(self, session: SessionData) -> None:
        json_data = session.model_dump_json()
        updated_at = session.updated_at.isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, data_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    data_json = excluded.data_json,
                    updated_at = excluded.updated_at;
                """,
                (session.session_id, json_data, updated_at),
            )
            conn.commit()
