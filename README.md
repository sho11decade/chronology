# Chronology Maker

日本語テキストから高精度な年表を生成する FastAPI ベースのバックエンドです。漢数字や和暦を含む日付抽出、人物・場所の分類、信頼度スコア算出など、日本語特有の表現に最適化したロジックを備えています。

## 主な特徴

- **日本語向け日付解析**: 漢数字・和暦・相対表現（「十年前」など）を正規化し ISO 形式へ変換。曖昧表現（「上旬」「頃」など）も考慮したソートキーを生成します。
- **人物・場所の自動抽出**: 接尾辞辞書と形態的ヒューリスティクスで人物・場所を判別し、イベントごとに整理。
- **信頼度スコア**: 抽出したメタ情報（ISO 日付化の可否、人物・場所の数、文脈量）から 0〜1 の信頼度を算出。
- **Wikipedia 互換の前処理**: 脚注・テンプレート・箇条書きなどのノイズを除去し、文章単位で解析。
- **大容量テキストとファイルアップロード**: 50,000 文字までのテキスト、5MB までの PDF/Word ファイルを扱い、抽出結果を年表化。
- **履歴管理**: SQLite に年表を永続化し、履歴 API から再取得可能。

## プロジェクト構成

```
chronology/
├── Dockerfile
├── README.md
├── run.sh
└── src/
		├── app.py                 # FastAPI エントリポイント
		├── database.py            # SQLite 永続化レイヤー
		├── japanese_calendar.py   # 和暦→西暦変換と漢数字処理
		├── models.py              # Pydantic モデル
		├── text_cleaner.py        # Wikipedia 等のノイズ除去
		├── text_extractor.py      # ファイルアップロードのテキスト抽出
		├── text_features.py       # 辞書・カテゴリ・接尾辞定義
		├── timeline_generator.py  # 年表生成ロジック
		└── test_*.py              # pytest によるユニットテスト
```

## 必要要件

- Python 3.10 以上（推奨 3.10 系）
- Poetry / pip いずれか（本リポジトリでは `pip` 前提）
- SQLite (Python 標準ライブラリで利用可能)

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

## ローカル起動

```powershell
cd chronology/src
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

- 起動後、`http://127.0.0.1:8000/docs` で OpenAPI ドキュメントを確認できます。
- 既定では `src/chronology.db` に SQLite が作成されます。環境変数 `CHRONOLOGY_DB_PATH` で保存先を変更可能。

## テスト

```powershell
cd chronology
.\.venv\Scripts\python.exe -m pytest
```

（macOS / Linux の場合は `source .venv/bin/activate` 後に `python -m pytest`）

## API エンドポイント一覧

| メソッド | パス                | 説明                                           |
|----------|---------------------|------------------------------------------------|
| GET      | `/health`           | ヘルスチェック                                 |
| POST     | `/api/upload`       | PDF / DOCX などをアップロードしてテキスト抽出 |
| POST     | `/api/generate`     | テキストから年表を生成し、DB に保存            |
| GET      | `/api/history`      | 保存済み年表の一覧（最新順・最大 50 件）       |
| GET      | `/api/history/{id}` | 指定 ID の年表詳細を取得                       |

### `/api/generate` レスポンス例

```json
{
	"request_id": 123,
	"items": [
		{
			"id": "...",
			"date_text": "令和三年四月一日",
			"date_iso": "2021-04-01",
			"title": "京都で新しい政策が発表された",
			"description": "令和三年四月一日、京都で新しい政策が発表された。",
			"people": ["山田太郎"],
			"locations": ["京都"],
			"category": "politics",
			"importance": 0.78,
			"confidence": 0.74
		}
	],
	"total_events": 15,
	"generated_at": "2025-09-27T09:00:00.000000"
}
```

## データベース

- SQLite を使用。テーブルは `timeline_requests`（メタ情報）と `timeline_items`（イベント詳細）の 2 つ。
- WAL モードを有効化しているため並列アクセスに強いです。
- `CHRONOLOGY_DB_PATH` を設定すると任意パスへ出力できます。

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
