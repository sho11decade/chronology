# フロントエンド実装ガイド

フロントから本APIを呼び出すための実装ガイドです。主にブラウザ（Fetch/React）やCloudflare Pages/Workersなどのエッジ環境での利用を想定しています。

- ベースURL: デプロイ先のURL（例: `https://chronology.onrender.com`）
- OpenAPI ドキュメント: `GET /docs`（Swagger UI）, `GET /openapi.json`
- CORS: `CHRONOLOGY_ALLOWED_ORIGINS` で許可オリジンを設定（`*` も可）

---

## よく使うフロー

### 1) テキストから年表生成
- エンドポイント: `POST /api/generate`
- 入力: `{ text: string (<= 50000) }`
- 出力: `{ items: TimelineItem[], total_events, generated_at }`

例（ブラウザ Fetch）:
```ts
const res = await fetch(`${BASE}/api/generate`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ text }),
});
if (!res.ok) throw new Error('failed to generate');
const data = await res.json();
```

### 2) ファイルからテキスト抽出
- エンドポイント: `POST /api/upload`（multipart）
- 入力: `file`（PDF/DOCX等）
- 出力: `{ filename, characters, text_preview, text }`

例:
```ts
const form = new FormData();
form.append('file', file);
const res = await fetch(`${BASE}/api/upload`, { method: 'POST', body: form });
const data = await res.json(); // data.text を /api/generate に渡す
```

### 3) 年表検索
- エンドポイント: `POST /api/search`
- 入力: `{ text, keywords?, query?, categories?, date_from?, date_to?, match_mode?, max_results? }`
- 出力: `SearchResponse`（スコア順の結果）

### 4) 年表を共有として保存 → 後から取得
- 作成: `POST /api/share`（本文から年表を生成し保存）
  - 入力: `{ text, title? }`
  - 出力: `{ id, url, created_at, total_events }`
- 取得（全文）: `GET /api/share/{id}`
  - 出力: `{ id, title, text, items, created_at }`
- 公開用（本文なし・キャッシュ向け）: `GET /api/share/{id}/items`
  - 出力: `{ id, title, items, created_at }`
  - `ETag`/`Cache-Control` 付き。`If-None-Match` で 304 応答。
- JSONダウンロード: `GET /api/share/{id}/export`
  - `Content-Disposition: attachment; filename="timeline-{id}.json"`

---

## 型リファレンス（TypeScript）

```ts
export type TimelineItem = {
  id: string;
  date_text: string;
  date_iso?: string | null;
  title: string;
  description: string;
  people: string[];
  locations: string[];
  category: string; // lowercase
  importance: number; // 0..1
  confidence: number; // 0..1
};

export type GenerateResponse = {
  items: TimelineItem[];
  total_events: number;
  generated_at: string; // ISO UTC
};

export type UploadResponse = {
  filename: string;
  characters: number;
  text_preview: string;
  text: string;
};

export type SearchResult = {
  item: TimelineItem;
  score: number;
  matched_keywords: string[];
  matched_fields: string[];
};

export type SearchResponse = {
  keywords: string[];
  categories: string[];
  date_from?: string | null;
  date_to?: string | null;
  match_mode: 'any' | 'all';
  total_events: number;
  total_matches: number;
  results: SearchResult[];
  generated_at: string;
};

export type ShareCreateResponse = {
  id: string;
  url: string; // PUBLIC_BASE_URL が設定されていればフルURL
  created_at: string;
  total_events: number;
  expires_at: string;
};

export type ShareGetResponse = {
  id: string;
  title: string;
  text: string;
  items: TimelineItem[];
  created_at: string;
  expires_at: string;
};

export type SharePublicResponse = {
  id: string;
  title: string;
  items: TimelineItem[];
  created_at: string;
  expires_at: string;
};
```

---

## 実装スニペット

### React: 共有閲覧（公開JSON）
```tsx
import { useEffect, useState } from 'react';

export function SharedTimeline({ id }: { id: string }) {
  const [data, setData] = useState<SharePublicResponse | null>(null);
  const [etag, setEtag] = useState<string | null>(null);

  useEffect(() => {
    let aborted = false;
    (async () => {
      const headers: Record<string, string> = {};
      if (etag) headers['If-None-Match'] = etag;
      const res = await fetch(`${BASE}/api/share/${id}/items`, { headers });
      if (res.status === 304) return; // キャッシュ利用で差分なし
      const newEtag = res.headers.get('ETag');
      const json = await res.json();
      if (!aborted) {
        setData(json);
        if (newEtag) setEtag(newEtag);
      }
    })();
    return () => { aborted = true };
  }, [id]);

  if (!data) return <div>Loading...</div>;
  return (
    <div>
      <h1>{data.title}</h1>
      <ul>
        {data.items.map(it => (
          <li key={it.id}>
            <strong>{it.date_iso ?? it.date_text}:</strong> {it.title}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

### ブラウザでのエラーハンドリング
```ts
async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    // FastAPI の標準エラー: { detail: string | { msg, loc, type }[] }
    let detail = 'Request failed';
    try { const body = await res.json(); detail = body.detail ?? detail; } catch {}
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}
```

---

## キャッシュとパフォーマンス

- `/api/share/{id}/items` は `Cache-Control: public, max-age=300` と `ETag` を返します
 - `/api/share/{id}/items` は `Cache-Control: public, max-age=300` と `ETag` を返します
  - ブラウザ・CDNの再利用が効き、ページロードが高速化します
  - Cloudflare等のCDNを前段に置く場合、ルールベースのキャッシュを適用可能
 - 共有には有効期限（既定30日）があり、期限切れ後は 404 を返します（`expires_at`で事前に判定可能）
- 生成系（/generate, /search, /upload, /share POST）はキャッシュ非推奨

---

## 環境変数とCORS

- `CHRONOLOGY_ALLOWED_ORIGINS`
  - 例: `*` または `https://app.example,https://another.example`
  - JSON形式（`["*"]`）でも可
- `CHRONOLOGY_PUBLIC_BASE_URL`
  - 共有作成時に返す `url` のベース（例: `https://api.example.com`）
 - `CHRONOLOGY_SHARE_TTL_DAYS`
   - 共有の有効期限（日）。既定30。

---

## エラー仕様

- バリデーションエラー（HTTP 422）
  - Pydanticのエラーリスト（`detail`配列）
- 業務エラー（HTTP 400/403/404など）
  - `{ detail: string }`
- サーバ内部エラー（HTTP 500）
  - `{ detail: string, request_id: string }`（`X-Request-ID` ヘッダにも同値）

---

## よくある質問（FAQ）

- Q. 共有URLをフロントでそのまま開ける？
  - A. `/api/share/{id}/items` はJSONなので、フロントでフェッチしてレンダリングしてください。将来的にHTMLビューを追加可能です。
- Q. 本文を公開したくない
  - A. 公開用は `items` のみ返す `/api/share/{id}/items` を使ってください。本文が必要な場合は `export` を手動配布すると安全です。
- Q. CORSで失敗する
  - A. デプロイ環境の `CHRONOLOGY_ALLOWED_ORIGINS` を確認。`*` または正しいオリジンのカンマ区切りにしてください。
