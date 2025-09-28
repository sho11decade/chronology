from __future__ import annotations

from fastapi.testclient import TestClient

try:  # pragma: no cover - allow running tests from repo root
    from . import app as app_module
except ImportError:  # pragma: no cover - fallback for direct execution
    import app as app_module


def _post_search(payload: dict) -> dict:
    with TestClient(app_module.app) as client:
        response = client.post("/api/search", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_search_endpoint_filters_by_keyword() -> None:
    text = (
        "2022年3月1日、大阪で技術展示会が開催された。国内外の企業が参加した。\n"
        "2021年5月20日、東京で教育改革が開始された。大勢の生徒がオンラインで参加した。"
    )

    data = _post_search({"text": text, "keywords": ["大阪"]})

    assert data["total_events"] >= 2
    assert data["total_matches"] == 1

    result = data["results"][0]
    assert "大阪" in result["matched_keywords"][0]
    assert "大阪" in result["item"]["title"] or "大阪" in result["item"]["description"]


def test_search_endpoint_match_all_keywords() -> None:
    text = (
        "2023年4月10日、大阪で国際技術会議が開かれ、新製品が発表された。\n"
        "2023年4月11日、東京で芸術祭が華やかに開催された。"
    )

    data = _post_search(
        {
            "text": text,
            "query": "大阪 技術",
            "match_mode": "all",
        }
    )

    assert data["total_matches"] == 1
    result = data["results"][0]
    assert set(result["matched_keywords"]) >= {"大阪", "技術"}
    assert "title" in result["matched_fields"] or "description" in result["matched_fields"]


def test_search_endpoint_applies_date_filter() -> None:
    text = (
        "2010年6月1日、東京で国際的な経済フォーラムが開催された。\n"
        "2022年9月15日、名古屋でスマートシティプロジェクトが始動した。"
    )

    data = _post_search(
        {
            "text": text,
            "keywords": ["プロジェクト"],
            "date_from": "2020-01-01",
        }
    )

    assert data["total_matches"] == 1
    result = data["results"][0]
    assert result["item"]["date_iso"] >= "2020-01-01"
    assert "date" in result["matched_fields"]
    assert any("プロジェクト" in keyword for keyword in result["matched_keywords"])
