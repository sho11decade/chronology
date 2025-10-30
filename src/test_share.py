from __future__ import annotations

from typing import Iterable

import pytest
from fastapi.testclient import TestClient

try:
    from . import app as app_module
except ImportError:
    import app as app_module


@pytest.fixture
def client() -> Iterable[TestClient]:
    with TestClient(app_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_create_and_get_share(client: TestClient) -> None:
    # Create share
    payload = {
        "text": "2020年1月1日にテストイベントがありました。次は2021年2月3日です。",
        "title": "テスト共有",
        "items": [
            {
                "id": "item-1",
                "date_text": "2020年1月1日",
                "date_iso": "2020-01-01",
                "title": "イベントA",
                "description": "テストイベントが発生した。",
                "people": ["山田太郎"],
                "locations": ["東京"],
                "category": "general",
                "importance": 0.7,
                "confidence": 0.6,
            }
        ],
    }
    res = client.post("/api/share", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert "id" in data and data["id"]
    assert "url" in data and data["url"].endswith(data["id"])  # base URL 未設定の場合パスのみ
    assert data["total_events"] == 1

    # Fetch share
    path = data["url"] if data["url"].startswith("/api/") else "/api/share/" + data["id"]
    res2 = client.get(path)
    assert res2.status_code == 200, res2.text
    got = res2.json()
    assert got["id"] == data["id"]
    assert got["title"] == "テスト共有"
    assert isinstance(got["items"], list) and len(got["items"]) == 1
    assert got["items"][0]["title"] == "イベントA"
