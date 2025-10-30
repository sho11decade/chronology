# Chronology Maker

日本語テキストから高精度な年表を生成する FastAPI ベースのバックエンドです。漢数字や和暦を含む日付抽出、人物・場所の分類、信頼度スコア算出など、日本語特有の表現に最適化したロジックを備えています。

## 主な特徴

- **日本語向け日付解析**: 漢数字・和暦・相対表現（「十年前」など）を正規化し ISO 形式へ変換。曖昧表現（「上旬」「頃」など）も考慮したソートキーを生成します。
- **人物・場所の自動抽出**: 接尾辞辞書と形態的ヒューリスティクスで人物・場所を判別し、イベントごとに整理。
- **信頼度スコア**: 抽出したメタ情報（ISO 日付化の可否、人物・場所の数、文脈量）から 0〜1 の信頼度を算出。
- **Wikipedia 互換の前処理**: 脚注・テンプレート・箇条書きなどのノイズを除去し、文章単位で解析。
- **大容量テキストとファイルアップロード**: 200,000 文字までのテキスト、5MB までの PDF/Word ファイルを扱い、抽出結果を年表化。
- **柔軟な共有API**: クライアントが生成した年表項目をそのまま保存でき、レスポンスでは共有URLとメタ情報だけを返します。
- **高度な検索フィルタ**: キーワード、カテゴリ、日付範囲を組み合わせた年表検索 API を提供。
- **運用性に配慮した API**: リクエスト ID 自動付与、ライブ/レディネスヘルスチェック、環境変数による設定をサポート。

## プロジェクト構成

```
chronology/
├── Dockerfile
├── README.md
├── run.sh
└── src/
		├── app.py                 # FastAPI エントリポイント
		├── japanese_calendar.py   # 和暦→西暦変換と漢数字処理
		├── models.py              # Pydantic モデル
		├── search.py              # タイムライン検索ロジック
		├── text_cleaner.py        # Wikipedia 等のノイズ除去
		├── text_extractor.py      # ファイルアップロードのテキスト抽出
		├── text_features.py       # 辞書・カテゴリ・接尾辞定義
		├── timeline_generator.py  # 年表生成ロジック
		└── test_*.py              # pytest によるユニットテスト
```

## 必要要件

- Python 3.10 以上（推奨 3.10 系）
- Poetry / pip いずれか（本リポジトリでは `pip` 前提）

## セットアップ

```powershell
cd chronology
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r src/requirements.txt
```

macOS / Linux の場合:

```bash
cd chronology
python -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
```

### 環境変数

アプリの挙動は環境変数（または `.env` ファイル）で調整できます。

- `CHRONOLOGY_ALLOWED_ORIGINS`: CORS で許可するオリジン（カンマ区切り）
- `CHRONOLOGY_LOG_LEVEL`: ログレベル（`DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL`）
- `CHRONOLOGY_ENABLE_REQUEST_LOGGING`: リクエストログの有効・無効（`true`/`false`）
- `CHRONOLOGY_MAX_INPUT_CHARACTERS`: テキスト入力の最大文字数（既定: 200000）
- `CHRONOLOGY_MAX_TIMELINE_EVENTS`: 年表生成で保持する最大イベント数（既定: 500）
- `CHRONOLOGY_MAX_SEARCH_RESULTS`: 検索レスポンスの最大件数（既定: 500）

## ローカル起動

```powershell
cd chronology/src
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

- 起動後、`http://127.0.0.1:8000/docs` で OpenAPI ドキュメントを確認できます。

## テスト

```powershell
cd chronology
.\.venv\Scripts\python.exe -m pytest
```

（macOS / Linux の場合は `source .venv/bin/activate` 後に `python -m pytest`）

## フロントエンド実装ガイド

フロントからの呼び出し手順、型定義、Reactサンプル、キャッシュ/ETagの扱いなどは `docs/frontend-integration.md` を参照してください。

主なポイント:
- 生成・検索・共有のAPIを一連のフローで利用可能
- 共有の公開用エンドポイント（`/api/share/{id}/items`）は ETag 対応でキャッシュしやすい
- CORSは `CHRONOLOGY_ALLOWED_ORIGINS` で制御（`*` やカンマ区切り、JSON表記のどちらも可）

## API エンドポイント一覧

| メソッド | パス                     | 説明                                                 |
|----------|--------------------------|------------------------------------------------------|
| GET      | `/health`                | 稼働状態とアップタイムを返すヘルスチェック           |
| GET      | `/health/live`           | プロセス稼働を確認するライブネスチェック             |
| GET      | `/health/ready`          | アプリケーションの起動状態を確認するレディネス       |
| POST     | `/api/upload`            | PDF / DOCX などをアップロードしてテキスト抽出       |
| POST     | `/api/generate`          | テキストから年表を生成して返す                        |
| POST     | `/api/search`            | 生成した年表をキーワードや日付でフィルタリング        |
| POST     | `/api/import/wikipedia`  | Wikipedia の記事タイトル/URL から本文を取得し年表生成 |
| POST     | `/api/share`             | 本文から年表を生成し、共有IDを発行して保存            |
| GET      | `/api/share/{id}`        | 共有IDに紐づく本文と年表を取得                         |
| GET      | `/api/share/{id}/items`  | 公開用。本文を除いた年表（items）だけを返す            |
| GET      | `/api/share/{id}/export` | ダウンロード用。本文と年表の JSON を添付で返す        |

### `/api/generate` レスポンス例

```json
{
	"items": [
		{
			"id": "...",
			"date_text": "令和三年四月一日",
			"date_iso": "2021-04-01",
			"title": "京都で新しい政策が発表された",
			"description": "令和三年四月一日、京都で新しい政策が発表された。",
			"people": ["山田太郎"],
			"locations": ["京都"],
			"category": "政治",
			"importance": 0.78,
			"confidence": 0.74
		}
	],
	"total_events": 15,
	"generated_at": "2025-09-27T09:00:00.000000"
}
```

### `/api/search` リクエスト・レスポンス例

```jsonc
POST /api/search
{
	"text": "2023年4月10日、大阪で国際技術会議が開催された。2022年3月15日、東京で教育改革が始まった。",
	"keywords": ["大阪", "技術"],
	"match_mode": "all",
	"date_from": "2020-01-01",
	"max_results": 5
}

{
	"keywords": ["大阪", "技術"],
	"categories": [],
	"date_from": "2020-01-01",
	"date_to": null,
	"match_mode": "all",
	"total_events": 2,
	"total_matches": 1,
	"results": [
		{
			"score": 6.3,
			"matched_keywords": ["大阪", "技術"],
			"matched_fields": ["description", "title"],
			"item": {
				"id": "...",
				"date_text": "2023年4月10日",
				"date_iso": "2023-04-10",
				"title": "大阪で国際技術会議が開催された",
				"description": "2023年4月10日、大阪で国際技術会議が開催された。",
				"people": [],
				"locations": ["大阪"],
				"category": "technology",
				"importance": 0.78,
				"confidence": 0.74
			}
		}
	],
	"generated_at": "2025-09-28T09:00:00.000000"
}
```

### `/api/import/wikipedia` リクエスト・レスポンス例

```jsonc
POST /api/import/wikipedia
{
	"topic": "坂本龍馬",
	"language": "ja"
}

{
	"source_title": "坂本龍馬",
	"source_url": "https://ja.wikipedia.org/wiki/%E5%9D%82%E6%9C%AC%E9%BE%8D%E9%A6%AC",
	"characters": 1200,
	"text_preview": "土佐藩出身の志士。...",
	"items": [
		{
			"id": "...",
			"date_text": "1867年11月15日",
			"date_iso": "1867-11-15",
			"title": "坂本龍馬が暗殺された",
			"description": "1867年11月15日、京都・近江屋で坂本龍馬が暗殺された。",
			"people": ["坂本龍馬"],
			"locations": ["京都"],
			"category": "政治",
			"importance": 0.82,
			"confidence": 0.75
		}
	],
	"total_events": 20,
	"generated_at": "2025-09-27T09:00:00.000000"
}
```

## 共有機能（Firestore / SQLite 対応）

本APIは、生成した年表を「共有ID」として保存し、後から取得できる共有機能を提供します。保存先は次の2通りです。

- 既定: ローカルの SQLite（`./data/chronology.db`）
- オプション: Google Cloud Firestore

クライアントが年表を生成し、本文とともに `items` 配列として送信する前提です。サーバー側では受け取った項目をそのまま保存し、レスポンスでは共有 ID・URL・期限のみ返却します。

### 環境変数

`.env` あるいはデプロイ先の環境変数で次を設定します。

- `CHRONOLOGY_ENABLE_SHARING`（既定: `true`）共有APIの有効・無効
- `CHRONOLOGY_PUBLIC_BASE_URL`（任意）共有URLのベース（例: `https://example.com`）
- `CHRONOLOGY_FIRESTORE_ENABLED`（任意）`true` で Firestore を使用（既定はローカル SQLite）
- `CHRONOLOGY_FIRESTORE_PROJECT_ID`（Firestore 使用時推奨）Firestore クライアントで使用する GCP プロジェクトID
- `CHRONOLOGY_FIRESTORE_CREDENTIALS_PATH`（任意）サービスアカウントJSONのパス。省略時は ADC を利用
- `CHRONOLOGY_FIRESTORE_COLLECTION`（任意、既定 shares）共有データを格納するコレクション名
- `CHRONOLOGY_SHARE_TTL_DAYS`（任意、既定30）共有の有効期限（日）。30で約1カ月。
- `CHRONOLOGY_MAX_INPUT_CHARACTERS`（任意、既定200000）共有APIが受け付ける本文の最大文字数
- `CHRONOLOGY_MAX_TIMELINE_EVENTS`（任意、既定500）共有生成時に保存するイベント数の上限
- `CHRONOLOGY_MAX_SEARCH_RESULTS`（任意、既定500）共有検索時に返却する結果数の上限

Firestore を有効化すると、共有データは指定したコレクションにドキュメントとして保存されます（ローカル開発やスタンドアロン運用では SQLite をそのまま利用可能です）。

### API 使用例

```http
POST /api/share
Content-Type: application/json

{
	"text": "2020年1月1日にテストイベントがありました。次は2021年2月3日です。",
	"title": "テスト共有",
	"items": [
		{
			"id": "item-1",
			"date_text": "2020年1月1日",
			"date_iso": "2020-01-01",
			"title": "テストイベント",
			"description": "テキストから抽出したイベントの説明。",
			"people": ["山田太郎"],
			"locations": ["東京"],
			"category": "general",
			"importance": 0.7,
			"confidence": 0.6
		}
	]
}
```

レスポンス例:

```json
{
	"id": "a2e5...",
	"url": "/api/share/a2e5...",  // CHRONOLOGY_PUBLIC_BASE_URL を設定している場合はフルURL
	"created_at": "2025-10-28T00:00:00+00:00",
	"total_events": 2
}
```

取得:

```http
GET /api/share/{id}
```

```json
{
	"id": "a2e5...",
	"title": "テスト共有",
	"text": "2020年1月1日にテストイベントがありました。次は2021年2月3日です。",
	"items": [ { /* TimelineItem */ } ],
	"created_at": "2025-10-28T00:00:00+00:00",
	"expires_at": "2025-11-27T00:00:00+00:00"
}
```

公開JSON（本文なし、キャッシュ対応）:

```http
GET /api/share/{id}/items
```

- ETag/Cache-Control ヘッダが付与され、CDNやブラウザキャッシュで効率よく配信できます。
	期限切れ後は 404 を返します。

JSONダウンロード（添付ファイル）:

```http
GET /api/share/{id}/export
```

- `Content-Disposition: attachment` を付与して `timeline-{id}.json` をダウンロードできます。
	期限切れ後は 404 を返します。

## Docker / Render での利用

### Docker でのビルドと実行

```bash
docker build -t chronology-api .
docker run -p 8000:8000 chronology-api
```

### Render.com でのデプロイ手順

1. リポジトリを GitHub にプッシュ
2. Render で「New Web Service」を選択し、リポジトリを接続
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `cd src && python -m uvicorn app:app --host 0.0.0.0 --port $PORT`

無料プランでは 15 分間アクセスがないとスリープしますが、自動的に復帰します。

## 開発メモ

- 字句・辞書を拡張する際は `text_features.py` を更新し、`pytest` で回帰テストを確認してください。
- 日付処理を追加するときは `timeline_generator.py` の `_parse_sort_candidate` とテスト (`test_timeline_generator.py`) を更新するのが安全です。
- ファイル抽出ロジックは `text_extractor.py` に集約されており、ライブラリ追加時は `src/requirements.txt` も更新してください。

---

## English Summary

Chronology Maker is a FastAPI backend tailored for Japanese text. It normalises kanji numerals, Japanese eras, and relative expressions, extracts people and locations, and returns timelines with confidence scores. See the sections above for setup, API endpoints, and deployment tips.
