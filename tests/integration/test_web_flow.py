"""Integration tests for web workflow routes and templates."""

from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient

from news_post_builder.config import Settings
from news_post_builder.web.app import create_app


@pytest.fixture
def web_client(tmp_path: Path) -> TestClient:
    db_file = tmp_path / "app.db"
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        LLM_API_KEY="test_key",
        DATABASE_URL=f"sqlite:///{db_file}",
    )
    app = create_app(settings)
    return TestClient(app, follow_redirects=False)


@respx.mock
def test_web_flow_from_start_to_confirm(web_client: TestClient) -> None:
    respx.get("https://nudvnures.wpenginepowered.com/wp-json/wp/v2/media").respond(200, json=[])
    # 1. GET / redirects to new session
    res_index = web_client.get("/")
    assert res_index.status_code == 303
    redirect_url = res_index.headers["location"]
    session_id = redirect_url.split("/")[-1]

    # 2. GET /session/{id} renders index form
    res_form = web_client.get(redirect_url)
    assert res_form.status_code == 200
    assert "Create WordPress News Post" in res_form.text

    # 3. POST /session/{id}/submit with pasted text
    article_body = (
        "Groundbreaking Fusion Energy Milestone Achieved\n\n"
        "Scientists at the National Ignition Facility have achieved net energy gain from a "
        "controlled fusion reaction for the second consecutive experiment. The achievement "
        "validates mathematical models and provides confidence for prototype commercial reactors."
    )
    res_submit = web_client.post(
        f"/session/{session_id}/submit",
        data={"text": article_body},
    )
    assert res_submit.status_code == 303
    assert res_submit.headers["location"] == f"/session/{session_id}/options"

    # 4. GET /session/{id}/options shows options and recommendation badges
    res_options = web_client.get(f"/session/{session_id}/options")
    assert res_options.status_code == 200
    assert "1. Select a Headline" in res_options.text
    assert "2. Select a Description" in res_options.text
    assert "3. Select Featured Image" in res_options.text
    assert "Top Recommendation" in res_options.text

    # 5. POST /session/{id}/more adds options
    res_more = web_client.post(f"/session/{session_id}/more?target=both")
    assert res_more.status_code == 303

    # 6. POST /session/{id}/select
    res_select = web_client.post(
        f"/session/{session_id}/select",
        data={
            "headline_id": "H1",
            "headline_text": "Fusion Milestone Verified",
            "description_id": "D1",
            "description_text": "Researchers achieved net fusion energy gain twice in a row.",
            "media_id": 4732,
        },
    )
    assert res_select.status_code == 303
    assert res_select.headers["location"] == f"/session/{session_id}/preview"

    # 7. GET /session/{id}/preview
    res_preview = web_client.get(f"/session/{session_id}/preview")
    assert res_preview.status_code == 200
    assert "Final Post Preview" in res_preview.text
    assert "Fusion Milestone Verified" in res_preview.text
    assert "4732" in res_preview.text

    # 8. POST /session/{id}/confirm (Dry-Run)
    res_confirm = web_client.post(f"/session/{session_id}/confirm")
    assert res_confirm.status_code == 200
    assert "Post Confirmed in Dry-Run Mode" in res_confirm.text
    assert "Saved Dry-Run Output" in res_confirm.text


def test_web_flow_fetch_failure_shows_paste_fallback(web_client: TestClient) -> None:
    res_index = web_client.get("/")
    session_id = res_index.headers["location"].split("/")[-1]

    with respx.mock(using="httpx") as respx_mock:
        respx_mock.get("https://news.example.com/bad").respond(404)

        # Submit bad URL
        res_submit = web_client.post(
            f"/session/{session_id}/submit",
            data={"url": "https://news.example.com/bad"},
        )
        assert res_submit.status_code == 200
        assert "Could not access or extract article content" in res_submit.text
        assert "Paste Article Text Directly" in res_submit.text


def test_web_flow_cancel_and_new_routes(web_client: TestClient) -> None:
    # 1. GET /session/new creates a fresh session
    res_new = web_client.get("/session/new")
    assert res_new.status_code == 303
    session_id = res_new.headers["location"].split("/")[-1]

    # 2. POST /session/{id}/cancel cancels the session
    res_cancel = web_client.post(f"/session/{session_id}/cancel")
    assert res_cancel.status_code == 200
    assert res_cancel.json() == {"status": "cancelled", "redirect": "/"}

    # 3. GET /session/{id} on cancelled session redirects to /
    res_get_cancelled = web_client.get(f"/session/{session_id}")
    assert res_get_cancelled.status_code == 303
    assert res_get_cancelled.headers["location"] == "/"
