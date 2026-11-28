"""Microsoft Teams Outgoing Webhook integration with Adaptive Cards."""

import base64
import hashlib
import hmac
import html
import logging
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from news_post_builder.config import Settings, get_settings
from news_post_builder.core.models import (
    ArticleInput,
    DescriptionOption,
    HeadlineOption,
    SessionState,
)
from news_post_builder.core.service import NewsPostService
from news_post_builder.web.dependencies import get_service

logger = logging.getLogger("news_post_builder.teams")

teams_router = APIRouter(prefix="/api/webhooks", tags=["Teams Webhook"])


def verify_teams_hmac(body: bytes, auth_header: str | None, secret: str) -> bool:
    """Verify HMAC SHA-256 signature sent by Microsoft Teams Outgoing Webhook."""
    if not secret.strip():
        logger.warning("TEAMS_WEBHOOK_SECRET is not configured; skipping HMAC verification.")
        return True
    if not auth_header:
        logger.warning("Missing Authorization header in Teams webhook request.")
        return False

    token = auth_header.strip()
    if token.startswith("HMAC "):
        token = token[5:].strip()

    try:
        decoded_secret = base64.b64decode(secret)
        expected_hmac = hmac.new(decoded_secret, body, hashlib.sha256).digest()
        expected_token = base64.b64encode(expected_hmac).decode("utf-8")
        return hmac.compare_digest(token, expected_token)
    except Exception as exc:
        logger.error("Error computing Teams HMAC signature: %s", exc)
        return False


def build_suggestion_adaptive_card(
    headlines: list[HeadlineOption],
    descriptions: list[DescriptionOption],
    source_url: str | None,
    featured_image_url: str | None,
    session_id: str,
    base_url: str,
) -> dict[str, Any]:
    """Generate an Adaptive Card payload containing all article suggestions."""
    review_url = f"{base_url.rstrip('/')}/options?session_id={session_id}"

    body: list[dict[str, Any]] = [
        {
            "type": "Container",
            "style": "emphasis",
            "items": [
                {
                    "type": "TextBlock",
                    "text": "📰 NURES News Post Suggestions",
                    "weight": "Bolder",
                    "size": "Medium",
                    "color": "Accent",
                },
            ],
        },
    ]

    if source_url:
        body.append(
            {
                "type": "TextBlock",
                "text": f"**Source Article:** [{source_url}]({source_url})",
                "wrap": True,
                "size": "Small",
                "isSubtle": True,
            }
        )

    # 1. Headline Options
    body.append(
        {
            "type": "TextBlock",
            "text": "🏷️ **Headline Options:**",
            "weight": "Bolder",
            "spacing": "Medium",
        }
    )
    for h in headlines:
        badge = "⭐ **[Top Pick]** " if h.is_recommended else ""
        body.append(
            {
                "type": "TextBlock",
                "text": f"• **{h.id}:** {badge}{h.text}",
                "wrap": True,
                "spacing": "Small",
            }
        )

    # 2. Description Options
    body.append(
        {
            "type": "TextBlock",
            "text": "📝 **Description Options:**",
            "weight": "Bolder",
            "spacing": "Medium",
        }
    )
    for d in descriptions:
        badge = "⭐ **[Top Pick]** " if d.is_recommended else ""
        body.append(
            {
                "type": "TextBlock",
                "text": f"• **{d.id}:** {badge}{d.text}",
                "wrap": True,
                "spacing": "Small",
            }
        )

    if featured_image_url:
        body.append(
            {
                "type": "Image",
                "url": featured_image_url,
                "size": "Medium",
                "altText": "Featured Image Preview",
            }
        )

    body.append(
        {
            "type": "TextBlock",
            "text": (
                f"💡 **Publish recommended:** `@NewsBot publish {session_id[:8]}`\n"
                f"💡 **Publish custom picks:** `@NewsBot publish {session_id[:8]} H2 D3`\n"
                f"💡 **Get more choices:** `@NewsBot more`"
            ),
            "wrap": True,
            "spacing": "Medium",
            "isSubtle": True,
        }
    )

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                    "actions": [
                        {
                            "type": "Action.OpenUrl",
                            "title": "🚀 1-Click Publish (Top Picks)",
                            "url": f"{base_url.rstrip('/')}/quick-publish?session_id={session_id}",
                        },
                        {
                            "type": "Action.OpenUrl",
                            "title": "🎨 Select & Customize in Browser",
                            "url": review_url,
                        },
                    ],
                },
            }
        ],
    }


def build_published_adaptive_card(
    title: str,
    wp_url: str | None,
    is_dry_run: bool,
) -> dict[str, Any]:
    """Generate an Adaptive Card payload confirming successful post publishing."""
    target_text = "Dry-Run Local Post" if is_dry_run else "Live WordPress Post"
    body: list[dict[str, Any]] = [
        {
            "type": "Container",
            "style": "good",
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"✅ {target_text} Published Successfully!",
                    "weight": "Bolder",
                    "size": "Medium",
                },
            ],
        },
        {
            "type": "TextBlock",
            "text": f"**Headline:** {title}",
            "wrap": True,
        },
    ]

    actions: list[dict[str, Any]] = []
    if wp_url:
        body.append(
            {
                "type": "TextBlock",
                "text": f"**Live Link:** [{wp_url}]({wp_url})",
                "wrap": True,
            }
        )
        actions.append(
            {
                "type": "Action.OpenUrl",
                "title": "🔗 View Live Post",
                "url": wp_url,
            }
        )

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": body,
                    "actions": actions,
                },
            }
        ],
    }


def build_simple_message(text: str) -> dict[str, Any]:
    """Return a plain text message for Teams."""
    return {"type": "message", "text": text}


@teams_router.post("/teams")
async def handle_teams_webhook(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    service: Annotated[NewsPostService, Depends(get_service)] = None,  # type: ignore[assignment]
) -> JSONResponse:
    """Handle incoming requests from Microsoft Teams Outgoing Webhook."""
    settings: Settings = getattr(request.app.state, "settings", None) or get_settings()

    body = await request.body()
    if not verify_teams_hmac(body, authorization, settings.teams_webhook_secret):
        logger.warning("Rejected unauthorized Teams webhook call.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC signature",
        )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(build_simple_message("❌ Invalid JSON payload received."))

    raw_text = payload.get("text", "")
    sender_name = payload.get("from", {}).get("name", "User")

    # Clean text:
    # 1. Unescape HTML entities
    clean_text = html.unescape(raw_text)

    # 2. Extract and preserve URLs from <a href="..."> hyperlinks created by Teams
    clean_text = re.sub(
        r'<a\s+(?:[^>]*?\s+)?href=["\'](https?://[^"\'>\s]+)["\'][^>]*>(?:.*?</a>)?',
        r" \1 ",
        clean_text,
        flags=re.IGNORECASE,
    )

    # 3. Strip <at> tags, any remaining HTML tags, and literal @NewsBot mentions
    clean_text = re.sub(r"<at[^>]*>.*?</at>", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"<[^>]+>", "", clean_text)
    clean_text = re.sub(r"@?newsbot", "", clean_text, flags=re.IGNORECASE).strip()

    logger.info("Teams webhook received message from %s: %r", sender_name, clean_text)

    tokens = clean_text.split()

    # 1. Check for Help command
    if any(t.lower() in {"help", "?", "commands"} for t in tokens):
        help_msg = (
            "👋 **Hi! I am the NURES News Post Builder Bot.**\n\n"
            "Here is how you can use me:\n"
            "• **Generate suggestions:** `@NewsBot https://...` (paste news link)\n"
            "• **Get more choices:** `@NewsBot more` (or `@NewsBot more headlines`)\n"
            "• **Publish latest:** `@NewsBot publish`\n"
            "• **Publish specific post:** `@NewsBot publish <session_id>`\n"
            "• **Publish custom picks:** `@NewsBot publish <session_id> H2 D3`\n"
            "• **Cancel:** `@NewsBot cancel`\n"
        )
        return JSONResponse(build_simple_message(help_msg))

    # 2. Check for Publish / Confirm command
    publish_idx = next(
        (i for i, t in enumerate(tokens) if t.lower() in {"publish", "confirm"}),
        None,
    )
    if publish_idx is not None:
        prefix: str | None = None
        chosen_h_id: str | None = None
        chosen_d_id: str | None = None

        for tok in tokens[publish_idx + 1 :]:
            tok_upper = tok.upper()
            if re.match(r"^H\d+$", tok_upper):
                chosen_h_id = tok_upper
            elif re.match(r"^D\d+$", tok_upper):
                chosen_d_id = tok_upper
            elif not prefix:
                prefix = tok

        try:
            if prefix:
                session = service.get_session_by_prefix(prefix)
            else:
                session = service.get_latest_session()

            if session.state == SessionState.DONE and session.publish_result:
                pub_url = session.publish_result.wp_post_url or "Post already published."
                msg = (
                    f"ℹ️ Post **{session.selected_headline}** was already published!\n\n"
                    f"Link: {pub_url}"
                )
                return JSONResponse(build_simple_message(msg))

            if session.state == SessionState.OPTIONS_READY:
                # Find chosen headline (custom ID or top pick)
                selected_h = None
                if chosen_h_id:
                    selected_h = next(
                        (h for h in session.accumulated_headlines if h.id.upper() == chosen_h_id),
                        None,
                    )
                if not selected_h:
                    selected_h = next(
                        (h for h in session.accumulated_headlines if h.is_recommended),
                        session.accumulated_headlines[0] if session.accumulated_headlines else None,
                    )

                # Find chosen description (custom ID or top pick)
                selected_d = None
                if chosen_d_id:
                    selected_d = next(
                        (
                            d
                            for d in session.accumulated_descriptions
                            if d.id.upper() == chosen_d_id
                        ),
                        None,
                    )
                if not selected_d:
                    selected_d = next(
                        (d for d in session.accumulated_descriptions if d.is_recommended),
                        session.accumulated_descriptions[0]
                        if session.accumulated_descriptions
                        else None,
                    )

                if not selected_h or not selected_d:
                    return JSONResponse(
                        build_simple_message(
                            "⚠️ No generated headlines or descriptions found in this session."
                        )
                    )

                service.select(
                    session_id=session.session_id,
                    headline=selected_h.text,
                    description=selected_d.text,
                    headline_id=selected_h.id,
                    description_id=selected_d.id,
                    media_id=session.selected_media_id,
                )

            updated_session, publish_result = await service.confirm(session.session_id)
            title = updated_session.selected_headline or "News Post"
            card = build_published_adaptive_card(
                title=title,
                wp_url=publish_result.wp_post_url,
                is_dry_run=publish_result.is_dry_run,
            )
            return JSONResponse(card)
        except Exception as exc:
            logger.error("Failed to publish via Teams command: %s", exc)
            return JSONResponse(build_simple_message(f"⚠️ Could not publish post: {exc}"))

    # 3. Check for More Options command
    if any(t.lower() == "more" for t in tokens):
        target = "both"
        if any(t.lower() in {"headlines", "headline", "h"} for t in tokens):
            target = "headlines"
        elif any(t.lower() in {"descriptions", "description", "d"} for t in tokens):
            target = "descriptions"

        cmd_words = {
            "more",
            "both",
            "headlines",
            "headline",
            "h",
            "descriptions",
            "description",
            "d",
            "options",
        }
        prefix = next((t for t in tokens if t.lower() not in cmd_words), None)

        try:
            if prefix:
                session = service.get_session_by_prefix(prefix)
            else:
                session = service.get_latest_session()

            updated_session = await service.request_more(session.session_id, target=target)
            src_url = (
                updated_session.extracted_article.source_url
                if updated_session.extracted_article
                else updated_session.input_url
            )
            card = build_suggestion_adaptive_card(
                headlines=updated_session.accumulated_headlines,
                descriptions=updated_session.accumulated_descriptions,
                source_url=src_url,
                featured_image_url=updated_session.selected_media_url,
                session_id=updated_session.session_id,
                base_url=settings.app_base_url,
            )
            return JSONResponse(card)
        except Exception as exc:
            logger.error("Failed to fetch more options via Teams: %s", exc)
            return JSONResponse(build_simple_message(f"⚠️ Could not fetch more options: {exc}"))

    # 4. Check for Cancel command
    if any(t.lower() == "cancel" for t in tokens):
        try:
            session = service.get_latest_session()
            service.cancel(session.session_id)
            return JSONResponse(
                build_simple_message(f"🛑 Session `{session.session_id[:8]}` has been cancelled.")
            )
        except Exception as exc:
            return JSONResponse(build_simple_message(f"⚠️ Could not cancel: {exc}"))

    # 4. Check for URL input
    url_match = re.search(r"https?://[^\s<>\"']+", clean_text)
    if url_match:
        target_url = url_match.group(0)
        try:
            session = service.create_session()
            updated_session = await service.submit(
                session.session_id,
                ArticleInput(url=target_url),
            )

            if updated_session.state == SessionState.FETCH_FAILED:
                err_msg = (
                    updated_session.fetch_error
                    or "Article content is too short or could not be extracted."
                )
                return JSONResponse(
                    build_simple_message(f"❌ Failed to extract article: {err_msg}")
                )

            card = build_suggestion_adaptive_card(
                headlines=updated_session.accumulated_headlines,
                descriptions=updated_session.accumulated_descriptions,
                source_url=target_url,
                featured_image_url=updated_session.selected_media_url,
                session_id=updated_session.session_id,
                base_url=settings.app_base_url,
            )
            return JSONResponse(card)
            return JSONResponse(card)
        except Exception as exc:
            logger.error("Error processing URL in Teams webhook: %s", exc)
            return JSONResponse(build_simple_message(f"❌ Failed to generate options: {exc}"))

    # 5. Fallback message
    fallback_text = (
        "🤔 I didn't see an article link in your message.\n\n"
        "Try sending `@NewsBot https://...` with an article URL, or type `@NewsBot help`."
    )
    return JSONResponse(build_simple_message(fallback_text))
