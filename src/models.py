from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime
from typing import List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, HttpUrl, root_validator, validator

LARGE_TEXT_MAX_LENGTH = 200_000


class TimelineItem(BaseModel):
    """Represents a single entry inside the generated chronology."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    date_text: str = Field(..., description="Readable representation of the detected date")
    date_iso: Optional[str] = Field(
        default=None,
        description="ISO-8601 formatted date string when the date could be normalised.",
    )
    title: str = Field(..., description="Short headline describing the event")
    description: str = Field(..., description="Longer summary extracted from the source text")
    people: List[str] = Field(default_factory=list, description="People associated with the event")
    locations: List[str] = Field(default_factory=list, description="Locations related to the event")
    category: str = Field(default="general", description="High-level category of the event")
    importance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Normalised importance score between 0 and 1",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Heuristic confidence score indicating reliability of the event",
    )

    @validator("category")
    def normalise_category(cls, value: str) -> str:
        return value.lower()

    @validator("date_iso")
    def validate_iso(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        # Ensure ISO strings are valid
        try:
            datetime.fromisoformat(value)
            return value
        except ValueError:
            pass

        match = re.fullmatch(r"(-?\d{1,6})-(\d{2})-(\d{2})", value)
        if not match:
            raise ValueError("date_iso must be an ISO-8601 formatted string")

        year, month, day = (int(part) for part in match.groups())
        if not (1 <= month <= 12):
            raise ValueError("date_iso must be an ISO-8601 formatted string")
        last_day = monthrange(max(1, abs(year) or 1), month)[1]
        if not (1 <= day <= last_day):
            raise ValueError("date_iso must be an ISO-8601 formatted string")
        return value


class GenerateRequest(BaseModel):
    text: str = Field(
        ...,
        max_length=LARGE_TEXT_MAX_LENGTH,
        description="Input text from which the timeline should be generated",
    )

    @validator("text")
    def ensure_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("テキストが空です。内容を入力してください。")
        return cleaned


class GenerateResponse(BaseModel):
    items: List[TimelineItem]
    total_events: int
    generated_at: datetime


class UploadResponse(BaseModel):
    filename: str
    characters: int
    text_preview: str
    text: str


class WikipediaImportRequest(BaseModel):
    topic: Optional[str] = Field(
        default=None,
        description="Wikipedia の記事タイトル (例: 坂本龍馬)",
        max_length=300,
    )
    url: Optional[HttpUrl] = Field(
        default=None,
        description="Wikipedia 記事への完全な URL",
    )
    language: str = Field(
        default="ja",
        max_length=12,
        description="MediaWiki 言語コード (例: ja, en)",
    )

    @root_validator
    def ensure_topic_or_url(cls, values: dict) -> dict:
        topic = values.get("topic")
        url = values.get("url")
        if not topic and not url:
            raise ValueError("topic または url のいずれかを指定してください。")

        language = (values.get("language") or "ja").strip()
        if not language:
            raise ValueError("language を指定してください。")
        values["language"] = language
        return values


class SearchResult(BaseModel):
    """タイムライン項目に対する検索結果の詳細。"""

    item: TimelineItem
    score: float = Field(..., ge=0.0, description="検索条件に対する一致スコア")
    matched_keywords: List[str] = Field(
        default_factory=list,
        description="一致したキーワードの一覧（重複除去済み）",
    )
    matched_fields: List[str] = Field(
        default_factory=list,
        description="一致が見つかったフィールド名 (title, description, people など)",
    )


class SearchResponse(BaseModel):
    """検索 API のレスポンス。"""

    keywords: List[str] = Field(..., description="適用されたキーワード")
    categories: List[str] = Field(..., description="適用されたカテゴリフィルター")
    date_from: Optional[date] = Field(
        default=None, description="日付フィルターの開始 (ISO 日付)"
    )
    date_to: Optional[date] = Field(
        default=None, description="日付フィルターの終了 (ISO 日付)"
    )
    match_mode: Literal["any", "all"] = Field(
        ..., description="キーワードマッチの条件 (any=いずれか、all=すべて)"
    )
    total_events: int = Field(..., description="生成された年表の総イベント数")
    total_matches: int = Field(..., description="検索条件に一致したイベント数")
    results: List[SearchResult] = Field(..., description="スコア順に並んだ検索結果")
    generated_at: datetime = Field(..., description="レスポンス生成日時 (UTC)")


class SearchRequest(BaseModel):
    """タイムライン検索のためのリクエスト。"""

    text: str = Field(
        ...,
        max_length=LARGE_TEXT_MAX_LENGTH,
        description="検索対象となる本文。タイムライン生成と同じ前処理を行います。",
    )
    keywords: List[str] = Field(
        default_factory=list,
        description="検索に使用するキーワード（空白・句読点区切り）",
        max_items=20,
    )
    query: Optional[str] = Field(
        default=None,
        description="任意のフリーテキストクエリ。スペースなどで分割して keywords に統合されます。",
    )
    categories: List[str] = Field(
        default_factory=list,
        description="カテゴリフィルター。カテゴリ名は小文字に正規化されます。",
        max_items=20,
    )
    date_from: Optional[date] = Field(
        default=None,
        description="この日付以降のイベントのみを対象とします (ISO 日付)",
    )
    date_to: Optional[date] = Field(
        default=None,
        description="この日付以前のイベントのみを対象とします (ISO 日付)",
    )
    match_mode: Literal["any", "all"] = Field(
        default="any",
        description="キーワード一致条件。any はいずれか一致、all は全キーワード一致。",
    )
    max_results: int = Field(
        default=50,
        ge=1,
        le=5_000,
        description="返却する最大件数。スコアの高い順に切り詰められます。",
    )

    @validator("text")
    def ensure_non_empty_text(cls, value: str) -> str:  # type: ignore[override]
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("テキストが空です。内容を入力してください。")
        return cleaned

    @validator("keywords", each_item=True, pre=True)
    def _normalise_keyword(cls, value: str) -> str:  # type: ignore[override]
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
        raise ValueError("キーワードは空にできません。")

    @validator("categories", each_item=True, pre=True)
    def _normalise_category(cls, value: str) -> str:  # type: ignore[override]
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned:
                return cleaned
        raise ValueError("カテゴリ名は空にできません。")

    @root_validator
    def _merge_query_into_keywords(cls, values: dict) -> dict:  # type: ignore[override]
        keywords: List[str] = values.get("keywords", [])
        query: Optional[str] = values.get("query")
        if query:
            extra_terms = [
                term.strip()
                for term in re.split(r"[\s、,，]+", query)
                if term and term.strip()
            ]
            keywords = [*keywords, *extra_terms]

        # 重複除去（大文字小文字は区別しないが、元の表記を保持）
        deduped: List[str] = []
        seen: set[str] = set()
        for keyword in keywords:
            lowered = keyword.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(keyword)

        values["keywords"] = deduped

        has_keywords = bool(deduped)
        has_category = bool(values.get("categories"))
        has_date_filter = bool(values.get("date_from") or values.get("date_to"))
        if not (has_keywords or has_category or has_date_filter):
            raise ValueError("検索条件を少なくとも1つ指定してください。")

        return values


class WikipediaImportResponse(GenerateResponse):
    source_title: str = Field(..., description="取得した Wikipedia 記事のタイトル")
    source_url: str = Field(..., description="取得した Wikipedia 記事の URL")


class PrintTimelineOptions(BaseModel):
    """印刷用レイアウト・表示オプション。"""

    page_size: Literal["A4", "Letter"] = Field(
        default="A4",
        description="用紙サイズ。現状は A4 / Letter のみ対応。",
    )
    orientation: Literal["portrait", "landscape"] = Field(
        default="portrait",
        description="印刷時の向き。portrait=縦、landscape=横。",
    )
    sort_order: Literal["asc", "desc"] = Field(
        default="asc",
        description="イベント並び順。asc=古い順、desc=新しい順。",
    )
    group_by_century: bool = Field(
        default=False,
        description="世紀単位で見出しを付与してグルーピングするかどうか。",
    )
    show_people: bool = Field(
        default=True,
        description="人物情報を表示するかどうか。",
    )
    show_locations: bool = Field(
        default=True,
        description="場所情報を表示するかどうか。",
    )
    show_category: bool = Field(
        default=True,
        description="カテゴリを表示するかどうか。",
    )


class PrintTimelineRequest(BaseModel):
    """印刷用タイムラインを生成するためのリクエスト。"""

    title: str = Field(..., max_length=200, description="年表タイトル（印刷ヘッダに表示）")
    subtitle: str = Field(
        default="",
        max_length=400,
        description="任意のサブタイトル / 補足説明。空でも可。",
    )
    items: List[TimelineItem] = Field(
        ...,
        min_items=1,
        max_items=5_000,
        description="印刷対象とするタイムライン項目の配列。",
    )
    options: PrintTimelineOptions = Field(
        default_factory=PrintTimelineOptions,
        description="印刷レイアウトおよび表示オプション。",
    )

    @validator("title")
    def _ensure_non_empty_title(cls, value: str) -> str:  # type: ignore[override]
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title は空にできません。")
        return cleaned

    @validator("subtitle")
    def _normalise_subtitle(cls, value: str) -> str:  # type: ignore[override]
        return value.strip()


class ShareCreateRequest(BaseModel):
    """共有データ作成のためのリクエスト。"""

    text: str = Field(..., max_length=LARGE_TEXT_MAX_LENGTH, description="共有対象の本文")
    items: List[TimelineItem] = Field(
        default_factory=list,
        description="クライアント側で用意した年表項目の一覧",
    )
    title: str = Field(default="", max_length=200, description="任意のタイトル")

    @validator("text")
    def ensure_non_empty(cls, value: str) -> str:  # type: ignore[override]
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("テキストが空です。内容を入力してください。")
        return cleaned

    @validator("items")
    def ensure_items_not_empty(cls, value: List[TimelineItem]) -> List[TimelineItem]:
        if not value:
            raise ValueError("共有する年表項目を1件以上指定してください。")
        return value


class ShareCreateResponse(BaseModel):
    id: str = Field(..., description="共有ID")
    url: str = Field(..., description="共有URL（base設定がない場合はAPIのパス）")
    created_at: datetime
    total_events: int
    expires_at: datetime


class ShareGetResponse(BaseModel):
    id: str
    title: str
    text: str
    items: List[TimelineItem]
    created_at: datetime
    expires_at: datetime


class SharePublicResponse(BaseModel):
    """公開用の共有レスポンス（本文は含めない）。"""

    id: str
    title: str
    items: List[TimelineItem]
    created_at: datetime
    expires_at: datetime


