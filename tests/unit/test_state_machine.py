"""Unit tests for the state machine transitions."""

import pytest

from news_post_builder.core.exceptions import InvalidTransitionError
from news_post_builder.core.models import SessionData, SessionState
from news_post_builder.core.state_machine import transition_session


def get_current_state(session: SessionData) -> SessionState:
    return session.state


def test_valid_transitions_lifecycle() -> None:
    session = SessionData(session_id="test-1", state=SessionState.NEW)

    # NEW -> FETCHING
    transition_session(session, SessionState.FETCHING)
    assert get_current_state(session) == SessionState.FETCHING

    # FETCHING -> OPTIONS_READY
    transition_session(session, SessionState.OPTIONS_READY)
    assert get_current_state(session) == SessionState.OPTIONS_READY

    # OPTIONS_READY -> OPTIONS_READY (accumulate)
    transition_session(session, SessionState.OPTIONS_READY)
    assert get_current_state(session) == SessionState.OPTIONS_READY

    # OPTIONS_READY -> PREVIEW
    transition_session(session, SessionState.PREVIEW)
    assert get_current_state(session) == SessionState.PREVIEW

    # PREVIEW -> OPTIONS_READY (back/edit)
    transition_session(session, SessionState.OPTIONS_READY)
    assert get_current_state(session) == SessionState.OPTIONS_READY

    # OPTIONS_READY -> PREVIEW
    transition_session(session, SessionState.PREVIEW)
    assert get_current_state(session) == SessionState.PREVIEW

    # PREVIEW -> DONE
    transition_session(session, SessionState.DONE)
    assert get_current_state(session) == SessionState.DONE


def test_fetching_failure_and_retry_flow() -> None:
    session = SessionData(session_id="test-2", state=SessionState.NEW)

    transition_session(session, SessionState.FETCHING)
    assert get_current_state(session) == SessionState.FETCHING

    # FETCHING -> FETCH_FAILED
    transition_session(session, SessionState.FETCH_FAILED)
    assert get_current_state(session) == SessionState.FETCH_FAILED

    # FETCH_FAILED -> FETCHING (retry with pasted text)
    transition_session(session, SessionState.FETCHING)
    assert get_current_state(session) == SessionState.FETCHING

    # FETCHING -> OPTIONS_READY
    transition_session(session, SessionState.OPTIONS_READY)
    assert get_current_state(session) == SessionState.OPTIONS_READY


@pytest.mark.parametrize(
    ("start_state", "invalid_target"),
    [
        (SessionState.NEW, SessionState.DONE),
        (SessionState.NEW, SessionState.PREVIEW),
        (SessionState.NEW, SessionState.OPTIONS_READY),
        (SessionState.FETCHING, SessionState.DONE),
        (SessionState.FETCH_FAILED, SessionState.OPTIONS_READY),
        (SessionState.FETCH_FAILED, SessionState.DONE),
        (SessionState.OPTIONS_READY, SessionState.FETCHING),
        (SessionState.OPTIONS_READY, SessionState.DONE),
        (SessionState.PREVIEW, SessionState.FETCHING),
        (SessionState.DONE, SessionState.PREVIEW),
        (SessionState.DONE, SessionState.NEW),
    ],
)
def test_invalid_transitions_raise_error(
    start_state: SessionState, invalid_target: SessionState
) -> None:
    session = SessionData(session_id="test-invalid", state=start_state)
    with pytest.raises(InvalidTransitionError):
        transition_session(session, invalid_target)
