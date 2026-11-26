"""SSRF guard and URL validation."""

import ipaddress
import socket
from urllib.parse import urlparse

from news_post_builder.core.exceptions import FetchError, SSRFError


def validate_url_and_ip(url: str) -> None:
    """Validate that the URL has an allowed scheme and does not resolve to an unsafe IP.

    Guards against SSRF by checking private, loopback, link-local, and reserved IP ranges.

    Raises:
        SSRFError: If the URL resolves to a forbidden or private address.
        FetchError: If the URL is malformed or hostname resolution fails.
    """
    if not url or not url.strip():
        raise FetchError("URL cannot be empty.", user_message="Please enter a valid URL.")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in {"http", "https"}:
        raise FetchError(
            f"Unsupported scheme '{parsed.scheme}'. Only http and https are allowed.",
            user_message="Only standard web links (http:// or https://) are supported.",
        )

    hostname = parsed.hostname
    if not hostname:
        raise FetchError(
            "URL does not contain a valid hostname.",
            user_message="The provided link is missing a valid domain name.",
        )

    # Immediately block obvious local addresses
    if hostname.lower() in {"localhost", "localhost.localdomain"}:
        raise SSRFError(
            f"Blocked local hostname '{hostname}'",
            user_message="Access to local or internal addresses is blocked for security.",
        )

    # Resolve all IP addresses for the hostname
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(
            f"DNS resolution failed for '{hostname}': {exc}",
            user_message=f"Could not resolve domain '{hostname}'. Please check the link.",
        ) from exc

    if not addr_info:
        raise FetchError(
            f"No IP addresses resolved for '{hostname}'.",
            user_message=f"Could not resolve domain '{hostname}'.",
        )

    for _family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise SSRFError(
                f"Invalid IP address format '{ip_str}'",
                user_message="Invalid IP address format in destination host.",
            ) from exc

        # Check for any private, loopback, link-local, multicast, or reserved ranges
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise SSRFError(
                f"Access to IP '{ip}' is blocked (private/internal/reserved range).",
                user_message="Access to internal, local, or cloud metadata addresses is forbidden.",
            )
