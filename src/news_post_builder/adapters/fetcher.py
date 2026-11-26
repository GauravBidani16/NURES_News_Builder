"""HTTP article fetcher with SSRF protection, size caps, and redirect tracking."""

from urllib.parse import urljoin

import httpx

from news_post_builder.adapters.url_validator import validate_url_and_ip
from news_post_builder.config import Settings, get_settings
from news_post_builder.core.exceptions import (
    FetchError,
    FetchSizeExceededError,
    FetchTimeoutError,
    HttpStatusError,
    NonHtmlContentError,
)
from news_post_builder.core.ports import ArticleFetcher


class HttpxArticleFetcher(ArticleFetcher):
    """Article fetcher implementation using HTTPX."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
        max_redirects: int = 5,
    ) -> None:
        self.settings = settings or get_settings()
        self._custom_client = client
        self.max_redirects = max_redirects

    async def fetch_html(self, url: str) -> tuple[str, str]:
        """Fetch article HTML, validating every redirect hop against SSRF."""
        current_url = url
        redirect_count = 0

        headers = {
            "User-Agent": self.settings.fetch_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        # If a custom client is injected (for tests/mocking), use it; otherwise instantiate one
        client = self._custom_client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=float(self.settings.fetch_timeout_seconds),
        )

        try:
            while True:
                validate_url_and_ip(current_url)

                try:
                    request = client.build_request("GET", current_url, headers=headers)
                    response = await client.send(request, stream=True)
                except httpx.TimeoutException as exc:
                    raise FetchTimeoutError(
                        f"Request timed out fetching {current_url}: {exc}",
                        user_message="The request to the news site timed out. Please try again.",
                    ) from exc
                except httpx.RequestError as exc:
                    raise FetchError(
                        f"Network error fetching {current_url}: {exc}",
                        user_message="A network error occurred while accessing the article link.",
                    ) from exc

                # Check for redirects
                if response.status_code in {301, 302, 303, 307, 308}:
                    await response.aclose()
                    redirect_count += 1
                    if redirect_count > self.max_redirects:
                        raise FetchError(
                            f"Too many redirects ({redirect_count}) for {url}",
                            user_message="Too many redirects encountered while opening the link.",
                        )

                    location = response.headers.get("location")
                    if not location:
                        raise FetchError(
                            f"Redirect status {response.status_code} with no Location header",
                            user_message="The website redirected with an invalid location.",
                        )

                    current_url = urljoin(current_url, location)
                    continue

                # Check HTTP status
                if response.status_code < 200 or response.status_code >= 300:
                    status = response.status_code
                    await response.aclose()
                    raise HttpStatusError(
                        f"HTTP error {status} fetching {current_url}",
                        user_message=f"The website returned an error (HTTP {status}).",
                    )

                # Check Content-Type
                content_type = response.headers.get("content-type", "").lower()
                allowed_types = ("text/html", "application/xhtml+xml")
                if not any(t in content_type for t in allowed_types):
                    await response.aclose()
                    raise NonHtmlContentError(
                        f"Unsupported content type '{content_type}' for {current_url}",
                        user_message="The link does not point to a readable HTML article page.",
                    )

                # Stream and enforce maximum byte cap
                raw_bytes = bytearray()
                try:
                    async for chunk in response.aiter_bytes():
                        raw_bytes.extend(chunk)
                        if len(raw_bytes) > self.settings.fetch_max_bytes:
                            await response.aclose()
                            raise FetchSizeExceededError(
                                f"Response size exceeded {self.settings.fetch_max_bytes} bytes",
                                user_message="The article page exceeded the maximum download size.",
                            )
                finally:
                    await response.aclose()

                # Decode HTML
                encoding = response.encoding or "utf-8"
                try:
                    html_content = raw_bytes.decode(encoding, errors="replace")
                except Exception:
                    html_content = raw_bytes.decode("utf-8", errors="replace")

                return html_content, current_url
        finally:
            if not self._custom_client:
                await client.aclose()
