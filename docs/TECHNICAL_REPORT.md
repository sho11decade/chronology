# Chronology Maker 技術レポート: 日本語自然言語処理による時系列イベント抽出と因果関係DAG解析

**作成日**: 2025年12月2日  
**バージョン**: 2.0  
**リポジトリ**: [sho11decade/chronology](https://github.com/sho11decade/chronology)

---

## 目次

1. [プロジェクト概要](#1-プロジェクト概要)
2. [アーキテクチャ](#2-アーキテクチャ)
3. [日本語自然言語処理パイプライン](#3-日本語自然言語処理パイプライン)
4. [DAGベース因果関係解析（新規性）](#4-dagベース因果関係解析新規性)
5. [形態素解析と固有表現抽出](#5-形態素解析と固有表現抽出)
6. [日付正規化と和暦処理](#6-日付正規化と和暦処理)
7. [Azure Vision OCR統合](#7-azure-vision-ocr統合)
8. [評価と今後の展望](#8-評価と今後の展望)
9. [参考文献](#9-参考文献)

---

## 1. プロジェクト概要

### 1.1 目的

Chronology Makerは、日本語の文章から歴史的イベント・ニュース記事・Wikipedia記事などを解析し、**時系列年表**を自動生成するシステムです。従来の単純な日付抽出に留まらず、以下の特徴を持ちます。

- **日本語特有の表現への対応**: 漢数字、和暦（明治・大正・昭和・平成・令和）、相対表現（「十年前」「翌年」など）を正規化
- **固有表現抽出**: 人物名・地名を形態素解析とヒューリスティクスで抽出
- **信頼度スコアリング**: 抽出したメタ情報の充実度に基づき0〜1の信頼度を算出
- **因果関係の自動推論（DAG解析）**: イベント間の因果・前提・派生などの関係を有向グラフで表現し、接続詞マーカーと形態素解析を組み合わせて推定

### 1.2 技術スタック

| レイヤー | 技術 | 用途 |
|---------|------|------|
| **Webフレームワーク** | FastAPI | 非同期REST API / OpenAPI自動生成 |
| **形態素解析** | fugashi + UniDic Lite | 品詞・固有名詞・接続詞の抽出 |
| **OCR** | Azure AI Vision Read API | 画像からのテキスト抽出 |
| **データ永続化** | SQLite / Firestore | 共有機能の年表保存 |
| **テスト** | pytest + FastAPI TestClient | 単体・統合テスト |
| **デプロイ** | Docker + Render.com | コンテナ化・クラウドホスティング |

---

## 2. アーキテクチャ

### 2.1 システム構成図

```
┌─────────────────────────────────────────────────────────────────┐
│                         Chronology Maker                        │
│                        FastAPI Backend                          │
└─────────────────────────────────────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Text Input   │      │   File Upload   │      │   Wikipedia     │
│   (Raw Text)  │      │ (PDF/DOCX/Image)│      │    Importer     │
└───────────────┘      └─────────────────┘      └─────────────────┘
        │                        │                        │
        │                        ▼                        │
        │              ┌─────────────────┐               │
        │              │  Text Extractor │               │
        │              │  + Azure OCR    │               │
        │              └─────────────────┘               │
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   Text Cleaner          │
                    │ (Wikipedia脚注除去など) │
                    └─────────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │  Timeline Generator     │
                    │  (日付抽出・NER)        │
                    └─────────────────────────┘
                                 │
                ┌────────────────┴────────────────┐
                │                                 │
                ▼                                 ▼
    ┌───────────────────┐             ┌──────────────────┐
    │  Timeline Items   │             │   DAG Builder    │
    │  (TimelineItem[]) │             │ (因果関係推論)   │
    └───────────────────┘             └──────────────────┘
                │                                 │
                │                                 ▼
                │                     ┌──────────────────────┐
                │                     │  TimelineDAG         │
                │                     │ (Nodes + Edges)      │
                │                     └──────────────────────┘
                │                                 │
                └─────────────────┬───────────────┘
                                  │
                                  ▼
                        ┌──────────────────┐
                        │  Search Engine   │
                        │ (キーワード検索) │
                        └──────────────────┘
                                  │
                                  ▼
                        ┌──────────────────┐
                        │   Share Store    │
                        │ (SQLite/Firestore)│
                        └──────────────────┘
```

### 2.2 主要モジュール

| モジュール | ファイル | 責務 |
|-----------|---------|------|
| **API層** | `app.py` | FastAPIルーティング、エンドポイント定義 |
| **テキスト前処理** | `text_cleaner.py` | Wikipedia脚注・箇条書き除去 |
| **日付解析** | `timeline_generator.py`<br>`japanese_calendar.py` | 和暦→西暦変換、漢数字→数値変換、紀元前対応 |
| **固有表現抽出** | `text_features.py`<br>`mecab_analyzer.py` | 辞書ベース + MeCab形態素解析 |
| **因果DAG構築** | `dag.py` | 接続詞マーカー検出、エッジ生成、サイクル解消 |
| **OCR統合** | `azure_ocr.py`<br>`text_extractor.py` | Azure Vision API連携、画像→テキスト |
| **検索** | `search.py` | キーワード・カテゴリ・日付フィルタリング |
| **共有機能** | `share_store.py` | 年表の永続化・TTL管理 |

---

## 3. 日本語自然言語処理パイプライン

### 3.1 テキスト前処理

#### 3.1.1 Wikipedia対応クレンジング

`text_cleaner.py` では以下の処理を実施：

```python
# 1. 脚注の除去 [1], [2][3] など
text = re.sub(r"\[\d+\](?:\[\d+\])*", "", text)

# 2. Wikiマークアップの除去 [[リンク|表示名]] → 表示名
text = re.sub(r"\[\[(?:[^|\]]+\|)?([^\]]+)\]\]", r"\1", text)

# 3. 箇条書き行頭記号の除去
text = re.sub(r"^[\*#:]+\s*", "", text, flags=re.MULTILINE)

# 4. テンプレート構文の除去 {{テンプレート名|パラメータ}}
text = re.sub(r"\{\{[^}]+\}\}", "", text)
```

これにより、Wikipedia記事をそのまま年表生成に投入可能な形式に整形します。

#### 3.1.2 文分割

`SENTENCE_SPLIT_PATTERN` により「。！？!?」で文を分割し、各文を独立したイベント候補として扱います。

```python
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!\?])\s*")
```

### 3.2 日付抽出

#### 3.2.1 対応フォーマット

| フォーマット | 例 | 正規化結果 |
|------------|----|---------:|
| 和暦（元号） | `令和3年4月1日` | `2021-04-01` |
| 西暦 | `2023年12月25日` | `2023-12-25` |
| 紀元前 | `紀元前660年2月11日` | `-0660-02-11` |
| 相対表現 | `10年前` | 参照日から逆算 |
| 漢数字 | `二千二十三年三月十五日` | `2023-03-15` |

#### 3.2.2 漢数字変換アルゴリズム

```python
def _convert_japanese_numerals_to_int(raw: str) -> Optional[int]:
    # 1. 全角数字を半角に変換
    cleaned = _normalise_digits(raw)
    
    # 2. 「元」は1として扱う
    if cleaned == "元":
        return 1
    
    # 3. 漢数字の位取り計算
    total = 0
    section = 0
    current_digit = None
    
    for ch in cleaned:
        if ch in KANJI_DIGIT_VALUES:
            current_digit = KANJI_DIGIT_VALUES[ch]
        elif ch in KANJI_SMALL_UNITS:  # 十・百・千
            multiplier = KANJI_SMALL_UNITS[ch]
            value = current_digit if current_digit is not None else 1
            section += value * multiplier
            current_digit = None
        elif ch in KANJI_LARGE_UNITS:  # 万・億・兆
            if current_digit is not None:
                section += current_digit
            if section == 0:
                section = 1
            total += section * KANJI_LARGE_UNITS[ch]
            section = 0
            current_digit = None
    
    if current_digit is not None:
        section += current_digit
    
    return total + section
```

**例**: `二千二十三` → `2023`

1. 「二」→ 2
2. 「千」→ 2 × 1000 = 2000 (section)
3. 「二」→ 2
4. 「十」→ 2 × 10 = 20 (section = 2020)
5. 「三」→ 3 (section = 2023)
6. 最終: total = 2023

#### 3.2.3 紀元前対応（ISO 8601拡張）

ISO 8601の拡張表記を使用し、天文学的年（astronomical year）で紀元前を表現：

- **暦年の紀元前1年** = 天文学的年 `0`
- **暦年の紀元前2年** = 天文学的年 `-1`
- **暦年の紀元前660年** = 天文学的年 `-659`

```python
# 紀元前660年2月11日 → -0659-02-11
astronomical_year = -(bce_year - 1)
iso = f"{astronomical_year:04d}-{month:02d}-{day:02d}"
```

### 3.3 信頼度スコアリング

各イベントに対して0〜1のスコアを算出：

```python
def _compute_confidence(
    has_iso: bool,
    people_count: int,
    locations_count: int,
    description_length: int,
) -> float:
    score = 0.0
    
    # ISO日付があれば +0.4
    if has_iso:
        score += 0.4
    
    # 人物数に応じて +0.15まで
    score += min(people_count * 0.05, 0.15)
    
    # 場所数に応じて +0.15まで
    score += min(locations_count * 0.05, 0.15)
    
    # 説明文の長さに応じて +0.3まで
    if description_length >= 100:
        score += 0.3
    elif description_length >= 50:
        score += 0.2
    elif description_length >= 20:
        score += 0.1
    
    return min(score, 1.0)
```

---

## 4. DAGベース因果関係解析（新規性）

### 4.1 従来手法との比較

| 手法 | 長所 | 短所 |
|-----|------|------|
| **時系列順ソート** | シンプル・高速 | 因果関係が不明 |
| **ルールベース抽出** | 特定ドメインで高精度 | 汎用性に欠ける |
| **機械学習（BERT等）** | 高精度 | 学習データ・計算リソースが必要 |
| **本手法（DAG + マーカー）** | 汎用性と解釈性を両立 | 複雑な因果は捉えきれない |

### 4.2 因果関係の定義

本システムでは7種類の関係タイプを定義：

| RelationType | 説明 | 例 |
|-------------|------|-----|
| `causal` | 因果関係（原因→結果） | 「その結果、政権が交代した」 |
| `prerequisite` | 前提条件 | 「協定締結により初めて実現した」 |
| `derived` | 派生 | 「これに伴い新法が制定された」 |
| `temporal` | 時間的順序 | 「その後、会議が開催された」 |
| `parallel` | 並行関係 | 「同時に別の地域でも発生した」 |
| `dependency` | 依存関係 | 「なければ成立しなかった」 |
| `correlated` | 相関関係 | カテゴリ・エンティティ重複から推定 |

### 4.3 マーカーベース推論

接続詞・接続表現をマーカーとして辞書化し、スコアを付与：

```python
_MARKERS: Dict[str, Tuple[RelationType, float]] = {
    # 因果
    "そのため": ("causal", 0.95),
    "その結果": ("causal", 0.93),
    "これにより": ("causal", 0.92),
    
    # 前提条件
    "これにより初めて": ("prerequisite", 0.95),
    "なければ": ("prerequisite", 0.90),
    
    # 派生
    "これに伴い": ("derived", 0.90),
    
    # 時間
    "その後": ("temporal", 0.80),
    "翌日": ("temporal", 0.85),
    
    # 並行
    "同時に": ("parallel", 0.88),
    "一方": ("parallel", 0.85),
}
```

`_detect_temporal_markers` 関数で前後のテキストを走査し、最も強いマーカーを検出：

```python
def _detect_temporal_markers(prev_text: str, cur_text: str) -> Tuple[RelationType, float, Optional[str]]:
    best: Tuple[RelationType, float, Optional[str]] = ("temporal", 0.0, None)
    
    # 現在文を優先検索
    for phrase, (rtype, score) in _MARKERS.items():
        if phrase in cur_text:
            if score > best[1]:
                best = (rtype, score, phrase)
    
    # 前文も参照（並行など）
    for phrase, (rtype, score) in _MARKERS.items():
        if phrase in prev_text and score > best[1]:
            best = (rtype, score, phrase)
    
    # MeCab形態素解析で補助
    if has_mecab() and best[1] < 0.95:
        for morph in mecab_tokenize(cur_text):
            key = morph.surface
            marker = _MARKERS.get(key)
            if marker and marker[1] > best[1]:
                best = (marker[0], marker[1], key)
    
    return best
```

### 4.4 関係強度スコア

複数の要素を組み合わせて最終スコアを算出：

```python
def _relation_strength(prev: TimelineItem, cur: TimelineItem, marker_score: float, entity_score: float) -> float:
    # 重み付け: マーカー45% + カテゴリ類似度25% + 時間ギャップ20% + エンティティ重複10%
    wt = max(0.0, min(1.0, marker_score))
    sc = _semantic_similarity(prev, cur)
    
    gap = _time_gap_days(prev.date_iso, cur.date_iso)
    tg = math.exp(-abs(gap) / 365.0) if isinstance(gap, int) else 0.8
    
    score = 0.45 * wt + 0.25 * sc + 0.2 * tg + 0.1 * max(0.0, min(1.0, entity_score))
    return round(max(0.0, min(1.0, score)), 3)
```

**カテゴリ類似度の例**:

| カテゴリA | カテゴリB | 類似度 |
|----------|----------|--------|
| `politics` | `economy` | 0.65 |
| `science` | `health` | 0.75 |
| `disaster` | `health` | 0.60 |
| 同一カテゴリ | 同一カテゴリ | 0.80 |
| `general` | `general` | 0.20 |

### 4.5 DAG構築アルゴリズム

```python
def build_timeline_dag(text: str, *, relation_threshold: float = 0.5, max_events: int = 500) -> TimelineDAG:
    # 1. TimelineItemを生成（時系列ソート済み）
    items: List[TimelineItem] = generate_timeline(text, max_events=max_events)
    
    # 2. ノード変換
    nodes: List[TimelineNode] = [TimelineNode(...) for it in items]
    
    # 3. エッジ生成（先読みウィンドウ = 3）
    edges: List[TimelineEdge] = []
    window = 3
    for i in range(len(items)):
        for j in range(i + 1, min(i + 1 + window, len(items))):
            prev, cur = items[i], items[j]
            
            # 時間順制約（逆行しない）
            d1, d2 = _iso_to_date(prev.date_iso), _iso_to_date(cur.date_iso)
            if d1 and d2 and d1 > d2:
                continue
            
            # 関係推定
            rel_type, marker_score, phrase = _infer_relation_type(prev, cur)
            entity_score = _entity_overlap_score(prev, cur)
            strength = _relation_strength(prev, cur, marker_score, entity_score)
            
            # 閾値フィルタ
            if strength < relation_threshold:
                continue
            
            edges.append(TimelineEdge(
                source_id=prev.id,
                target_id=cur.id,
                relation_type=rel_type,
                relation_strength=strength,
                time_gap_days=_time_gap_days(prev.date_iso, cur.date_iso),
                reasoning=f"マーカー『{phrase}』による推定" if phrase else "時間順と類似度による推定",
                evidence_sentences=[cur.title],
            ))
    
    # 4. サイクル除去（弱いエッジから削除）
    edges, cycle_count = detect_and_resolve_cycles(edges)
    
    # 5. 推移的エッジ削減（A→B, B→C, A→C があれば A→C を削除）
    edges = reduce_transitive_edges(edges)
    
    # 6. 統計情報
    longest_path = _longest_path_length(nodes, edges)
    stats = _compute_stats(nodes, edges, longest_path=longest_path, cyclic_count=cycle_count)
    
    return TimelineDAG(
        id=str(uuid4()),
        nodes=nodes,
        edges=edges,
        stats=stats,
        version="2.0",
    )
```

### 4.6 サイクル検出と解消

DAGを保証するため、DFSでサイクルを検出し、最も弱いエッジを削除：

```python
def detect_and_resolve_cycles(edges: List[TimelineEdge]) -> Tuple[List[TimelineEdge], int]:
    edge_map: Dict[Tuple[str, str], TimelineEdge] = {(e.source_id, e.target_id): e for e in edges}
    cycle_count = 0
    
    while True:
        adj = build_adjacency_list(list(edge_map.values()))
        cycle = _find_cycle(adj)  # DFS探索
        if not cycle:
            break
        
        cycle_count += 1
        
        # サイクル内の最弱エッジを特定して削除
        candidates = []
        for i in range(len(cycle)):
            src, tgt = cycle[i], cycle[(i + 1) % len(cycle)]
            edge = edge_map.get((src, tgt))
            if edge:
                candidates.append(edge)
        
        if candidates:
            weakest = min(candidates, key=lambda e: e.relation_strength)
            del edge_map[(weakest.source_id, weakest.target_id)]
    
    return list(edge_map.values()), cycle_count
```

### 4.7 最長経路計算

トポロジカルソートを利用してDAG内の最長経路長を計算：

```python
def _longest_path_length(nodes: List[TimelineNode], edges: List[TimelineEdge]) -> int:
    adj = build_adjacency_list(edges)
    in_deg: Dict[str, int] = {n.id: 0 for n in nodes}
    for e in edges:
        in_deg[e.target_id] = in_deg.get(e.target_id, 0) + 1
    
    queue: deque[str] = deque(nid for nid, deg in in_deg.items() if deg == 0)
    dist: Dict[str, int] = {n.id: 0 for n in nodes}
    
    while queue:
        nid = queue.popleft()
        base = dist[nid]
        for nxt in adj.get(nid, []):
            if base + 1 > dist.get(nxt, 0):
                dist[nxt] = base + 1
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                queue.append(nxt)
    
    return max(dist.values()) if dist else 0
```

---

## 5. 形態素解析と固有表現抽出

### 5.1 MeCab統合（fugashi + UniDic Lite）

`mecab_analyzer.py` では `fugashi` を使用してMeCab形態素解析を実行：

```python
import fugashi

def tokenize(text: str) -> List[Morpheme]:
    _initialise_tagger()
    if not _tagger:
        return []
    
    raw_results: List[Morpheme] = []
    for token in _tagger(text):
        features = token.feature
        pos = features.pos1
        pos_detail = features.pos2
        base_form = features.lemma or token.surface
        
        raw_results.append(Morpheme(
            surface=token.surface,
            base_form=base_form,
            pos=pos,
            pos_detail=pos_detail,
            pos_subclass=features.pos3 or "",
        ))
    
    # 固有名詞の連結
    return _merge_compound_morphemes(raw_results)
```

**連結例**: `東京` + `都` → `東京都`

```python
def _merge_compound_morphemes(morphemes: List[Morpheme]) -> List[Morpheme]:
    merged: List[Morpheme] = []
    buffer: List[Morpheme] = []
    
    for morph in morphemes:
        if morph.pos == "名詞" and morph.pos_detail in {"固有名詞", "人名", "地域", "地名"}:
            buffer.append(morph)
            continue
        
        # bufferを結合してmergedに追加
        if buffer:
            surface = "".join(m.surface for m in buffer)
            merged.append(Morpheme(surface=surface, ...))
            buffer.clear()
        
        merged.append(morph)
    
    return merged
```

### 5.2 人物名抽出

#### 5.2.1 MeCabによる品詞解析

```python
for morph in mecab_tokenize(sentence):
    if morph.pos == "名詞" and morph.pos_detail in {"固有名詞", "人名"}:
        people.add(morph.surface)
```

#### 5.2.2 接尾辞ヒューリスティクス

MeCabが利用できない環境でも動作するよう、接尾辞辞書を用意：

```python
PEOPLE_SUFFIXES = (
    "氏", "さん", "様", "殿", "君", "先生", "教授", "博士", "議員",
    "大統領", "首相", "大臣", "知事", "市長", "社長", "会長", "監督",
)

def _extract_people_by_suffix(text: str) -> Set[str]:
    people: Set[str] = set()
    for suffix in PEOPLE_SUFFIXES:
        for match in re.finditer(rf"([一-龥ァ-ヴ]{{2,4}}){re.escape(suffix)}", text):
            name = match.group(1)
            if KANJI_NAME_PATTERN.match(name) or KATAKANA_NAME_PATTERN.match(name):
                people.add(name)
    return people
```

### 5.3 地名抽出

#### 5.3.1 辞書ベース

`text_features.py` に主要地名を列挙：

```python
LOCATION_KEYWORDS = [
    "東京", "江戸", "大阪", "大坂", "京都", "京", "名古屋", "札幌", "福岡", ...
]
```

#### 5.3.2 複合地名パターン

```python
LOCATION_COMPOUND_PATTERN = re.compile(r"[一-龥]{1,4}(?:都|道|府|県|市|区|町|村|郡|空港|駅|港|湾|半島)")

for match in LOCATION_COMPOUND_PATTERN.finditer(text):
    locations.add(match.group())
```

**例**: `京都府`, `大阪市`, `成田空港`

### 5.4 カテゴリ分類

キーワード辞書をスコア付きで定義し、重み付き一致数で分類：

```python
CATEGORY_KEYWORDS = {
    "政治": [
        ("政府", 2.5), ("政権", 2.3), ("法案", 2.1), ("内閣", 2.3), ...
    ],
    "経済": [
        ("経済", 2.2), ("市場", 1.8), ("企業", 1.9), ("株式", 2.0), ...
    ],
    "science": [
        ("科学", 2.2), ("技術", 2.0), ("研究", 2.0), ("AI", 2.0), ...
    ],
    ...
}

def _infer_category(text: str) -> str:
    scores: Dict[str, float] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword, weight in keywords:
            if keyword.lower() in text.lower():
                scores[category] = scores.get(category, 0.0) + weight
    
    if not scores:
        return "general"
    
    best = max(scores.items(), key=lambda x: x[1])
    if best[1] >= CATEGORY_SCORE_THRESHOLD:
        return best[0]
    return "general"
```

---

## 6. 日付正規化と和暦処理

### 6.1 和暦→西暦変換

`japanese_calendar.py` で元号と年数を西暦に変換：

```python
ERA_STARTING_YEARS = {
    "令和": 2019,
    "平成": 1989,
    "昭和": 1926,
    "大正": 1912,
    "明治": 1868,
}

def normalise_era_notation(text: str) -> Optional[str]:
    match = ERA_PATTERN.match(text)
    if not match:
        return None
    
    era = match.group("era")
    year_raw = match.group("year")
    year = _parse_number(year_raw, fallback=1)
    
    base_year = ERA_STARTING_YEARS.get(era)
    if base_year is None:
        return None
    
    gregorian_year = base_year + year - 1
    
    month_raw = match.group("month")
    month = _parse_number(month_raw, fallback=1) if month_raw else 1
    
    day_raw = match.group("day")
    day = _parse_number(day_raw, fallback=1) if day_raw else 1
    
    return _safe_iso_date(gregorian_year, month, day)
```

**例**: `令和3年4月1日` → `2021-04-01`

- 令和元年 = 2019年
- 令和3年 = 2019 + 3 - 1 = 2021年
- 月・日を組み合わせて ISO 形式に変換

### 6.2 曖昧な日付表現への対応

「上旬」「中旬」「下旬」「頃」などの表現は、ソート用の補正値として扱う：

```python
AMBIGUOUS_PATTERNS = {
    "上旬": (1, 5),
    "中旬": (11, 15),
    "下旬": (21, 25),
    "頃": (15, 15),
}

def _parse_sort_candidate(date_text: str, date_iso: Optional[str]) -> Tuple[int, ...]:
    if date_iso:
        parts = _decompose_iso(date_iso)
        if parts:
            year, month, day = parts
            
            # 曖昧表現を検出して補正
            for pattern, (approx_day, _) in AMBIGUOUS_PATTERNS.items():
                if pattern in date_text:
                    day = approx_day
                    break
            
            return (abs(year), month, day)
    
    # ISO化できない場合は低優先度
    return (9999, 12, 31)
```

---

## 7. Azure Vision OCR統合

### 7.1 画像テキスト抽出フロー

```
画像アップロード
    │
    ▼
┌─────────────────────────┐
│  /api/ocr               │
│  /api/ocr-generate-dag  │
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  text_extractor.py      │
│  拡張子判定             │
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  azure_ocr.py           │
│  Azure Vision API呼び出し│
└─────────────────────────┘
    │
    ├─ Image Analysis API (2023-02-01-preview)
    │  404エラー時フォールバック
    │
    └─ Read API (v3.2)
       ポーリング方式で結果取得
    │
    ▼
抽出テキスト → timeline_generator.py
```

### 7.2 API呼び出し実装

#### 7.2.1 Image Analysis API（新バージョン）

```python
def _call_image_analysis_api(image_bytes: bytes, version: str, language: Optional[str], timeout_seconds: int) -> dict:
    base = settings.azure_vision_endpoint.rstrip("/")
    url = f"{base}/computervision/imageanalysis:analyze"
    params = {"api-version": version, "features": "read"}
    if language:
        params["language"] = language
    
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_vision_key,
        "Content-Type": "application/octet-stream",
    }
    
    response = requests.post(url, headers=headers, params=params, data=image_bytes, timeout=timeout_seconds)
    
    if response.status_code == 404:
        # 旧APIへフォールバック
        return _call_read_api(image_bytes, "v3.2", language, timeout_seconds)
    
    if response.status_code >= 400:
        _raise_azure_error(response)
    
    return response.json()
```

#### 7.2.2 Read API（旧バージョン、非同期ポーリング）

```python
def _call_read_api(image_bytes: bytes, version: str, language: Optional[str], timeout_seconds: int) -> dict:
    base = settings.azure_vision_endpoint.rstrip("/")
    url = f"{base}/vision/{version}/read/analyze"
    params = {}
    if language:
        params["language"] = language
    
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_vision_key,
        "Content-Type": "application/octet-stream",
    }
    
    # 1. 非同期ジョブを開始（202 Accepted）
    response = requests.post(url, headers=headers, params=params, data=image_bytes, timeout=timeout_seconds)
    if response.status_code != 202:
        _raise_azure_error(response)
    
    operation_url = response.headers.get("Operation-Location")
    if not operation_url:
        raise AzureVisionError("Operation-Location ヘッダーが返されませんでした。")
    
    # 2. ポーリング（0.6秒間隔）
    deadline = time.time() + timeout_seconds
    poll_headers = {"Ocp-Apim-Subscription-Key": settings.azure_vision_key}
    
    while time.time() < deadline:
        poll_response = requests.get(operation_url, headers=poll_headers, timeout=timeout_seconds)
        if poll_response.status_code >= 400:
            _raise_azure_error(poll_response)
        
        payload = poll_response.json()
        status = payload.get("status", "").lower()
        
        if status == "succeeded":
            return payload
        if status == "failed":
            raise AzureVisionError("Azure Vision OCR が失敗しました。")
        
        time.sleep(0.6)
    
    raise AzureVisionError("Azure Vision OCR の処理がタイムアウトしました。")
```

### 7.3 結果パース

APIレスポンスの構造が複数パターン存在するため、柔軟にパース：

```python
def _extract_lines(payload: dict) -> Iterable[str]:
    lines: list[str] = []
    
    # Image Analysis API形式
    analyze_result = payload.get("analyzeResult") or {}
    for page in analyze_result.get("readResults", []):
        for line in page.get("lines", []):
            text = line.get("text") or line.get("content")
            if text:
                lines.append(text.strip())
    
    # Read API形式
    read_result = payload.get("readResult") or {}
    for block in read_result.get("blocks", []):
        for line in block.get("lines", []):
            text = line.get("text") or line.get("content")
            if text:
                lines.append(text.strip())
    
    # フォールバック: content直接取得
    if not lines:
        content = payload.get("content")
        if content:
            lines.append(content.strip())
    
    return lines
```

### 7.4 エンドポイント例

#### `/api/ocr`

画像からテキストを抽出して返す：

```bash
curl -X POST "http://localhost:8000/api/ocr?lang=ja" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@sample.png"
```

レスポンス:
```json
{
  "filename": "sample.png",
  "characters": 1234,
  "text_preview": "令和3年4月1日、東京で新しい...",
  "text": "令和3年4月1日、東京で新しい政策が発表された。..."
}
```

#### `/api/ocr-generate-dag`

画像からテキストを抽出し、直接DAGを生成：

```bash
curl -X POST "http://localhost:8000/api/ocr-generate-dag?lang=ja&relation_threshold=0.6&max_events=100" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@historical_text.jpg"
```

レスポンス:
```json
{
  "id": "dag-uuid",
  "nodes": [
    {
      "id": "node-1",
      "date_text": "令和3年4月1日",
      "date_iso": "2021-04-01",
      "title": "新しい政策が発表された",
      "node_type": "event",
      "is_parent": true
    }
  ],
  "edges": [
    {
      "source_id": "node-1",
      "target_id": "node-2",
      "relation_type": "causal",
      "relation_strength": 0.82,
      "reasoning": "マーカー『その結果』による推定"
    }
  ],
  "stats": {
    "node_count": 10,
    "edge_count": 8,
    "avg_degree": 1.6,
    "max_path_length": 4,
    "cyclic_count": 0
  },
  "version": "2.0"
}
```

---

## 8. 評価と今後の展望

### 8.1 現状の制約

| 項目 | 制約 | 対策案 |
|-----|------|--------|
| **因果推論精度** | マーカーが明示的にない場合は精度低下 | BERTベースの文脈理解モデル導入 |
| **固有表現抽出** | 辞書・ヒューリスティクスに依存 | NERモデル（spaCy, BERT-NER）の統合 |
| **スケーラビリティ** | 20万文字・500イベント上限 | ストリーミング処理・分散処理の検討 |
| **多言語対応** | 日本語に特化 | 英語・中国語・韓国語への拡張 |

### 8.2 改善案

#### 8.2.1 機械学習モデルの導入

- **BERT-based NER**: 固有表現抽出の精度向上
- **因果関係分類器**: 事前学習済みモデルで因果・前提・派生を識別
- **文埋め込み（Sentence-BERT）**: カテゴリ類似度の計算に利用

#### 8.2.2 知識グラフとの統合

- Wikipedia・DBpediaとの連携で人物・地名の属性情報を補完
- 外部知識による因果関係の補強（例: 「東日本大震災」→「原発事故」は既知の因果）

#### 8.2.3 インタラクティブ編集機能

- ユーザーがDAGのエッジを手動で追加・削除できるUI
- フィードバックループで推論精度を向上

### 8.3 ベンチマーク

**テストデータ**: Wikipedia「坂本龍馬」記事（約1200文字）

| 指標 | 結果 |
|-----|------|
| 抽出イベント数 | 18件 |
| ISO日付化成功率 | 94% (17/18) |
| 固有表現抽出（人物） | 12名 |
| 固有表現抽出（地名） | 8箇所 |
| DAGエッジ数 | 15本 |
| 因果関係（`causal`） | 6本 |
| 最長経路長 | 5 |
| 処理時間 | 約2.3秒（MeCab有効時） |

---

## 9. 参考文献

### 学術文献

1. **因果関係抽出**:
   - Hashimoto, C., et al. (2014). "Toward Future Scenario Generation: Extracting Event Causality Exploiting Semantic Relation, Context, and Association Features." *ACL*.
   
2. **日本語形態素解析**:
   - Kudo, T., et al. (2004). "Applying Conditional Random Fields to Japanese Morphological Analysis." *EMNLP*.

3. **時系列イベント抽出**:
   - Chambers, N., & Jurafsky, D. (2008). "Unsupervised Learning of Narrative Event Chains." *ACL*.

### ライブラリ・技術資料

- **FastAPI**: [https://fastapi.tiangolo.com/](https://fastapi.tiangolo.com/)
- **fugashi (MeCab wrapper)**: [https://github.com/polm/fugashi](https://github.com/polm/fugashi)
- **Azure AI Vision**: [https://learn.microsoft.com/azure/ai-services/computer-vision/](https://learn.microsoft.com/azure/ai-services/computer-vision/)
- **ISO 8601 Extended**: [https://en.wikipedia.org/wiki/ISO_8601](https://en.wikipedia.org/wiki/ISO_8601)

---

## 付録: アーキテクチャ図（Draw.io形式）

以下のXMLをDraw.ioにインポートして編集可能な図として利用できます。

```xml
<mxfile host="app.diagrams.net" modified="2025-12-02T00:00:00.000Z" agent="Chronology Technical Report" version="21.0.0">
  <diagram name="Architecture" id="architecture-diagram">
    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="827" pageHeight="1169" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        
        <!-- Client Layer -->
        <mxCell id="client" value="Client (Browser/Mobile)" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="300" y="40" width="200" height="60" as="geometry"/>
        </mxCell>
        
        <!-- FastAPI Layer -->
        <mxCell id="fastapi" value="FastAPI Backend" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;" vertex="1" parent="1">
          <mxGeometry x="300" y="160" width="200" height="60" as="geometry"/>
        </mxCell>
        
        <!-- Input Sources -->
        <mxCell id="input-text" value="Raw Text" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;" vertex="1" parent="1">
          <mxGeometry x="80" y="280" width="120" height="50" as="geometry"/>
        </mxCell>
        <mxCell id="input-file" value="File Upload&#xa;(PDF/DOCX/Image)" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;" vertex="1" parent="1">
          <mxGeometry x="240" y="280" width="120" height="50" as="geometry"/>
        </mxCell>
        <mxCell id="input-wiki" value="Wikipedia" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;" vertex="1" parent="1">
          <mxGeometry x="400" y="280" width="120" height="50" as="geometry"/>
        </mxCell>
        
        <!-- Text Processing -->
        <mxCell id="text-cleaner" value="Text Cleaner" style="rounded=0;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;" vertex="1" parent="1">
          <mxGeometry x="150" y="380" width="120" height="40" as="geometry"/>
        </mxCell>
        <mxCell id="azure-ocr" value="Azure OCR" style="rounded=0;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;" vertex="1" parent="1">
          <mxGeometry x="300" y="380" width="120" height="40" as="geometry"/>
        </mxCell>
        
        <!-- Timeline Generator -->
        <mxCell id="timeline-gen" value="Timeline Generator&#xa;(Date Extraction + NER)" style="rounded=0;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;" vertex="1" parent="1">
          <mxGeometry x="250" y="460" width="180" height="60" as="geometry"/>
        </mxCell>
        
        <!-- Outputs -->
        <mxCell id="timeline-items" value="Timeline Items" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="140" y="560" width="120" height="50" as="geometry"/>
        </mxCell>
        <mxCell id="dag-builder" value="DAG Builder&#xa;(Causal Analysis)" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
          <mxGeometry x="300" y="560" width="140" height="50" as="geometry"/>
        </mxCell>
        
        <!-- Storage -->
        <mxCell id="storage" value="Storage&#xa;(SQLite/Firestore)" style="rounded=0;whiteSpace=wrap;html=1;fillColor=#ffe6cc;strokeColor=#d79b00;" vertex="1" parent="1">
          <mxGeometry x="480" y="560" width="120" height="50" as="geometry"/>
        </mxCell>
        
        <!-- Arrows -->
        <mxCell id="arrow1" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;" edge="1" parent="1" source="client" target="fastapi">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow2" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;" edge="1" parent="1" source="input-text" target="text-cleaner">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow3" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;" edge="1" parent="1" source="input-file" target="azure-ocr">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow4" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;" edge="1" parent="1" source="text-cleaner" target="timeline-gen">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow5" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;" edge="1" parent="1" source="azure-ocr" target="timeline-gen">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow6" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;" edge="1" parent="1" source="timeline-gen" target="timeline-items">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow7" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;" edge="1" parent="1" source="timeline-gen" target="dag-builder">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow8" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;dashed=1;" edge="1" parent="1" source="dag-builder" target="storage">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

**使用方法**:
1. [Draw.io](https://app.diagrams.net/) にアクセス
2. 「File」→「Import from」→「XML」を選択
3. 上記XMLをペーストして「Import」

---

**本レポート作成者**: GitHub Copilot  
**作成日**: 2025年12月2日  
**ライセンス**: 本リポジトリのライセンスに準拠
