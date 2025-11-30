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


def _image_payload(content: bytes = b"fake-binary", filename: str = "sample.png") -> dict:
    return {"file": (filename, content, "image/png")}


def test_ocr_endpoint_requires_configuration(client: TestClient) -> None:
    response = client.post("/api/ocr", files=_image_payload())
    assert response.status_code == 503
    data = response.json()
    assert "OCR" in data["detail"]


def test_ocr_endpoint_rejects_non_image_file(client: TestClient) -> None:
    response = client.post(
        "/api/ocr",
        files={"file": ("notes.txt", b"dummy", "text/plain")},
    )
    assert response.status_code == 400
    data = response.json()
    assert "画像ファイル" in data["detail"]


def test_ocr_endpoint_returns_text(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(app_module, "has_ocr", lambda: True)

    async def fake_extract_text_from_upload(*args, **kwargs):  # type: ignore[override]
        return "OCR結果", "OCR結果"

    monkeypatch.setattr(app_module, "extract_text_from_upload", fake_extract_text_from_upload)

    response = client.post("/api/ocr?lang=ja", files=_image_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "OCR結果"
    assert data["characters"] == len("OCR結果")


def test_ocr_generate_dag_returns_result(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(app_module, "has_ocr", lambda: True)

    async def fake_extract_text_from_upload(*args, **kwargs):  # type: ignore[override]
        return "年表テキスト", "プレビュー"

    def fake_build_timeline_dag(text: str, *, relation_threshold: float, max_events: int):
        assert text == "年表テキスト"
        assert relation_threshold == pytest.approx(0.6)
        assert max_events == min(12, app_module.settings.max_timeline_events)
        return app_module.TimelineDAG(id="dag-1", title="", text=text, nodes=[], edges=[])

    monkeypatch.setattr(app_module, "extract_text_from_upload", fake_extract_text_from_upload)
    monkeypatch.setattr(app_module, "build_timeline_dag", fake_build_timeline_dag)

    response = client.post("/api/ocr-generate-dag?relation_threshold=0.6&max_events=12", files=_image_payload())
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "dag-1"
    assert data["nodes"] == []
