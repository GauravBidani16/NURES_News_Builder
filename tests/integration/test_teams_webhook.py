"""Integration tests for Microsoft Teams Outgoing Webhook integration."""

import base64
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient

from news_post_builder.config import Settings
from news_post_builder.web.app import create_app

TEST_SECRET_RAW = b"my_teams_secret_1234567890123456"
TEST_SECRET_B64 = base64.b64encode(TEST_SECRET_RAW).decode("utf-8")


def compute_test_hmac(body: bytes, secret_b64: str) -> str:
    key = base64.b64decode(secret_b64)
    sig = hmac.new(key, body, hashlib.sha256).digest()
    return f"HMAC {base64.b64encode(sig).decode('utf-8')}"


@pytest.fixture
def teams_client(tmp_path: Path) -> TestClient:
    db_file = tmp_path / "teams_test.db"
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        LLM_API_KEY="test_key",
        DATABASE_URL=f"sqlite:///{db_file}",
        WP_PUBLISH_ENABLED=False,
        TEAMS_WEBHOOK_SECRET=TEST_SECRET_B64,
        APP_BASE_URL="https://test-nures-builder.onrender.com",
    )
    app = create_app(settings)
    return TestClient(app)


def test_teams_webhook_hmac_unauthorized(teams_client: TestClient) -> None:
    payload = {"type": "message", "text": "help"}
    raw_body = json.dumps(payload).encode("utf-8")

    # Missing header -> 401
    res1 = teams_client.post(
        "/api/webhooks/teams",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert res1.status_code == 401

    # Bad signature -> 401
    res2 = teams_client.post(
        "/api/webhooks/teams",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "HMAC bad_signature_here",
        },
    )
    assert res2.status_code == 401


def test_teams_webhook_help_command(teams_client: TestClient) -> None:
    payload: dict[str, Any] = {
        "type": "message",
        "text": "<at>NewsBot</at> help",
        "from": {"name": "Test User"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    auth_header = compute_test_hmac(raw_body, TEST_SECRET_B64)

    res = teams_client.post(
        "/api/webhooks/teams",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "message"
    assert "Hi! I am the NURES News Post Builder Bot" in data["text"]


def test_teams_webhook_wake_command(teams_client: TestClient) -> None:
    payload: dict[str, Any] = {
        "type": "message",
        "text": "<at>NewsBot</at> wake",
        "from": {"name": "Gaurav"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    auth_header = compute_test_hmac(raw_body, TEST_SECRET_B64)

    res = teams_client.post(
        "/api/webhooks/teams",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "message"
    assert "I am awake and ready" in data["text"]


@respx.mock
def test_teams_webhook_url_submission_and_publish(teams_client: TestClient) -> None:
    # Mock external WordPress media call
    respx.get("https://nudvnures.wpenginepowered.com/wp-json/wp/v2/media").respond(200, json=[])

    # Mock article fetch with >300 characters of substantive body text
    sample_article_html = (
        "<html><body><h1>Clinical Breakthrough in Autoimmune Disorders</h1>"
        "<p>Researchers have identified a novel therapeutic target for autoimmune disorders in a "
        "comprehensive multi-year study published today. The clinical findings represent a "
        "significant step forward in personalized medicine for millions of patients worldwide. "
        "Further Phase II clinical trials are scheduled to commence early next year "
        "across multiple leading university medical centers, with approvals already in place.</p>"
        "</body></html>"
    )
    respx.get("https://example.com/medical-news").respond(
        200,
        text=sample_article_html,
        headers={"content-type": "text/html"},
    )

    # 1. User submits an article URL
    payload: dict[str, Any] = {
        "type": "message",
        "text": "<at>NewsBot</at> https://example.com/medical-news",
        "from": {"name": "Gaurav"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    auth_header = compute_test_hmac(raw_body, TEST_SECRET_B64)

    res = teams_client.post(
        "/api/webhooks/teams",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "message"
    assert "attachments" in data
    attachment = data["attachments"][0]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    card = attachment["content"]
    assert card["type"] == "AdaptiveCard"

    # Verify card contents and OpenUrl actions (1-Click Publish + Customize)
    action_quick = card["actions"][0]
    assert action_quick["type"] == "Action.OpenUrl"
    assert "quick-publish?session_id=" in action_quick["url"]
    assert "https://test-nures-builder.onrender.com" in action_quick["url"]

    action_customize = card["actions"][1]
    assert action_customize["type"] == "Action.OpenUrl"
    assert "options?session_id=" in action_customize["url"]
    assert "https://test-nures-builder.onrender.com" in action_customize["url"]

    # Verify that multiple headline and description options are displayed
    all_card_text = " ".join(item.get("text", "") for item in card["body"])
    assert "H1:" in all_card_text
    assert "H2:" in all_card_text
    assert "D1:" in all_card_text
    assert "D2:" in all_card_text

    # Extract session ID from action URL
    session_id = action_quick["url"].split("session_id=")[1]

    # 2. User requests more options directly in Teams
    more_payload: dict[str, Any] = {
        "type": "message",
        "text": f"<at>NewsBot</at> more {session_id[:8]}",
        "from": {"name": "Gaurav"},
    }
    raw_body_more = json.dumps(more_payload).encode("utf-8")
    auth_header_more = compute_test_hmac(raw_body_more, TEST_SECRET_B64)

    res_more = teams_client.post(
        "/api/webhooks/teams",
        content=raw_body_more,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header_more,
        },
    )
    assert res_more.status_code == 200
    more_data = res_more.json()
    assert "attachments" in more_data
    more_card = more_data["attachments"][0]["content"]
    more_card_text = " ".join(item.get("text", "") for item in more_card["body"])
    assert "H4:" in more_card_text
    assert "D4:" in more_card_text

    # 3. User confirms/publishes post with custom options (H2 D2) directly from Teams
    publish_payload: dict[str, Any] = {
        "type": "message",
        "text": f"<at>NewsBot</at> publish {session_id[:8]} H2 D2",
        "from": {"name": "Gaurav"},
    }
    raw_body_pub = json.dumps(publish_payload).encode("utf-8")
    auth_header_pub = compute_test_hmac(raw_body_pub, TEST_SECRET_B64)

    res_pub = teams_client.post(
        "/api/webhooks/teams",
        content=raw_body_pub,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header_pub,
        },
    )
    assert res_pub.status_code == 200
    pub_data = res_pub.json()
    assert "attachments" in pub_data
    pub_card = pub_data["attachments"][0]["content"]
    # Check that published card contains success confirmation
    found_success = any(
        "Published Successfully" in item.get("text", "")
        for block in pub_card["body"]
        for item in block.get("items", [block])
    )
    assert found_success


@respx.mock
def test_teams_webhook_hyperlinked_title_url_extraction(teams_client: TestClient) -> None:
    respx.get("https://nudvnures.wpenginepowered.com/wp-json/wp/v2/media").respond(200, json=[])
    sample_article_html = (
        "<html><body><h1>Clinical Breakthrough in Autoimmune Disorders</h1>"
        "<p>Researchers have identified a novel therapeutic target for autoimmune disorders in a "
        "comprehensive multi-year study published today. The clinical findings represent a "
        "significant step forward in personalized medicine for millions of patients worldwide. "
        "Further Phase II clinical trials are scheduled to commence early next year "
        "across multiple leading university medical centers, with approvals already in place.</p>"
        "</body></html>"
    )
    respx.get("https://grants.nih.gov/notice.html").respond(
        200,
        text=sample_article_html,
        headers={"content-type": "text/html"},
    )

    # Teams automatically formats pasted URL into a rich title hyperlink
    payload: dict[str, Any] = {
        "type": "message",
        "text": (
            '<p><at>NewsBot</at> <a href="https://grants.nih.gov/notice.html">'
            "NOT-OD-26-131: NIH Operates Under a Continuing Resolution</a></p>"
        ),
        "from": {"name": "Gaurav"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    auth_header = compute_test_hmac(raw_body, TEST_SECRET_B64)

    res = teams_client.post(
        "/api/webhooks/teams",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert "attachments" in data
    card = data["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"

    # Test clicking the 1-click quick-publish button directly
    action_url = card["actions"][0]["url"]
    session_id = action_url.split("session_id=")[1]
    res_quick = teams_client.get(f"/quick-publish?session_id={session_id}")
    assert res_quick.status_code == 200
    assert "Post Confirmed in Dry-Run Mode" in res_quick.text
