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