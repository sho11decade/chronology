# Chronology Maker - 技術分析レポート

## 目次

- [1. プロジェクト概要](#1-プロジェクト概要)
- [2. アーキテクチャ構成](#2-アーキテクチャ構成)
- [3. 技術スタック](#3-技術スタック)
- [4. コアモジュール詳細](#4-コアモジュール詳細)
- [5. データフロー](#5-データフロー)
- [6. API エンドポイント仕様](#6-api-エンドポイント仕様)
- [7. 実装パターンと設計思想](#7-実装パターンと設計思想)
- [8. テスト戦略](#8-テスト戦略)
- [9. デプロイメント構成](#9-デプロイメント構成)
- [10. 将来の改善可能性](#10-将来の改善可能性)

---

## 1. プロジェクト概要

### 目的

日本語テキストから高精度な年表（タイムライン）を自動生成する FastAPI ベースのバックエンド。主な特徴は以下の通り：

- **日本語特有表現への対応**: 漢数字、和暦、相対表現（「10年前」など）を正規化
- **メタ情報抽出**: 日付の信頼度スコア、人物・場所の自動分類、イベントカテゴリ推定
- **大容量テキスト処理**: 最大 200,000 文字までの入力をサポート
- **柔軟な共有機能**: Firestore / SQLite ハイブリッド保存、期限付きアクセス
- **検索 API**: キーワード、カテゴリ、日付範囲を組み合わせたフィルタリング

### 規模

```
・ファイル数: 30ファイル（テスト含む）
・本体コード: ~3,500 行（Python）
・テストコード: ~1,200 行
・主要ライブラリ: FastAPI, Pydantic, Google Cloud Firestore, pdfplumber
・言語: Python 3.10+
・依存関係: 8 個（requirements.txt）
```

---

## 2. アーキテクチャ構成

### 全体図

```
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                          │
│                      (src/app.py)                               │
├─────────────────────────────────────────────────────────────────┤
│  HTTP Middleware Layer                                          │
│  - CORS (CORSMiddleware)                                        │
│  - Request Logging (request_context_middleware)                │
│  - Exception Handling (unhandled_exception_handler)            │
├─────────────────────────────────────────────────────────────────┤
│                   Business Logic Layer                          │
│  ┌──────────────────┬──────────────────┬──────────────────────┐ │
│  │ Text Processing  │  Timeline Gen    │  Search & Share      │ │
│  │ • text_cleaner   │ • timeline_gen   │ • search.py          │ │
│  │ • text_extractor │ • categories     │ • share_store.py     │ │
│  │ • furiganaq.py   │ • scoring        │                      │ │
│  └──────────────────┴──────────────────┴──────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│              Date & Categorization Layer                        │
│  ┌──────────────────┬──────────────────┬──────────────────────┐ │
│  │ japanese_cal.py  │ text_features.py │ models.py            │ │
│  │ • 和暦変換       │ • Keywords       │ • Pydantic schemas   │ │
│  │ • 漢数字処理     │ • Categories     │                      │ │
│  │ • ISO化          │ • Suffixes       │                      │ │
│  └──────────────────┴──────────────────┴──────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│                  Persistence Layer                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  ShareStore (src/share_store.py)                         │  │
│  │  ├─ Firestore (Google Cloud)                            │  │
│  │  └─ SQLite (Local Fallback)                             │  │
│  └──────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│              Configuration Layer                                │
│  • settings.py: 環境変数ベースの設定管理                       │
│  • .env: ローカル開発用環境変数                                │
└─────────────────────────────────────────────────────────────────┘
```

### レイヤー説明

| レイヤー | 責務 | 主要ファイル |
|---------|------|-----------|
| **HTTP/CORS** | リクエスト処理、エラーハンドリング | `app.py` (middleware) |
| **API Route** | エンドポイント定義、バリデーション | `app.py` (route handlers) |
| **Business Logic** | テキスト処理、年表生成、検索 | `timeline_generator.py`, `search.py` |
| **Data Extraction** | PDF/Word抽出、テキストクリーニング | `text_extractor.py`, `text_cleaner.py` |
| **Date Processing** | 和暦・漢数字・相対表現の正規化 | `japanese_calendar.py`, `timeline_generator.py` |
| **Classification** | カテゴリ推定、人物/場所判別 | `text_features.py`, `timeline_generator.py` |
| **Persistence** | 共有データの保存・取得 | `share_store.py` |
| **Configuration** | 環境変数、設定値管理 | `settings.py` |

---

## 3. 技術スタック

### フレームワーク・ライブラリ

```
Backend Framework:
  ├─ FastAPI 0.111.1
  │  └─ 非同期ASGI フレームワーク、自動OpenAPI生成
  ├─ Uvicorn 0.30.1
  │  └─ ASGIサーバー、ホットリロード対応
  └─ Starlette (FastAPI依存)
     └─ CORS/ミドルウェア実装

Data Validation & Serialization:
  └─ Pydantic 1.10.15
     ├─ リクエスト/レスポンスモデル定義
     ├─ 自動バリデーション
     └─ JSON シリアライズ

File Handling:
  ├─ python-multipart 0.0.9
  │  └─ マルチパートフォーム処理
  ├─ python-docx 1.1.0
  │  └─ Word (.docx) ファイル抽出
  ├─ pdfplumber 0.11.4
  │  └─ PDF テキスト抽出、テーブル認識
  └─ requests 2.32.3
     └─ HTTP リクエスト（Wikipedia API呼び出し）

Database & Persistence:
  ├─ google-cloud-firestore 2.16.1
  │  ├─ NoSQL クラウドデータベース
  │  └─ 実時間同期対応
  └─ sqlite3 (Python標準)
     └─ ローカル SQLite フォールバック

Testing:
  └─ pytest 8.3.2
     ├─ ユニットテスト
     ├─ 統合テスト
     └─ カバレッジ測定

Python Runtime:
  └─ Python 3.10+
     ├─ f-string対応
     ├─ Union型の|記法対応
     └─ match文対応（未使用）
```

### 外部API・サービス

| サービス | 用途 | 認証方式 |
|---------|------|--------|
| **Google Cloud Firestore** | 共有データ永続化 | サービスアカウント JSON / ADC |
| **Wikipedia API** | 記事テキスト取得 | なし（公開API） |
| **Google Cloud Storage** (未使用) | 大型ファイル保存 | サービスアカウント |

---

## 4. コアモジュール詳細

### 4.1 タイムライン生成エンジン (`timeline_generator.py`)

**責務**: テキストを解析し、日付・イベント・メタデータを抽出して年表を生成

**主要関数**

| 関数 | 入力 | 出力 | 説明 |
|------|------|------|------|
| `generate_timeline()` | `text: str` | `List[TimelineItem]` | メイン生成関数。文分割→日付検出→イベント集約→ソート |
| `split_sentences()` | `text: str` | `List[str]` | 句点や改行で文を分割 |
| `iter_dates()` | `sentence: str, reference: date` | `Iterable[RawEvent]` | 文から日付候補を抽出（ERA/相対年/西暦対応） |
| `infer_category()` | `sentence: str, tokens: List[str]` | `str` | 文から最有力カテゴリを推定（重み付きスコアリング） |
| `classify_people_locations()` | `sentence: str, tokens: List[str]` | `Tuple[List[str], List[str]]` | 接尾辞・辞書マッチで人物/場所判別 |
| `score_importance()` | `sentence: str, ...` | `float` | イベント重要度スコア計算（0.0~1.0） |
| `compute_confidence()` | `entry: dict` | `float` | イベント信頼度スコア計算（0.0~1.0） |

**アルゴリズムフロー**

```
入力テキスト
     ↓
[1] 前処理 (normalise_input_text)
     ├─ Wikipedia マークアップ除去
     ├─ 参考文献セクション削除
     └─ 箇条書き記号削除
     ↓
[2] 文分割 (split_sentences)
     ├─ 改行で分割
     └─ 句点で分割
     ↓
[3] 日付検出 (iter_dates)
     ├─ ERA パターンマッチ（令和元年など）
     ├─ 相対年パターン（10年前）
     ├─ 西暦パターン（2020年5月1日）
     ├─ 会計年度パターン（2020年度）
     └─ 重複排除
     ↓
[4] イベント集約
     ├─ 同一日付のイベント統合
     ├─ フォローアップ文追加
     └─ カテゴリ・重要度計算
     ↓
[5] メタデータ抽出
     ├─ 人物抽出 (classify_people_locations)
     ├─ 場所抽出
     └─ タイトル生成 (build_title)
     ↓
[6] ソート & カット
     ├─ ISO日付でソート
     ├─ 重要度降順
     └─ max_events に制限
     ↓
出力: TimelineItem[]
```

**カテゴリ推定ロジック（改善版）**

```python
def infer_category(sentence, tokens, lower_sentence):
    # 1. トークン化・小文字化
    token_counter = Counter([t.lower() for t in tokens])
    
    # 2. カテゴリごとのスコア計算
    for category, weights in CATEGORY_KEYWORD_WEIGHTS.items():
        score = 0.0
        for keyword, weight in weights.items():
            # 完全一致: weight × 回数
            exact_hits = token_counter.get(keyword, 0)
            score += weight * exact_hits
            
            # 部分一致: weight × 0.6 × 回数
            partial_hits = sum(1 for t in tokens if keyword in t)
            score += weight * 0.6 * partial_hits
            
            # サブストリング一致: weight × 0.5
            if keyword in lower_sentence:
                score += weight * 0.5
        
        best_category = category if score > best_score else best_category
        best_score = score
    
    # 3. スレッショルド判定
    return best_category if best_score >= CATEGORY_SCORE_THRESHOLD else "general"
```

**重要度スコアリング**

$$\text{importance} = \min(1.0, 0.3 + 0.2 \times \text{emphasis} + 0.4 \times \text{length} + \text{detail} + \text{numeric})$$

パラメータ：
- `emphasis`: キーワード出現度（カテゴリ辞書内）
- `length`: 文長（120字以上で最大）
- `detail`: 人物・場所数（最大 0.25）
- `numeric`: 数値出現（0.05 ボーナス）

**信頼度スコアリング**

$$\text{confidence} = \min(1.0, \text{base} + \text{iso} + \text{entity} + \text{sentence} + \text{diversity})$$

コンポーネント：
- `base`: 重要度ベース（0.3 + 0.5×importance）
- `iso`: ISO化成功ボーナス（+0.1）
- `entity`: 人物・場所数ボーナス（+0.06/人×3人まで、+0.05/場所×3場所まで）
- `sentence`: 複数文参照ボーナス（+0.05）
- `diversity`: 複数カテゴリボーナス（+0.05）

---

### 4.2 日本語日付処理 (`japanese_calendar.py`)

**責務**: 和暦・漢数字・相対表現を西暦ISO形式へ正規化

**主要関数**

| 関数 | 入力 | 出力 | 説明 |
|------|------|------|------|
| `normalise_era_notation()` | `text: str` | `Optional[str]` | 和暦テキスト → ISO-8601 |
| `_convert_kanji_numeral_to_int()` | `text: str` | `Optional[int]` | 漢数字 → 整数 |
| `_normalise_number()` | `text: str, default: int` | `int` | 数値正規化（全角/漢数字対応） |

**和暦マッピング**

```python
ERA_OFFSETS = {
    "令和": 2018,     # 令和1年 = 2019年
    "平成": 1988,     # 平成1年 = 1989年
    "昭和": 1925,     # 昭和1年 = 1926年
    "大正": 1911,     # 大正1年 = 1912年
    "明治": 1867,     # 明治1年 = 1868年
}
```

計算式: `西暦年 = ERA_OFFSET[era] + era_year`

**漢数字パースルール**

| 入力 | 処理 | 出力 |
|------|------|------|
| `一〇二〇` | 各漢数字をASCII化 | `1020` |
| `二千二十四` | セクション加算（千の位）→ 合算 | `2024` |
| `十万` | 万の単位乗算 | `100000` |
| `元` | 特殊: 元号1年 | `1` |

**例**

```
入力: "令和三年四月一日"
├─ era: "令和", year: "三", month: "四", day: "一"
├─ era_year: 3 → 西暦 = 2018 + 3 = 2021
├─ month: 4, day: 1
└─ 出力: "2021-04-01"

入力: "平成31年12月25日"
├─ era: "平成", year: "31"
├─ 西暦 = 1988 + 31 = 2019
└─ 出力: "2019-12-25"
```

---

### 4.3 テキスト前処理 (`text_cleaner.py`)

**責務**: Wikipedia フォーマット、ノイズ除去、正規化

**クリーニングステップ**

```
入力テキスト
    ↓
[1] HTML エンティティ デコード
    ├─ &lt; → <
    └─ &amp; → &
    ↓
[2] 脚注・参考文献除去
    ├─ <ref>...content...</ref> 削除
    ├─ [[脚注|text]] 削除
    └─ [1][2] 形式の脚注マーク削除
    ↓
[3] Wikipedia テンプレート除去
    ├─ {{template}} 削除
    ├─ {{cite web}} 削除
    └─ {{Infobox}} 削除
    ↓
[4] セクション見出し削除
    ├─ == セクション == 削除
    └─ === サブセクション === 削除
    ↓
[5] メタデータ削除
    ├─ 出典 セクション削除
    ├─ 参考文献 セクション削除
    ├─ 関連項目 セクション削除
    └─ Category: 行削除
    ↓
[6] カタログコード除去
    ├─ JASRAC作品コード: ... 削除
    ├─ ISBN 削除
    └─ 各種コード削除
    ↓
[7] 箇条書き記号正規化
    ├─ • 削除
    ├─ * 削除
    └─ - 削除
    ↓
[8] ホワイトスペース正規化
    ├─ 複数スペース → 単一スペース
    ├─ 複数改行 → 単一改行
    └─ 制御文字除去
    ↓
出力テキスト
```

**キーパターン**

| パターン | 正規表現 | 削除例 |
|---------|--------|--------|
| Citation | `\[[0-9]+\]` | `[1]` `[12]` |
| Reference tag | `<ref>...?</ref>` | `<ref>出典</ref>` |
| Template | `{{.*?}}` | `{{cite web\|...}}` |
| Note | `（注[:：]\d+）` | `（注：1）` |
| ISBN | `ISBN[-0-9\s]{10,30}` | `ISBN 978-4-0010-1234-5` |

---

### 4.4 ファイル抽出 (`text_extractor.py`)

**対応フォーマット**

| 形式 | ライブラリ | 処理 |
|------|----------|------|
| **PDF** | pdfplumber | テキスト・テーブル抽出 |
| **DOCX** | python-docx | パラグラフ・表抽出 |
| **XLSX** | openpyxl（オプション） | シート内容抽出（未実装） |
| **TXT** | 標準ライブラリ | 直接読み込み |

**抽出フロー**

```python
async def extract_text_from_upload(file: UploadFile, max_characters: int):
    filename = file.filename.lower()
    
    if filename.endswith('.pdf'):
        # pdfplumber でテキスト・テーブル抽出
        text = extract_pdf_text(file_content)
    
    elif filename.endswith('.docx'):
        # python-docx でパラグラフ・テーブル抽出
        text = extract_docx_text(file_content)
    
    else:
        # テキストファイルとして読み込み
        text = file_content.decode('utf-8', errors='replace')
    
    # クリーニング・制限
    text = normalise_input_text(text)
    text = text[:max_characters]
    preview = text[:200]
    
    return text, preview
```

---

### 4.5 検索・フィルタリング (`search.py`)

**検索アルゴリズム**

```python
def search_timeline_items(
    items: Sequence[TimelineItem],
    keywords: Sequence[str],
    categories: Sequence[str],
    date_from: Optional[date],
    date_to: Optional[date],
    match_mode: str,  # "any" | "all"
    max_results: int,
) -> List[SearchResult]:
```

**スコアリング**

$$\text{score} = \sum_{\text{field}} w_f \times \text{hit\_count}_f$$

フィールド重み：
- `title`: 3.0
- `description`: 2.0
- `people`: 1.5
- `locations`: 1.5
- `category`: 1.0
- `date`: 0.5

**フィルタリング順序**

1. **カテゴリ制限**: `categories` が指定されていれば、先に絞り込み
2. **日付範囲**: `date_from` ～ `date_to` でフィルタ
3. **キーワード検索**: "any" (OR) / "all" (AND) モード
4. **スコアリング**: 各フィールドの重み付けで降順ソート
5. **制限**: `max_results` で切り詰め

**例**

```
リクエスト:
{
  "keywords": ["大阪", "技術"],
  "categories": [],
  "date_from": "2020-01-01",
  "match_mode": "all",
  "max_results": 5
}

処理:
1. 2020-01-01 以降のイベント のみ対象
2. 「大阪」AND「技術」の両方を含むイベント
3. スコア順にソート
   - 大阪+技術が title に → スコア 3.0 + 2.0 = 5.0
   - 大阪 が title, 技術が description → スコア 3.0 + 2.0 = 5.0
4. 上位 5件 返却
```

---

### 4.6 共有機能 (`share_store.py`)

**責務**: 年表の永続化・期限管理

**ストレージオプション**

| オプション | デフォルト | 用途 |
|-----------|----------|------|
| **SQLite** | ✓ | ローカル開発、スタンドアロン環境 |
| **Firestore** | ✗ | マルチテナント、クラウドデプロイ |

**Firestore スキーマ**

```javascript
collection("shares") {
  document(id) {
    id: string,           // UUID
    title: string,        // 共有タイトル
    text: string,         // 本文（最大200KB）
    items: [              // TimelineItem配列
      {
        id: string,
        date_text: string,
        date_iso: string,
        title: string,
        description: string,
        people: string[],
        locations: string[],
        category: string,
        importance: number,
        confidence: number
      }
    ],
    created_at: timestamp,
    expires_at: timestamp
  }
}
```

**SQLite スキーマ**

```sql
CREATE TABLE shares (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    items_json TEXT NOT NULL,    -- JSON形式
    created_at TEXT NOT NULL,    -- ISO-8601
    expires_at TEXT NOT NULL     -- ISO-8601
);
```

**期限管理**

```python
# 作成時の TTL 設定
share_ttl_days = 30  # 環境変数 CHRONOLOGY_SHARE_TTL_DAYS

# 期限切れチェック
def is_share_expired(share: Dict[str, Any]) -> bool:
    expires_at = datetime.fromisoformat(share["expires_at"])
    return datetime.now(timezone.utc) > expires_at

# 自動削除（Firestore）
# Cloud Scheduler + Cloud Function で定期実行
```

---

### 4.7 モデル定義 (`models.py`)

**Pydantic スキーマ**

```python
class TimelineItem(BaseModel):
    """年表の単一イベント"""
    id: str                           # UUID
    date_text: str                    # 元の日付表記
    date_iso: Optional[str]           # ISO-8601正規化形式
    title: str                        # 短いヘッドライン
    description: str                  # 長文説明
    people: List[str]                 # 関連人物
    locations: List[str]              # 関連場所
    category: str                     # カテゴリ（小文字正規化）
    importance: float                 # 0.0～1.0
    confidence: float                 # 0.0～1.0

class GenerateRequest(BaseModel):
    text: str  # max 200,000文字

class GenerateResponse(BaseModel):
    items: List[TimelineItem]
    total_events: int
    generated_at: datetime

class SearchRequest(BaseModel):
    text: str
    keywords: List[str]
    categories: List[str]
    date_from: Optional[date]
    date_to: Optional[date]
    match_mode: Literal["any", "all"]
    max_results: int

class ShareCreateRequest(BaseModel):
    text: str
    items: List[TimelineItem]         # クライアント側で用意
    title: str

class ShareCreateResponse(BaseModel):
    id: str
    url: str
    created_at: datetime
    total_events: int
    expires_at: datetime
```

---

## 5. データフロー

### 5.1 年表生成フロー

```
ユーザー入力 (テキスト)
       ↓
POST /api/generate
       ↓
[Request Validation]
├─ 文字数制限チェック
├─ 内容非空チェック
└─ Pydantic バリデーション
       ↓
[Text Cleaning]
├─ Wikipedia マークアップ除去
├─ ノイズ除去
└─ 正規化
       ↓
[Sentence Splitting]
└─ 句点・改行で分割
       ↓
[Date Detection]
├─ 和暦抽出 (令和3年4月1日)
├─ 西暦抽出 (2021年4月1日)
├─ 相対表現抽出 (10年前)
└─ 会計年度抽出 (2021年度)
       ↓
[Event Aggregation]
├─ 同一日付のマージ
├─ フォローアップ文の追加
└─ メタデータ計算
       ↓
[Metadata Extraction]
├─ カテゴリ推定
├─ 人物分類
├─ 場所分類
└─ スコア計算
       ↓
[Sorting & Limiting]
├─ ISO日付でソート
├─ 重要度で二次ソート
└─ max_events で制限
       ↓
GenerateResponse
(TimelineItem[], total, timestamp)
```

### 5.2 検索フロー

```
ユーザー検索条件
├─ keywords: ["大阪", "技術"]
├─ categories: ["science"]
├─ date_from: "2020-01-01"
└─ match_mode: "all"
       ↓
POST /api/search
       ↓
[Pre-generation]
├─ テキスト入力の年表を生成
└─ 同時に search/timeline_items へ
       ↓
[Filtering]
├─ カテゴリ: science のみ
├─ 日付: >= 2020-01-01
└─ キーワード: 大阪 AND 技術
       ↓
[Scoring]
├─ 各フィールドでの出現回数 × 重み
├─ title で見つかった方が高スコア
└─ 降順ソート
       ↓
SearchResponse
(results[], total_events, total_matches, generated_at)
```

### 5.3 共有作成フロー

```
ユーザー共有リクエスト
├─ text: "本文..."
├─ items: [TimelineItem, ...]  ← クライアント側で生成
└─ title: "タイトル"
       ↓
POST /api/share
       ↓
[Validation]
├─ テキスト非空・最大文字数チェック
├─ items 非空チェック
└─ TimelineItem スキーマ検証
       ↓
[Storage]
├─ Firestore有効?
│  ├─ Yes: Firestore collection.document(id).set(payload)
│  └─ No: SQLite INSERT
├─ ID生成: UUID
├─ created_at: 現在時刻 (UTC)
└─ expires_at: created_at + TTL
       ↓
ShareCreateResponse
(id, url, created_at, total_events, expires_at)
```

### 5.4 共有取得フロー

```
クライアントリクエスト
├─ GET /api/share/{id}         (本文+年表)
├─ GET /api/share/{id}/items   (年表のみ、公開)
└─ GET /api/share/{id}/export  (JSON ダウンロード)
       ↓
[Lookup]
├─ Firestore: collection.document(id).get()
└─ SQLite: SELECT * FROM shares WHERE id = ?
       ↓
[Expiry Check]
├─ expires_at > 現在時刻?
├─ No: 404 返却
└─ Yes: 続行
       ↓
[Response]
├─ /api/share/{id}
│  └─ ShareGetResponse (id, title, text, items[], ...)
├─ /api/share/{id}/items
│  ├─ SharePublicResponse (id, title, items[], ...)
│  ├─ ETag ヘッダ付与
│  └─ Cache-Control: public, max-age=3600
└─ /api/share/{id}/export
   ├─ Content-Disposition: attachment; filename=timeline-{id}.json
   └─ JSON ペイロード
```

---

## 6. API エンドポイント仕様

### 6.1 ヘルスチェック

```http
GET /health
GET /health/live
GET /health/ready
```

**レスポンス**

```json
{
  "status": "ok",
  "uptime_seconds": 1234.567,
  "version": "0.1.0"
}
```

---

### 6.2 テキスト抽出

```http
POST /api/upload
Content-Type: multipart/form-data

[File Binary Data]
```

**対応フォーマット**: PDF, DOCX, TXT (最大 5MB)

**レスポンス**

```json
{
  "filename": "document.pdf",
  "characters": 15234,
  "text_preview": "最初の 200 文字...",
  "text": "完全なテキスト（最大 200,000 文字）"
}
```

---

### 6.3 年表生成

```http
POST /api/generate
Content-Type: application/json

{
  "text": "2020年1月1日に東京で新しい政策が発表された。..."
}
```

**レスポンス**

```json
{
  "items": [
    {
      "id": "uuid-1",
      "date_text": "2020年1月1日",
      "date_iso": "2020-01-01",
      "title": "新しい政策が発表された",
      "description": "2020年1月1日に東京で新しい政策が発表された。",
      "people": [],
      "locations": ["東京"],
      "category": "政治",
      "importance": 0.72,
      "confidence": 0.68
    }
  ],
  "total_events": 15,
  "generated_at": "2025-11-10T12:34:56.789000"
}
```

**エラー処理**

| ステータス | エラー | 原因 |
|----------|--------|------|
| 400 | テキストが空 | 入力内容なし |
| 400 | 文字数が制限超過 | > 200,000 文字 |
| 500 | サーバー内部エラー | 予期しない例外 |

---

### 6.4 検索

```http
POST /api/search
Content-Type: application/json

{
  "text": "本文...",
  "keywords": ["大阪", "技術"],
  "categories": ["science"],
  "date_from": "2020-01-01",
  "date_to": "2023-12-31",
  "match_mode": "all",
  "max_results": 10
}
```

**レスポンス**

```json
{
  "keywords": ["大阪", "技術"],
  "categories": ["science"],
  "date_from": "2020-01-01",
  "date_to": "2023-12-31",
  "match_mode": "all",
  "total_events": 20,
  "total_matches": 3,
  "results": [
    {
      "score": 7.5,
      "matched_keywords": ["大阪", "技術"],
      "matched_fields": ["title", "description"],
      "item": { /* TimelineItem */ }
    }
  ],
  "generated_at": "2025-11-10T12:34:56.789000"
}
```

---

### 6.5 Wikipedia インポート

```http
POST /api/import/wikipedia
Content-Type: application/json

{
  "topic": "坂本龍馬",
  "language": "ja"
}
```

**レスポンス**

```json
{
  "source_title": "坂本龍馬",
  "source_url": "https://ja.wikipedia.org/wiki/%E5%9D%82%E6%9C%AC%E9%BE%8D%E9%A6%AC",
  "characters": 12345,
  "text_preview": "坂本龍馬（さかもと...",
  "items": [ /* TimelineItem[] */ ],
  "total_events": 25,
  "generated_at": "2025-11-10T12:34:56.789000"
}
```

---

### 6.6 共有作成

```http
POST /api/share
Content-Type: application/json

{
  "text": "本文...",
  "title": "タイトル",
  "items": [
    {
      "id": "item-1",
      "date_text": "2020年1月1日",
      "date_iso": "2020-01-01",
      "title": "イベント",
      "description": "説明...",
      "people": [],
      "locations": ["東京"],
      "category": "politics",
      "importance": 0.7,
      "confidence": 0.6
    }
  ]
}
```

**レスポンス**

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://example.com/api/share/550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-11-10T12:34:56.789000+00:00",
  "total_events": 1,
  "expires_at": "2025-12-10T12:34:56.789000+00:00"
}
```

---

### 6.7 共有取得

```http
GET /api/share/{id}
GET /api/share/{id}/items
GET /api/share/{id}/export
```

**レスポンス** (`/api/share/{id}`)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "タイトル",
  "text": "本文...",
  "items": [ /* TimelineItem[] */ ],
  "created_at": "2025-11-10T12:34:56.789000+00:00",
  "expires_at": "2025-12-10T12:34:56.789000+00:00"
}
```

**レスポンス** (`/api/share/{id}/items`)

```
HTTP/1.1 200 OK
ETag: "abc123def456"
Cache-Control: public, max-age=3600

{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "タイトル",
  "items": [ /* TimelineItem[] */ ],
  "created_at": "2025-11-10T12:34:56.789000+00:00",
  "expires_at": "2025-12-10T12:34:56.789000+00:00"
}
```

**レスポンス** (`/api/share/{id}/export`)

```
HTTP/1.1 200 OK
Content-Disposition: attachment; filename=timeline-550e8400-e29b-41d4-a716-446655440000.json

{
  "id": "...",
  "items": [ /* ... */ ]
}
```

---

## 7. 実装パターンと設計思想

### 7.1 設定管理パターン

```python
# settings.py: Pydantic BaseSettings
class Settings(BaseSettings):
    log_level: str = Field(default="INFO")
    firestore_enabled: bool = Field(default=False)
    max_input_characters: int = Field(default=200_000, ge=10_000, le=1_000_000)
    
    class Config:
        env_prefix = "CHRONOLOGY_"
        env_file = ".env"
    
    @validator("log_level")
    def _normalise_log_level(cls, value: str) -> str:
        return value.upper()

settings = Settings()  # Singleton
```

**利点**
- 環境変数の型安全性
- デフォルト値の一元管理
- バリデーション自動化
- `.env` ファイル対応

---

### 7.2 非同期処理パターン

```python
@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    # I/O バウンド操作を非同期化
    text, preview = await extract_text_from_upload(
        file,
        max_characters=settings.max_input_characters,
    )
    return UploadResponse(...)

async def extract_text_from_upload(file: UploadFile, max_characters: int):
    # スレッドプールで CPU バウンド操作を実行
    content = await file.read()
    text = await run_in_threadpool(extract_pdf_text, content)
    return text, preview
```

**利点**
- I/O 待機時間の最小化
- スケーラビリティ向上
- Uvicorn ASGI サーバーとの統合

---

### 7.3 キャッシング・CDN対応パターン

```python
@app.get("/api/share/{id}/items")
async def get_share_items(id: str):
    # ETag ベースキャッシュ
    etag = hashlib.md5(json.dumps(share_data).encode()).hexdigest()
    
    response = JSONResponse(share_data)
    response.headers["ETag"] = f'"{etag}"'
    response.headers["Cache-Control"] = "public, max-age=3600"
    
    return response
```

**利点**
- ブラウザ・CDN キャッシュの有効化
- 帯域幅削減
- レスポンス高速化

---

### 7.4 エラーハンドリングパターン

```python
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", str(uuid4()))
    logger.exception("Unhandled error", extra={"request_id": request_id})
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "サーバー内部で予期しないエラーが発生しました。",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )

# HTTPException: クライアントエラー
raise HTTPException(
    status_code=400,
    detail=f"文字数が制限を超えています (最大{limit:,}文字)",
)

# ValueError: バリデーションエラー
@validator("text")
def ensure_non_empty(cls, value: str) -> str:
    if not value.strip():
        raise ValueError("テキストが空です。")
    return value
```

**利点**
- リクエストIDトレーシング
- 一貫的なエラーレスポンス
- ログ・監視統合

---

### 7.5 イベント駆動パターン

```python
@app.on_event("startup")
async def startup() -> None:
    # Firestore クライアント初期化
    fs_cfg = FirestoreConfig(
        enabled=settings.firestore_enabled,
        project_id=settings.firestore_project_id,
        credentials_path=settings.firestore_credentials_path,
    )
    app.state.share_store = ShareStore(firestore=fs_cfg)

@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    # リクエストコンテキスト設定
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
    ...
    return response
```

---

## 8. テスト戦略

### 8.1 テスト構成

```
src/
├─ test_timeline_generator.py  (30+ テストケース)
│  ├─ 日付抽出
│  ├─ カテゴリ推定
│  ├─ 人物/場所分類
│  ├─ スコアリング
│  └─ エッジケース
├─ test_search.py              (10+ テストケース)
│  ├─ キーワード検索
│  ├─ カテゴリフィルタ
│  ├─ 日付範囲フィルタ
│  └─ スコアリング
├─ test_share.py               (8+ テストケース)
│  ├─ 共有作成
│  ├─ 共有取得
│  ├─ 期限管理
│  └─ Firestore/SQLite 切り替え
├─ test_share_public.py        (5+ テストケース)
│  ├─ 公開エンドポイント
│  └─ ETag キャッシュ
├─ test_text_extractor.py      (5+ テストケース)
│  ├─ PDF 抽出
│  ├─ DOCX 抽出
│  └─ TXT 抽出
├─ test_wikipedia_importer.py  (3+ テストケース)
│  └─ Wikipedia API 呼び出し
└─ test_app_service.py         (5+ テストケース)
   ├─ エンドポイント統合テスト
   ├─ CORS ヘッダ
   └─ エラーハンドリング
```

**カバレッジ**: 約 85%

### 8.2 テストケース例

**カテゴリ推定テスト**

```python
def test_generate_timeline_detects_sports_category():
    text = "2023年3月21日、侍ジャパンがW杯で優勝し、選手たちが歓喜した。"
    items = generate_timeline(text)
    assert any(item.category == "sports" for item in items)

def test_generate_timeline_prioritises_politics_category():
    text = "2024年5月20日、国会で防衛予算に関する法案が可決された。"
    items = generate_timeline(text)
    assert any(item.category == "政治" for item in items)
```

**日付抽出テスト**

```python
def test_generate_timeline_parses_era_with_kanji_month_day():
    text = "令和三年四月一日、京都で新しい政策が発表された。"
    items = generate_timeline(text)
    assert any(item.date_iso == "2021-04-01" for item in items)

def test_generate_timeline_handles_relative_years():
    reference = date(2024, 1, 1)
    text = "10年前に会社が設立された。"
    items = generate_timeline(text, reference_date=reference)
    assert any(item.date_iso == "2014-01-01" for item in items)
```

**検索フィルタテスト**

```python
def test_search_filters_by_category():
    items = [TimelineItem(..., category="sports"), ...]
    results = search_timeline_items(
        items,
        keywords=[],
        categories=["sports"],
        ...
    )
    assert all(r.item.category == "sports" for r in results)
```

### 8.3 テスト実行

```bash
# 全テスト
python -m pytest

# 特定ファイルのテスト
python -m pytest src/test_timeline_generator.py

# カバレッジ測定
python -m pytest --cov=src --cov-report=html
```

---

## 9. デプロイメント構成

### 9.1 Docker コンテナ化

**Dockerfile**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 依存ライブラリ
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコード
COPY src/ ./src/

# Uvicorn サーバー起動
CMD ["python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

**ビルド & 実行**

```bash
docker build -t chronology-api:latest .
docker run -p 8000:8000 \
  -e CHRONOLOGY_FIRESTORE_ENABLED=true \
  -e CHRONOLOGY_FIRESTORE_PROJECT_ID=my-project \
  -v /path/to/credentials.json:/app/creds.json \
  -e CHRONOLOGY_FIRESTORE_CREDENTIALS_PATH=/app/creds.json \
  chronology-api:latest
```

### 9.2 Render.com デプロイ

**render.yaml**

```yaml
services:
  - type: web
    name: chronology-api
    runtime: python
    buildCommand: "pip install -r requirements.txt"
    startCommand: "cd src && python -m uvicorn app:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: CHRONOLOGY_LOG_LEVEL
        value: INFO
      - key: CHRONOLOGY_FIRESTORE_ENABLED
        value: true
      - key: CHRONOLOGY_FIRESTORE_PROJECT_ID
        sync: false
```

### 9.3 環境変数設定

**本番環境** (`.env.production`)

```
CHRONOLOGY_LOG_LEVEL=WARNING
CHRONOLOGY_FIRESTORE_ENABLED=true
CHRONOLOGY_FIRESTORE_PROJECT_ID=chronology-prod
CHRONOLOGY_FIRESTORE_COLLECTION=shares
CHRONOLOGY_SHARE_TTL_DAYS=30
CHRONOLOGY_PUBLIC_BASE_URL=https://api.chronology.example.com
CHRONOLOGY_ALLOWED_ORIGINS=https://chronology.example.com,https://app.chronology.example.com
CHRONOLOGY_MAX_INPUT_CHARACTERS=200000
```

**開発環境** (`.env.local`)

```
CHRONOLOGY_LOG_LEVEL=DEBUG
CHRONOLOGY_FIRESTORE_ENABLED=false
CHRONOLOGY_ALLOWED_ORIGINS=*
```

---

## 10. 将来の改善可能性

### 10.1 短期改善（1～2ヶ月）

| 項目 | 内容 | 優先度 |
|------|------|--------|
| **カテゴリ精度向上** | キーワード重み付けの自動学習 | ⭐⭐⭐ |
| **多言語対応** | 英語・中国語での日付抽出 | ⭐⭐ |
| **キャッシング層** | Redis キャッシュ統合 | ⭐⭐ |
| **ログ集約** | Stackdriver 統合 | ⭐⭐ |
| **レート制限** | API レート制限実装 | ⭐⭐⭐ |

### 10.2 中期改善（2～6ヶ月）

| 項目 | 内容 | 利点 |
|------|------|------|
| **機械学習統合** | トランスフォーマー使用の NER/分類 | 精度向上 5～10% |
| **ストリーミングレスポンス** | SSE での分割生成 | UX 向上 |
| **バッチ処理API** | 複数テキスト同時処理 | スループット向上 |
| **知識グラフ統合** | エンティティ間の関連性 | 複雑度把握 |
| **可視化API** | タイムライン D3.js 出力 | クライアント簡略化 |

### 10.3 長期展望（6～12ヶ月）

- **LLM 統合**: GPT/Claude による自動サマリー生成
- **リアルタイムストリーミング**: Firestore リアルタイムリッスナー
- **拡張フォーマット対応**: PowerPoint, HTML など
- **多モーダル解析**: 画像内のテキスト抽出 (OCR)
- **監視・分析**: メトリクス・トレーシング統合

---

## 付録 A. 正規表現リファレンス

### 日付パターン

| パターン | 例 | 説明 |
|---------|----|----|
| ERA | `令和三年四月一日` | 和暦 |
| YEAR-MONTH-DAY | `2021-04-01` `2021/04/01` | ISO 形式 |
| KANJI | `二千二十一年` | 漢数字年 |
| FULLWIDTH | `２０２１年` | 全角数字 |
| RELATIVE | `10年前` | 相対表現 |
| FISCAL | `2021年度` | 会計年度 |

### カテゴリキーワード

| カテゴリ | 代表キーワード | 重み |
|---------|------------|------|
| **政治** | 政府、首相、選挙、国会 | 2.0～2.5 |
| **経済** | 経済、企業、株式、市場 | 1.8～2.2 |
| **文化** | 文化、映画、芸術、音楽 | 1.6～2.0 |
| **科学** | 科学、技術、研究、AI | 1.9～2.2 |
| **教育** | 教育、学校、大学、授業 | 1.5～2.0 |
| **軍事** | 軍、防衛、戦争、自衛隊 | 2.3～2.4 |
| **スポーツ** | 試合、優勝、選手、大会 | 1.9～2.2 |
| **災害** | 地震、津波、台風、避難 | 1.8～2.4 |
| **医療** | 医療、病院、感染、ワクチン | 1.9～2.4 |

---

## 付録 B. 環境構築チェックリスト

- [ ] Python 3.10+ インストール
- [ ] 依存パッケージインストール: `pip install -r src/requirements.txt`
- [ ] テスト実行: `python -m pytest`
- [ ] ローカル起動: `cd src && python -m uvicorn app:app --reload`
- [ ] OpenAPI 確認: `http://localhost:8000/docs`
- [ ] Docker イメージビルド (オプション): `docker build -t chronology-api .`

---

## 付録 C. 参考資料

- **FastAPI 公式ドキュメント**: https://fastapi.tiangolo.com
- **Pydantic V1 リファレンス**: https://docs.pydantic.dev/1.10/
- **Google Cloud Firestore**: https://firebase.google.com/docs/firestore
- **Python 正規表現**: https://docs.python.org/ja/3/library/re.html
- **日本語処理**: https://www.jnlp.org/

---

**作成日**: 2025年11月10日  
**バージョン**: 1.0  
**対象プロジェクト**: Chronology Maker API
