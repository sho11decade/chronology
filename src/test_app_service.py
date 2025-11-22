from __future__ import annotations

from typing import Iterable

import pytest
from fastapi.testclient import TestClient

try:  # pragma: no cover - relative import when running tests via package
    from . import app as app_module
except ImportError:  # pragma: no cover - fallback for direct execution
    import app as app_module


@pytest.fixture
def client() -> Iterable[TestClient]:
    with TestClient(app_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_health_endpoint_returns_uptime_and_version(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert "version" in data
    assert "X-Request-ID" in response.headers


def test_health_ready_checks_database(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_request_id_header_is_reused_from_client(client: TestClient) -> None:
    custom_request_id = "test-request-123"
    response = client.get("/health", headers={"X-Request-ID": custom_request_id})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == custom_request_id


def test_unhandled_exception_returns_request_id(client: TestClient) -> None:
    if not any(
        getattr(route, "path", None) == "/_test-error"
        for route in app_module.app.router.routes
    ):
        @app_module.app.get("/_test-error")
        async def _raise_error():  # pragma: no cover - used only for tests
            raise RuntimeError("boom")

    response = client.get("/_test-error")
    assert response.status_code == 500
    data = response.json()
    assert "request_id" in data
    assert data["detail"].startswith("サーバー内部")
    assert response.headers["X-Request-ID"] == data["request_id"]
