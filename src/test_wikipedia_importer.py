from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

try:  # pragma: no cover - support running tests from repository root
    from . import app as app_module
    from .wikipedia_importer import WikipediaArticle, fetch_wikipedia_article, requests
except ImportError:  # pragma: no cover - fallback for direct execution
    import app as app_module
    from wikipedia_importer import WikipediaArticle, fetch_wikipedia_article, requests


class _DummyResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:  # pragma: no cover - no failure path in tests
        return None

    def json(self) -> dict:
        return self._payload


def test_fetch_wikipedia_article(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "query": {
            "pages": [
                {
                    "pageid": 1,
                    "title": "坂本龍馬",
                    "extract": "土佐藩出身の志士。\n2020年1月1日に記念式典が開催された。",
                }
            ]
        }
    }

    def fake_get(url: str, params: dict, headers: dict, timeout: int):
        assert "w/api.php" in url
        assert params["titles"] == "坂本龍馬"
        return _DummyResponse(payload)

    monkeypatch.setattr(requests, "get", fake_get)

    article = fetch_wikipedia_article(topic="坂本龍馬", language="ja")
    assert article.title == "坂本龍馬"
    assert article.language == "ja"
    assert article.preview.startswith("土佐藩出身")
    assert "記念式典" in article.text


def test_import_wikipedia_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_article = WikipediaArticle(
        title="坂本龍馬",
        language="ja",
        url="https://ja.wikipedia.org/wiki/%E5%9D%82%E6%9C%AC%E9%BE%8D%E9%A6%AC",
        text="2020年1月1日、東京で記念式典が開催された。",
        preview="2020年1月1日、東京で記念式典が開催された。",
    )

    monkeypatch.setattr(app_module, "DB_PATH", tmp_path / "test.db", raising=False)
    monkeypatch.setattr(app_module, "fetch_wikipedia_article", lambda **_: fake_article)

    with TestClient(app_module.app) as client:
        response = client.post("/api/import/wikipedia", json={"topic": "坂本龍馬"})

    assert response.status_code == 200
    data = response.json()
    assert data["source_title"] == "坂本龍馬"
    assert data["characters"] == len(fake_article.text)
    assert data["items"]
    assert data["total_events"] == len(data["items"])
    assert data["text_preview"].startswith("2020年1月1日")
    assert data["request_id"] is not None