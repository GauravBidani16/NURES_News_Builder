"""Typed domain exceptions for News Post Builder.

All exceptions provide user-friendly messages for safe UI display.
"""


class NewsBuilderError(Exception):
    """Base exception for all news post builder domain errors."""

    def __init__(self, message: str, user_message: str | None = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class FetchError(NewsBuilderError):
    """Base error for article fetching failures."""


class SSRFError(FetchError):
    """Raised when a URL resolves to a forbidden, private, or loopback IP."""


class FetchTimeoutError(FetchError):
    """Raised when an HTTP fetch request times out."""


class FetchSizeExceededError(FetchError):
    """Raised when the fetched page exceeds the maximum allowed size."""


class NonHtmlContentError(FetchError):
    """Raised when the fetched resource is not an HTML document."""


class HttpStatusError(FetchError):
    """Raised when the remote server returns a non-2xx status code."""


class ExtractionError(NewsBuilderError):
    """Base error for article content extraction failures."""


class InsufficientContentError(ExtractionError):
    """Raised when the extracted article body is too short."""


class PaywallOrConsentError(ExtractionError):
    """Raised when the page appears to be gated by a paywall or cookie/consent wall."""


class LLMError(NewsBuilderError):
    """Raised when the LLM provider fails, times out, or returns invalid output."""


class InvalidTransitionError(NewsBuilderError):
    """Raised when an invalid state machine transition is attempted."""


class PublishError(NewsBuilderError):
    """Raised when post publishing fails."""
