from __future__ import annotations

from ..services.timeline_generator import generate_timeline


def test_generate_timeline_extracts_events():
    text = """
    令和3年4月1日、東京で新しい教育改革が発表された。これは学校教育に大きな影響を与える。
    2020年5月10日には大阪で国際経済フォーラムが開催された。
    """
    items = generate_timeline(text)
    assert len(items) >= 2

    iso_dates = {item.date_iso for item in items if item.date_iso}
    assert "2021-04-01" in iso_dates

    categories = {item.category for item in items}
    assert "education" in categories
    assert "economy" in categories or "politics" in categories


def test_generate_timeline_limits_events():
    many_events = "\n".join(
        f"2020年1月{i}日 重要な出来事がありました。" for i in range(1, 180)
    )
    items = generate_timeline(many_events, max_events=100)
    assert len(items) == 100
