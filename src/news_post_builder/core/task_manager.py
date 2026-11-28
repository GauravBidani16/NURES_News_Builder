"""In-memory active task registry for session lifecycle management."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TaskManager:
    """Tracks active asyncio tasks per session to allow immediate cancellation."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def register(self, session_id: str, task: asyncio.Task[Any]) -> None:
        """Register an active task for a session."""
        self._tasks[session_id] = task

    def unregister(self, session_id: str) -> None:
        """Remove a completed or terminated task."""
        self._tasks.pop(session_id, None)

    def cancel(self, session_id: str) -> bool:
        """Cancel an in-flight task for session_id if active. Returns True if cancelled."""
        task = self._tasks.pop(session_id, None)
        if task and not task.done():
            logger.info("Cancelling active task for session %s", session_id)
            task.cancel()
            return True
        return False
