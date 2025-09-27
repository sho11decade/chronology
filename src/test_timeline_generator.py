from __future__ import annotations

from datetime import date

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

    for item in items:
        assert 0.0 <= item.confidence <= 1.0


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
    assert any(item.confidence >= 0.5 for item in items)


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


def test_generate_timeline_strips_wikipedia_markers():
    text = (
        "2020年1月1日、首都圏で大規模な式典が開催された[1]。"
        "<ref>出典: ウィキペディア</ref>{{Infobox}}"
    )
    items = generate_timeline(text)
    assert items
    description = items[0].description
    assert "[1]" not in description
    assert "出典" not in description


def test_generate_timeline_handles_bullet_list():
    text = """
    * 2019年10月22日　即位礼正殿の儀が執り行われた。
    * 2019年11月10日　祝賀御列の儀が行われた。
    """
    items = generate_timeline(text)
    assert len(items) >= 2
    dates = {item.date_iso for item in items if item.date_iso}
    assert "2019-10-22" in dates


def test_generate_timeline_handles_relative_years():
    reference = date(2024, 1, 1)
    text = "10年前に会社が設立された。"
    items = generate_timeline(text, reference_date=reference)
    assert any(item.date_iso == "2014-01-01" for item in items)


def test_generate_timeline_handles_fullwidth_relative_years():
    reference = date(2024, 1, 1)
    text = "１０年前のきょう、重要な合意がなされた。"
    items = generate_timeline(text, reference_date=reference)
    assert any(item.date_iso == "2014-01-01" for item in items)


def test_generate_timeline_title_preserves_clause_without_truncation():
    text = (
        "2024年6月1日、長いタイトルが途中で切れずに伝えたい内容を含むように改善されました。"
        "さらに説明が続く。"
    )
    items = generate_timeline(text)
    assert items
    assert any(
        item.title == "長いタイトルが途中で切れずに伝えたい内容を含むように改善されました"
        for item in items
    )


def test_generate_timeline_prefers_detailed_sentence_for_title():
    text = (
        "2020年1月1日、これは非常に長い説明文でありながら重要な固有名詞は含まれていませんただの説明文です。"
        "\n2020年1月1日、東京都で田中太郎氏が新店舗を開業した。"
    )
    items = generate_timeline(text)
    assert items
    item = items[0]
    assert item.title.startswith("東京都で田中太郎氏が新店舗を開業した")
    assert item.confidence >= 0.5


def test_generate_timeline_confidence_increases_with_additional_context():
    text = (
        "2022年4月10日、東京都で佐藤花子氏が新しい教育プログラムを発表し、文部科学省も支援を表明した。"
        "同日、渋谷区で関連イベントが開催された。"
    )
    items = generate_timeline(text)
    assert items
    item = items[0]
    assert item.confidence >= 0.6


def test_generate_timeline_title_strips_parenthetical_dates():
    text = "2014年4月1日、2014年（平成26年）に改正された法律が施行された。"
    items = generate_timeline(text)
    assert items
    titles = {item.title for item in items}
    assert any("法律が施行された" in title for title in titles)
    assert all("平成26年" not in title or "法律" in title for title in titles)


def test_generate_timeline_preserves_meaningful_parentheses():
    text = "2015年5月1日、東京（渋谷区）で大型の文化イベントが開催された。"
    items = generate_timeline(text)
    assert any("渋谷区" in item.title for item in items)


def test_generate_timeline_ignores_meaningless_date_only_sentences():
    text = "\n".join(
        [
            "2020年5月。",
            "2021年6月",
            "2021年6月15日、東京で新しい交通計画が発表された。",
        ]
    )
    items = generate_timeline(text)
    assert items
    assert len(items) == 1
    assert items[0].date_iso == "2021-06-15"
