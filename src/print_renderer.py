from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
from typing import Iterable, List, Optional, Tuple

from .models import PrintTimelineOptions, TimelineItem


@dataclass
class _RenderableItem:
    sort_key: Tuple[Optional[str], str]
    group_label: Optional[str]
    item: TimelineItem


def _parse_date_iso(date_iso: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
    """date_iso から (year, month) をゆるく取り出す。

    - ISO-8601 拡張形式の負年 (例: -0045-03-15) にも対応
    - 月が取れない場合は (year, None)
    - 完全に解釈できない場合は (None, None)
    """

    if not date_iso:
        return None, None

    try:
        # 標準の fromisoformat が扱える範囲
        dt = datetime.fromisoformat(date_iso)
        return dt.year, dt.month
    except Exception:
        pass

    import re

    m = re.fullmatch(r"(-?\d{1,6})-(\d{2})-(\d{2})", date_iso)
    if not m:
        return None, None
    year = int(m.group(1))
    month = int(m.group(2))
    return year, month


def _century_label(year: int) -> str:
    if year <= 0:
        # 紀元前は単純化してそのまま世紀表示
        return f"{abs(year)}年頃 (BCE)"
    century = (year - 1) // 100 + 1
    return f"{century}世紀"


def _build_renderable_items(items: Iterable[TimelineItem], options: PrintTimelineOptions) -> List[_RenderableItem]:
    renderables: List[_RenderableItem] = []
    for item in items:
        year, _month = _parse_date_iso(item.date_iso)
        if year is not None:
            group_label = _century_label(year) if options.group_by_century else None
            sort_key = (f"{year:06d}", item.id)
        else:
            group_label = None
            sort_key = (None, item.id)

        renderables.append(_RenderableItem(sort_key=sort_key, group_label=group_label, item=item))

    reverse = options.sort_order == "desc"
    renderables.sort(key=lambda r: (r.sort_key[0] is None, r.sort_key[0] or "", r.sort_key[1]), reverse=reverse)
    return renderables


def render_printable_timeline_html(title: str, subtitle: str, items: List[TimelineItem], options: Optional[PrintTimelineOptions] = None) -> str:
    """TimelineItem 配列から印刷向けの HTML を生成する。

    返却される HTML は単独でブラウザに表示してそのまま印刷が可能な、
    シンプルな 1 ページのドキュメントを想定している。
    """

    if options is None:
        options = PrintTimelineOptions()

    renderables = _build_renderable_items(items, options)

    orient_css = "portrait" if options.orientation == "portrait" else "landscape"
    page_size = options.page_size

    parts: List[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang=\"ja\">")
    parts.append("<head>")
    parts.append("    <meta charset=\"utf-8\" />")
    parts.append("    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />")
    parts.append("    <title>" + escape(title) + "</title>")
    parts.append("    <style>")
    parts.append("        @page { size: " + page_size + " " + orient_css + "; margin: 20mm; }")
    parts.append("        body { font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #222; }")
    parts.append("        h1 { font-size: 20pt; margin-bottom: 4pt; }")
    parts.append("        h2 { font-size: 12pt; margin-top: 0; color: #555; }")
    parts.append("        .meta { font-size: 9pt; color: #666; margin-bottom: 16pt; }")
    parts.append("        .group-heading { font-size: 12pt; font-weight: bold; border-bottom: 1px solid #aaa; margin-top: 16pt; padding-bottom: 2pt; }")
    parts.append("        .event { margin-top: 8pt; break-inside: avoid; }")
    parts.append("        .event-header { display: flex; gap: 8pt; align-items: baseline; }")
    parts.append("        .event-date { font-weight: bold; white-space: nowrap; }")
    parts.append("        .event-title { font-weight: bold; }")
    parts.append("        .event-body { margin-left: 0; font-size: 10pt; }")
    parts.append("        .chips { margin-top: 2pt; font-size: 8pt; color: #555; }")
    parts.append("        .chip { display: inline-block; border-radius: 10px; border: 1px solid #ccc; padding: 0 4pt; margin-right: 2pt; }")
    parts.append("        .footer { margin-top: 24pt; font-size: 8pt; color: #999; text-align: right; }")
    parts.append("    </style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("    <h1>" + escape(title) + "</h1>")
    if subtitle.strip():
        parts.append("    <h2>" + escape(subtitle.strip()) + "</h2>")
    parts.append("    <div class=\"meta\">合計 " + str(len(items)) + " 件のイベント</div>")

    current_group: Optional[str] = None
    for renderable in renderables:
        group_label = renderable.group_label
        if group_label and group_label != current_group:
            current_group = group_label
            parts.append("    <div class=\"group-heading\">" + escape(group_label) + "</div>")

        item = renderable.item
        parts.append("    <div class=\"event\">")
        parts.append("        <div class=\"event-header\">")
        parts.append("            <div class=\"event-date\">" + escape(item.date_text) + "</div>")
        parts.append("            <div class=\"event-title\">" + escape(item.title) + "</div>")
        parts.append("        </div>")
        parts.append("        <div class=\"event-body\">" + escape(item.description) + "</div>")

        chips: List[str] = []
        if options.show_people and item.people:
            chips.append("人物: " + ", ".join(escape(p) for p in item.people))
        if options.show_locations and item.locations:
            chips.append("場所: " + ", ".join(escape(l) for l in item.locations))
        if options.show_category and item.category:
            chips.append("カテゴリ: " + escape(item.category))
        if chips:
            parts.append("        <div class=\"chips\">")
            for chip in chips:
                parts.append("            <span class=\"chip\">" + chip + "</span>")
            parts.append("        </div>")

        parts.append("    </div>")

    parts.append("    <div class=\"footer\">Generated by Chronology API</div>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)
