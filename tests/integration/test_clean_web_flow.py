"""Integration tests for clean URL workflow (cookie sessions)."""

from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient

from news_post_builder.config import Settings
from news_post_builder.web.app import create_app


@pytest.fixture
def clean_client(tmp_path: Path) -> TestClient:
    db_file = tmp_path / "app.db"
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        LLM_API_KEY="test_key",
        DATABASE_URL=f"sqlite:///{db_file}",
        WP_PUBLISH_ENABLED=False,
    )
    app = create_app(settings)
    # TestClient maintains session cookies automatically
    return TestClient(app, follow_redirects=False)


@respx.mock
def test_clean_url_full_lifecycle(clean_client: TestClient) -> None:
    respx.get("https://nudvnures.wpenginepowered.com/wp-json/wp/v2/media").respond(200, json=[])

    # 1. GET / renders index form with cookie
    res_home = clean_client.get("/")
    assert res_home.status_code == 200
    assert "Create WordPress News Post" in res_home.text
    assert "npb_session_id" in clean_client.cookies

    # 2. POST /submit
    article_body = (
        "Revolutionary Solar Breakthrough Announced\n\n"
        "Engineers have developed ultra-thin perovskite tandem solar cells reaching record "
        "energy conversion efficiency of thirty-four percent in outdoor trials. "
        "Commercial production lines are set to begin next quarter. "
        "The manufacturing process reduces energy requirements and provides long-term stability "
        "under real-world temperature variations across all global testing environments."
    )
    res_submit = clean_client.post("/submit", data={"text": article_body})
    assert res_submit.status_code == 303
    assert res_submit.headers["location"] == "/options"

    # 3. GET /options
    res_options = clean_client.get("/options")
    assert res_options.status_code == 200
    assert "1. Select a Headline" in res_options.text
    assert "2. Select a Description" in res_options.text
    assert "3. Select Featured Image" in res_options.text

    # 4. POST /more
    res_more = clean_client.post("/more?target=both")
    assert res_more.status_code == 303
    assert res_more.headers["location"] == "/options"

    # 5. POST /select
    res_select = clean_client.post(
        "/select",
        data={
            "headline_id": "H1",
            "headline_text": "Solar Efficiency Reaches Record 34%",
            "description_id": "D1",
            "description_text": "Perovskite tandem cells pass outdoor tests.",
            "media_id": 4749,
        },
    )
    assert res_select.status_code == 303
    assert res_select.headers["location"] == "/preview"

    # 6. GET /preview
    res_preview = clean_client.get("/preview")
    assert res_preview.status_code == 200
    assert "Final Post Preview" in res_preview.text
    assert "Solar Efficiency Reaches Record 34%" in res_preview.text

    # 7. POST /confirm
    res_confirm = clean_client.post("/confirm")
    assert res_confirm.status_code == 200
    assert "Post Confirmed in Dry-Run Mode" in res_confirm.text

    # 8. GET /new starts fresh
    res_new = clean_client.get("/new")
    assert res_new.status_code == 303
    assert res_new.headers["location"] == "/"

    res_home2 = clean_client.get("/")
    assert res_home2.status_code == 200
    assert "Create WordPress News Post" in res_home2.text


def test_clean_cancel_route(clean_client: TestClient) -> None:
    # 1. Start on home
    clean_client.get("/")
    assert "npb_session_id" in clean_client.cookies

    # 2. Cancel
    res_cancel = clean_client.post("/cancel")
    assert res_cancel.status_code == 200
    assert res_cancel.json() == {"status": "cancelled", "redirect": "/"}
