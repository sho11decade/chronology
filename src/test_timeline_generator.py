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
    assert "教育" in categories
    assert "経済" in categories or "政治" in categories

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


def test_generate_timeline_prioritises_politics_category():
    text = "2024年5月20日、国会で防衛予算に関する法案が可決され、与党と野党の攻防が続いた。"
    items = generate_timeline(text)
    assert any(item.category == "政治" for item in items)


def test_generate_timeline_detects_health_policy_context():
    text = "2023年11月12日、厚労省がワクチン接種の新指針を発表し、医療機関に通知した。"
    items = generate_timeline(text)
    assert any(item.category == "health" for item in items)


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


def test_generate_timeline_attaches_followup_sentence():
    text = (
        "2021年8月20日、京都で国際会議が開催された。"
        "同日、関連イベントが市内全域で実施された。"
    )
    items = generate_timeline(text)
    assert len(items) == 1
    assert any("関連イベント" in sentence for sentence in items[0].description.split("\n"))
    assert "同日" in items[0].description


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


def test_generate_timeline_parses_kanji_dates():
    text = "二千十四年四月一日、東京で重要な会議が開催された。"
    items = generate_timeline(text)
    assert any(item.date_iso == "2014-04-01" for item in items)


def test_generate_timeline_parses_era_with_kanji_month_day():
    text = "令和三年四月一日、京都で新しい政策が発表された。"
    items = generate_timeline(text)
    assert any(item.date_iso == "2021-04-01" for item in items)


def test_generate_timeline_parses_fiscal_year():
    text = "2020年度、東京都で新たな政策が実施された。"
    items = generate_timeline(text)
    assert items
    assert items[0].date_iso == "2020-04-01"
    assert items[0].date_text.startswith("2020年度")


def test_generate_timeline_parses_era_fiscal_year():
    text = "令和三年度、地域医療プログラムが開始された。"
    items = generate_timeline(text)
    assert items
    assert any(item.date_iso == "2021-04-01" for item in items)


def test_generate_timeline_handles_kanji_relative_years():
    reference = date(2024, 1, 1)
    text = "十年前に会社が創立された。"
    items = generate_timeline(text, reference_date=reference)
    assert any(item.date_iso == "2014-01-01" for item in items)


def test_generate_timeline_sorts_two_digit_years_before_modern_dates():
    text = (
        "45年8月15日、歴史的な宣言が発表された。"
        "\n1946年1月1日、新たな政策が開始された。"
    )
    items = generate_timeline(text)
    assert len(items) >= 2
    assert items[0].date_text.startswith("45年")
    assert items[1].date_iso == "1946-01-01"


def test_generate_timeline_ignores_isbn_sequences():
    text = (
        "ISBN 978-4-0010-1234-5\n"
        "2021年5月10日、東京で歴史資料の公開が行われた。"
    )
    items = generate_timeline(text)
    assert items
    descriptions = "\n".join(item.description for item in items)
    assert "ISBN" not in descriptions
    assert all("978-4-0010-1234-5" not in item.title for item in items)


def test_generate_timeline_excludes_jasrac_work_code():
    text = (
        "JASRAC作品コード：123-4567-8\n"
        "2020年1月1日、東京で新しい楽曲が初演された。"
    )
    items = generate_timeline(text)
    assert items
    for item in items:
        assert "JASRAC作品コード" not in item.description
        assert "JASRAC作品コード" not in item.title


def test_generate_timeline_orders_large_relative_years_first():
    reference = date(2024, 1, 1)
    text = (
        "二万年前、洞窟壁画が描かれた。\n"
        "100年前、京都で記念展示が開催された。"
    )
    items = generate_timeline(text, reference_date=reference)
    assert len(items) >= 2
    assert items[0].date_text.startswith("二万年前")
    assert items[0].date_iso is None
    assert any(item.date_text.startswith("100年前") for item in items)


def test_generate_timeline_title_strips_leading_dash():
    text = "2020年1月1日 - 東京で新年の式典が開催された。"
    items = generate_timeline(text)
    assert items
    assert not items[0].title.startswith("-")


def test_generate_timeline_title_removes_conjunctions():
    text = "2024年1月1日、しかし新プロジェクトが発表された。"
    items = generate_timeline(text)
    assert items
    assert not items[0].title.startswith("しかし")
    assert items[0].title.startswith("新プロジェクト")
