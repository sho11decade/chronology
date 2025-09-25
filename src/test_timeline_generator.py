from __future__ import annotations

try:
    from .timeline_generator import generate_timeline
except ImportError:
    # Fallback to absolute imports when running as script
    from timeline_generator import generate_timeline


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
        f"2020年{i // 31 + 1}月{i % 31 + 1}日 重要な出来事がありました。"
        for i in range(180)
    )
    items = generate_timeline(many_events, max_events=100)
    assert len(items) == 100


def test_generate_timeline_handles_fullwidth_digits():
    text = "２０２０年５月１５日、新製品が発表された。"
    items = generate_timeline(text)
    assert any(item.date_iso == "2020-05-15" for item in items)


def test_generate_timeline_merges_events_with_same_date():
    text = (
        "2020年5月1日、東京で国際会議が開催された。"
        "\n2020年5月1日には新技術が合わせて発表された。"
    )
    items = generate_timeline(text)
    assert len(items) == 1
    item = items[0]
    assert "国際会議" in item.description
    assert "新技術" in item.description
    assert item.importance >= 0


def test_generate_timeline_detects_disaster_category_and_location():
    text = "2021年2月13日、福島県沖で震度6強の地震が発生し、住民が避難した。"
    items = generate_timeline(text)
    assert items
    disaster_items = [item for item in items if item.category == "disaster"]
    assert disaster_items
    assert any("福島県" in item.locations for item in disaster_items)


def test_generate_timeline_detects_sports_category():
    text = "2023年3月21日、侍ジャパンがW杯で優勝し、選手たちが歓喜した。"
    items = generate_timeline(text)
    assert any(item.category == "sports" for item in items)
