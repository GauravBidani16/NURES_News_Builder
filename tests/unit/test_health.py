"""Unit tests for the /health endpoint."""

import pytest
from fastapi.testclient import TestClient

from news_post_builder.config import Settings
from news_post_builder.web.app import create_app


@pytest.fixture
def test_client() -> TestClient:
    settings = Settings(
        APP_ENV="test",
        LLM_PROVIDER="mock",
        LLM_API_KEY="",
    )
    app = create_app(settings)
    return TestClient(app)


def test_health_endpoint(test_client: TestClient) -> None:
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_env"] == "test"
    assert data["version"] == "0.1.0"
    assert data["wp_publish_enabled"] is False
