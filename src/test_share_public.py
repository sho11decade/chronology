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


def _create_share(client: TestClient) -> str:
    payload = {"text": "2020年1月1日にテスト。2021年2月3日もテスト。", "title": "公開テスト"}
    res = client.post("/api/share", json=payload)
    assert res.status_code == 200, res.text
    return res.json()["id"]


def test_get_share_items_and_export(client: TestClient) -> None:
    sid = _create_share(client)

    # 公開JSON（itemsのみ）
    res = client.get(f"/api/share/{sid}/items")
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["id"] == sid
    assert data["title"] == "公開テスト"
    assert isinstance(data["items"], list) and len(data["items"]) >= 1
    assert "Cache-Control" in res.headers and "ETag" in res.headers

    # 304 with If-None-Match
    etag = res.headers.get("ETag")
    res2 = client.get(f"/api/share/{sid}/items", headers={"If-None-Match": etag})
    assert res2.status_code == 304

    # エクスポート（添付）
    res3 = client.get(f"/api/share/{sid}/export")
    assert res3.status_code == 200
    assert res3.headers.get("Content-Disposition", "").startswith("attachment;")
    body = res3.json()
    assert body["id"] == sid and "text" in body and "items" in body
