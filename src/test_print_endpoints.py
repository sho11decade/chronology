from fastapi.testclient import TestClient

from .app import app, startup
from .models import TimelineItem


client = TestClient(app)


def setup_module() -> None:
    # startup イベントを手動で呼び出して share_store などを初期化
    import anyio

    anyio.run(startup)


def _timeline_payload():
    return {
        "title": "印刷テスト",
        "subtitle": "サブタイトル",
        "items": [
            {
                "id": "1",
                "date_text": "2020年1月1日",
                "date_iso": "2020-01-01",
                "title": "イベント1",
                "description": "説明",
                "people": ["人物A"],
                "locations": ["場所A"],
                "category": "history",
                "importance": 0.8,
                "confidence": 0.9,
            }
        ],
    }


def test_print_timeline_endpoint_returns_html():
    resp = client.post("/api/print/timeline", json=_timeline_payload())
    assert resp.status_code == 200
    body = resp.text
    assert "<!DOCTYPE html>" in body
    assert "印刷テスト" in body
    assert "イベント1" in body


def test_print_share_endpoint_not_found(monkeypatch):
    # 共有が無効な場合や存在しない場合の挙動を簡易確認
    from .app import settings

    # 共有を有効化した上で、存在しない share_id を叩く
    monkeypatch.setattr(settings, "enable_sharing", True, raising=False)
    resp = client.get("/api/print/share/nonexistent")
    assert resp.status_code in (403, 404)
