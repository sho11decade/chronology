from datetime import datetime

from .models import PrintTimelineOptions, TimelineItem, PrintTimelineRequest, GenerateResponse
from .print_renderer import render_printable_timeline_html


def _sample_item(date_iso: str, date_text: str, title: str) -> TimelineItem:
    return TimelineItem(
        id="1",
        date_text=date_text,
        date_iso=date_iso,
        title=title,
        description="説明",
        people=["人物A"],
        locations=["場所A"],
        category="history",
        importance=0.8,
        confidence=0.9,
    )


def test_render_printable_timeline_basic_html():
    items = [
        _sample_item("2020-01-01", "2020年1月1日", "イベント1"),
    ]
    options = PrintTimelineOptions()
    html = render_printable_timeline_html("タイトル", "サブタイトル", items, options)

    assert "<!DOCTYPE html>" in html
    assert "タイトル" in html
    assert "サブタイトル" in html
    assert "イベント1" in html
    assert "2020年1月1日" in html


def test_print_timeline_request_validation():
    # 空タイトルはバリデーションエラー
    from pytest import raises
    from pydantic import ValidationError

    with raises(ValidationError):
        # items は GenerateResponse と同様の形に合わせる
        PrintTimelineRequest(
            title=" ",
            subtitle="",
            items=[_sample_item("2020-01-01", "2020年1月1日", "イベント1")],
        )

    # 正常ケース
    req = PrintTimelineRequest(
        title="年表",
        subtitle="テスト",
        items=[_sample_item("2020-01-01", "2020年1月1日", "イベント1")],
    )
    assert req.title == "年表"
    assert req.options.page_size == "A4"  # デフォルトが入る
