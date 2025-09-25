# chronology Maker

テキストから年表を生成するアプリケーションのバックエンドシステムです。FastAPIを使用して構築されており、テキスト解析、年表生成、ファイルアップロードなどの機能を提供します。

## プロジェクト構成

```
.
|── README.md                # 本ファイル
└── src
    └── |
        ├── app.py             # FastAPIアプリケーションのエントリーポイント
        ├── models.py          # Pydanticモデル定義
        ├── services           # テキスト解析・年表生成ロジック
        ├── utils              # ユーティリティ関数（和暦→西暦変換など）
        └── tests              # pytestベースのユニットテスト
```
## セットアップ手順

```powershell
# 依存関係のインストール
pip install -r requirements.txt
# 開発サーバー起動
uvicorn app:app --reload --port 8000
```
もしくはShellで
```bash
# 依存関係のインストール
pip install -r requirements.txt
# 起動
./run.sh
```
## APIエンドポイント

| メソッド | パス           | 説明                         |
|----------|----------------|------------------------------|
| GET      | `/health`      | ヘルスチェック               |
| POST     | `/api/upload`  | ファイルをアップロードしテキスト抽出 |
| POST     | `/api/generate`| テキストから年表を生成       |

## Render.com無料プランでのデプロイ

このプロジェクトはRender.comの無料プランで簡単にホスティングできます。

### デプロイ手順

1. **GitHubリポジトリの準備**
   - コードをGitHubにプッシュ

2. **Render.comでのセットアップ**
   - [Render.com](https://render.com)でアカウント作成（GitHubアカウントでサインイン推奨）
   - 「New Web Service」を選択
   - GitHubリポジトリを接続
   - `render.yaml`の設定が自動的に読み込まれます

3. **手動設定（render.yamlを使わない場合）**
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `cd src && python -m uvicorn app:app --host 0.0.0.0 --port $PORT`
   - **Python Version**: `3.10.11`

### 無料プランの制限
- 月750時間の稼働時間
- 15分間アクセスがないとスリープ状態になります
- 初回アクセス時にコールドスタートで少し時間がかかります

### デプロイ後のURL
- **API**: `https://your-app-name.onrender.com`
- **API ドキュメント**: `https://your-app-name.onrender.com/docs`
- **ヘルスチェック**: `https://your-app-name.onrender.com/health`

# English Version
This is the backend system for an application that generates chronologies from text. Built using FastAPI, it provides features such as text analysis, chronology generation, and file upload.

## Project Structure

```
.
|── README.md # This file
└── src
└── |
├── app.py # Entry point for the FastAPI application
├── models.py # Pydantic model definition
├── services # Text analysis and chronology generation logic
├── utils # Utility functions (Japanese to Western calendar conversion, etc.)
└── tests # Pytest-based unit tests
```
## Setup Procedure

```powershell
# Install dependencies
pip install -r requirements.txt
# Start the development server
uvicorn app:app --reload --port 8000
```
Or in a shell:
```bash
# Install dependencies
pip install -r requirements.txt
# Start
./run.sh
```
## API Endpoint

| Method | Path | Description |
|----------|----------------|------------------------------|
| GET | `/health` | Health check |
| POST | `/api/upload` | Upload a file and extract text |
| POST | `/api/generate` | Generate a timeline from text |