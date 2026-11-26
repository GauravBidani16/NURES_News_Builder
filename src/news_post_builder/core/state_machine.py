"""Explicit state machine for news post builder sessions.

State diagram:
NEW --submit(url|text)--> FETCHING
FETCHING --ok--> OPTIONS_READY
FETCHING --fail--> FETCH_FAILED   (show reason; allow paste-text -> FETCHING)
OPTIONS_READY --more(headlines|descriptions|both)--> OPTIONS_READY   (options accumulate)
OPTIONS_READY --select(headline_id, description_id)--> PREVIEW
PREVIEW --edit / back--> OPTIONS_READY
PREVIEW --confirm--> DONE   (dry run: payload shown + saved; or real publish if enabled)
"""

from datetime import UTC, datetime

from news_post_builder.core.exceptions import InvalidTransitionError
from news_post_builder.core.models import SessionData, SessionState

VALID_TRANSITIONS: dict[SessionState, set[SessionState]] = {
    SessionState.NEW: {SessionState.FETCHING},
    SessionState.FETCHING: {SessionState.OPTIONS_READY, SessionState.FETCH_FAILED},
    SessionState.FETCH_FAILED: {SessionState.FETCHING},
    SessionState.OPTIONS_READY: {SessionState.OPTIONS_READY, SessionState.PREVIEW},
    SessionState.PREVIEW: {SessionState.OPTIONS_READY, SessionState.DONE},
    SessionState.DONE: set(),
}


def transition_session(session: SessionData, target_state: SessionState) -> None:
    """Transition session to target_state or raise InvalidTransitionError."""
    allowed_targets = VALID_TRANSITIONS.get(session.state, set())
    if target_state not in allowed_targets:
        raise InvalidTransitionError(
            f"Invalid transition from '{session.state}' to '{target_state}'.",
            user_message=f"Action not permitted while in '{session.state}' state.",
        )
    session.state = target_state
    session.updated_at = datetime.now(UTC)
