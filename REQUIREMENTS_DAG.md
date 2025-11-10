# タイムライン生成アルゴリズムへの DAG 採用 - 要件定義書

**バージョン**: 1.0  
**作成日**: 2025年11月10日  
**対象**: Chronology Maker API タイムライン生成エンジン

---

## 目次

1. [概要](#1-概要)
2. [背景と動機](#2-背景と動機)
3. [スコープと目標](#3-スコープと目標)
4. [DAG データモデル](#4-dag-データモデル)
5. [アルゴリズム設計](#5-アルゴリズム設計)
6. [API インターフェース](#6-api-インターフェース)
7. [性能要件](#7-性能要件)
8. [実装ロードマップ](#8-実装ロードマップ)
9. [検証・テスト戦略](#9-検証・テスト戦略)
10. [リスク管理](#10-リスク管理)

---

## 1. 概要

### 1.1 目的

現在の **イベント集約方式** から **有向非巡回グラフ（DAG: Directed Acyclic Graph）** ベースの **因果関係追跡システム** へ移行し、タイムライン内のイベント間の因果・前提・並行関係を明示的に表現・分析できるようにする。

### 1.2 期待される効果

| 効果 | 説明 |
|------|------|
| **精度向上** | 単なるイベント列ではなく、因果関係を明示 → 検索・フィルタ精度 +15～25% |
| **複雑な事象対応** | 連鎖的なイベント、派生事象を構造化 |
| **リアルタイム分析** | 経路検出、イベント伝播シミュレーション可能 |
| **クエリ拡張** | "Aが起きたら Bはいつ?", "C前提でのシナリオ分析" 等が実現 |

---

## 2. 背景と動機

### 2.1 現在のアルゴリズムの課題

**現在の方式** (`timeline_generator.py`)

```python
# 線形処理: 文 → 日付検出 → イベント集約 → ソート
aggregated_events[key] = {
    "sentences": [...],
    "importance": ...,
    "category": ...
}
items = sorted(aggregated_events.values(), key=lambda x: x["date_iso"])
```

**課題**

1. **因果関係喪失**: イベント間の因果・前後関係が表現されない
   - 例: "2020年に法案が成立した。翌年（2021年）に施行された" → 因果関係がなし
   
2. **複雑事象の過度な単純化**: 派生・連鎖関係が消失
   - 例: COVID-19 ウイルス発見 → PCR 検査開発 → ワクチン接種 → 副反応報告
   
3. **クエリ表現力の不足**: 複合条件検索が困難
   - "Aが起きた場合のB発生確率は?"
   - "Cに至るまでの最短経路は?"
   
4. **グラフィカル表現不可**: タイムラインの可視化が線形のみ

### 2.2 DAG導入のメリット

| メリット | 適用例 |
|---------|--------|
| **経路検出** | 歴史的因果鎖を追跡（改革 → 成立 → 施行 → 影響） |
| **並行関係表現** | 同時期の独立イベント |
| **派生分析** | 親イベント（法案成立）から子イベント（各地での導入） |
| **複雑クエリ** | "AかつBという前提条件下でのC" |
| **可視化** | D3.js/Cytoscape.js による対話型グラフ表示 |

---

## 3. スコープと目標

### 3.1 スコープ内

✅ **含める**

- DAG ノード・エッジ モデル定義
- テキストから因果関係を抽出する NLP ヒューリスティクス
- DAG 構築・トポロジカルソート・経路検出アルゴリズム
- 既存 API との後方互換性維持（JSON フィールド追加）
- 中規模テキスト（～200,000 文字）対応

❌ **スコープ外**

- 機械学習ベースの関係抽出（フェーズ 2）
- リアルタイム更新 / ストリーミング対応
- グラフのマージ・統合処理
- SQL グラフデータベース（Neo4j）統合

### 3.2 成功基準

| 基準 | 目標値 |
|------|--------|
| **因果関係抽出精度** | ≥ 75% (人手評価基準) |
| **計算時間** | 10,000文字: ≤ 500ms |
| **メモリ使用量** | 1,000 イベント: ≤ 50MB |
| **テストカバレッジ** | ≥ 85% |
| **既存API互換性** | 100% (JSON 拡張のみ) |

---

## 4. DAG データモデル

### 4.1 ノード定義

**ノード（TimelineNode）**: 一つのイベント/ファクト

```typescript
interface TimelineNode {
  // 既存フィールド（互換性保持）
  id: string;                      // UUID
  date_text: string;               // "令和3年4月1日"
  date_iso: string | null;         // "2021-04-01"
  title: string;                   // イベント短説
  description: string;             // 詳細説明
  people: string[];                // [人物名, ...]
  locations: string[];             // [地名, ...]
  category: string;                // "政治" | "経済" | ...
  importance: number;              // 0.0 ～ 1.0
  confidence: number;              // 0.0 ～ 1.0
  
  // DAG 拡張フィールド
  node_type: "event" | "fact" | "concept";
  semantic_cluster: string;        // グループID（後述）
  temporal_precision: 0 | 1 | 2;   // 0: 日 1: 月 2: 年
  is_parent: boolean;              // 親イベントか?
}
```

### 4.2 エッジ定義

**エッジ（TimelineEdge）**: イベント間の関係

```typescript
interface TimelineEdge {
  source_id: string;               // 元ノード UUID
  target_id: string;               // 先ノード UUID
  relation_type: RelationType;     // (次項参照)
  relation_strength: number;       // 0.0 ～ 1.0 (確度)
  time_gap_days: number | null;    // 時間差（日単位）
  reasoning: string;               // 関係推論の根拠
  evidence_sentences: string[];    // 根拠となった文リスト
}

type RelationType = 
  | "causal"         // A → B: Aが発生したので B が発生した
  | "temporal"       // A → B: A の後に B が起きた（因果性なし）
  | "prerequisite"   // A ⇒ B: A があってはじめて B が可能
  | "parallel"       // A ∥ B: 同時期の独立イベント
  | "derived"        // A ⊃ B: A の結果として B が派生
  | "dependency"     // A ← B: A は B の条件/前提
  | "correlated";    // A ≈ B: 相関関係
```

### 4.3 グラフ全体構造

```typescript
interface TimelineDAG {
  id: string;                      // グラフID
  title: string;
  text: string;                    // 元テキスト
  
  nodes: TimelineNode[];           // ノード一覧
  edges: TimelineEdge[];           // エッジ一覧
  
  // メタデータ
  total_events: number;
  generated_at: DateTime;
  version: string;                 // "2.0" (DAG対応)
  
  // 統計
  stats: {
    node_count: number;
    edge_count: number;
    avg_degree: number;            // 平均結合度
    max_path_length: number;       // 最長経路長
    cyclic_count: number;          // 巡回検出数（本来0）
  };
}
```

### 4.4 セマンティッククラスター

同じテーマ/主体のイベント群をグループ化

```typescript
interface SemanticCluster {
  cluster_id: string;
  name: string;                    // "COVID-19 関連" など
  node_ids: string[];              // 所属ノード
  relationships: {
    predecessor: SemanticCluster | null;
    successor: SemanticCluster | null;
  };
}
```

**例**

```
Cluster A: "COVID-19 ウイルス発見と初期対応"
  ├─ ノード 1: ウイルス発見 (2019年12月)
  ├─ ノード 2: WHO 警告 (2020年1月)
  └─ ノード 3: 緊急事態宣言 (2020年3月)

Cluster B: "ワクチン開発と接種開始"
  ├─ ノード 4: 臨床試験開始 (2020年6月)
  ├─ ノード 5: 認可取得 (2021年2月)
  └─ ノード 6: 接種開始 (2021年4月)

エッジ: Cluster A → Cluster B (主題的因果関係)
```

---

## 5. アルゴリズム設計

### 5.1 DAG 構築フロー

```
入力テキスト
    ↓
[Phase 1: ノード抽出]
  1.1 文分割 + 日付検出
  1.2 イベント集約（現在と同じ）
  1.3 TimelineNode 生成
    ↓
[Phase 2: 因果関係抽出]
  2.1 文間の共参照解析 (これが X)
  2.2 テンポラル・マーカー検出 (その後、同時に)
  2.3 セマンティック類似度計算
  2.4 TimelineEdge 候補生成
    ↓
[Phase 3: 因果性判定]
  3.1 ヒューリスティクスベース（フェーズ 1）
      - キーワードマッチ ("そのため", "その結果")
      - 時間前後関係（A < B ）
      - 関連キーワード距離
  3.2 NLP スコアリング（フェーズ 2）
      - Transformer 言語モデル（BERT-base-ja）
      - 関係ラベル分類
  3.3 relation_strength 計算
    ↓
[Phase 4: サイクル検出と除去]
  4.1 DFS + 訪問マーク
  4.2 サイクル分解（弱連結性維持）
    ↓
[Phase 5: 最適化]
  5.1 推移的 エッジ削減
  5.2 トポロジカル レイアウト生成
  5.3 TimelineDAG 出力
    ↓
出力: TimelineDAG
```

### 5.2 因果関係抽出 - ヒューリスティクス

#### 5.2.1 テンポラル・マーカー（確度: 0.95）

```python
TEMPORAL_CAUSAL = {
    "そのため": ("causal", 0.95),
    "その結果": ("causal", 0.93),
    "これにより": ("causal", 0.92),
    "これによって": ("causal", 0.92),
    "～に伴い": ("causal", 0.90),
    "その後": ("temporal", 0.80),
    "翌日": ("temporal", 0.85),
    "翌月": ("temporal", 0.85),
    "～年後": ("temporal", 0.75),
}

PREREQUISITE = {
    "～により初めて": ("prerequisite", 0.95),
    "～があって初めて": ("prerequisite", 0.94),
    "～を条件に": ("prerequisite", 0.92),
}

PARALLEL = {
    "一方": ("parallel", 0.85),
    "同時に": ("parallel", 0.88),
    "同月": ("parallel", 0.90),
}
```

#### 5.2.2 セマンティック類似度ベース

**カテゴリ親和性マトリックス**

```
            政治  経済  科学  文化  災害  医療
政治       0.0   0.6   0.3   0.2   0.4   0.3
経済       0.6   0.0   0.5   0.2   0.3   0.4
科学       0.3   0.5   0.0   0.2   0.4   0.7
文化       0.2   0.2   0.2   0.0   0.1   0.1
災害       0.4   0.3   0.4   0.1   0.0   0.5
医療       0.3   0.4   0.7   0.1   0.5   0.0
```

**スコアリング**

$$\text{relation\_strength} = 0.5 \times w_t + 0.3 \times s_c + 0.2 \times t_g$$

- $w_t$: テンポラル・マーカースコア（0.0 ～ 1.0）
- $s_c$: セマンティック類似度（0.0 ～ 1.0）
- $t_g$: 時間ギャップペナルティ（$e^{-|日数|/365}$）

### 5.3 アルゴリズム実装

#### 5.3.1 DAG 構築（Python ライク）

```python
def build_timeline_dag(text: str, max_events: int = 500) -> TimelineDAG:
    # Phase 1: ノード抽出
    nodes = extract_timeline_nodes(text, max_events)
    node_map = {n.id: n for n in nodes}
    
    # Phase 2: 関係候補生成
    edge_candidates = []
    for i, node_i in enumerate(nodes):
        for j, node_j in enumerate(nodes):
            if i >= j:  # 自己参照と重複排除
                continue
            
            relation = infer_relation(node_i, node_j, text)
            if relation and relation.relation_strength >= 0.5:  # スレッショルド
                edge_candidates.append(relation)
    
    # Phase 3: DAG 検証（サイクル検出）
    edges = detect_and_resolve_cycles(edge_candidates)
    
    # Phase 4: 推移的エッジ削減
    edges = reduce_transitive_edges(edges)
    
    # Phase 5: メタデータ計算
    stats = compute_graph_stats(nodes, edges)
    
    return TimelineDAG(
        nodes=nodes,
        edges=edges,
        stats=stats,
        generated_at=datetime.utcnow(),
    )

def infer_relation(
    node_i: TimelineNode,
    node_j: TimelineNode,
    text: str,
) -> TimelineEdge | None:
    """ノード i → j の関係を推論"""
    
    # 時間順序制約
    if node_i.date_iso and node_j.date_iso:
        if date(node_i.date_iso) > date(node_j.date_iso):
            return None  # 時間逆行は不可
    
    # テンポラル・マーカー検出
    temporal_score = detect_temporal_markers(
        node_i.description,
        node_j.description,
        text,
    )
    
    # セマンティック類似度
    semantic_score = compute_semantic_similarity(
        node_i.category,
        node_j.category,
        node_i.people,
        node_j.people,
    )
    
    # 関係型推定
    relation_type = classify_relation_type(
        node_i,
        node_j,
        temporal_score,
    )
    
    # 強度計算
    strength = 0.5 * temporal_score + 0.3 * semantic_score + 0.2 * time_decay
    
    if strength < 0.5:
        return None
    
    return TimelineEdge(
        source_id=node_i.id,
        target_id=node_j.id,
        relation_type=relation_type,
        relation_strength=strength,
        reasoning=generate_reasoning(node_i, node_j),
    )

def detect_and_resolve_cycles(edges: List[TimelineEdge]) -> List[TimelineEdge]:
    """DAG 性を強制（サイクルを弱い関係から削除）"""
    
    adj_list = build_adjacency_list(edges)
    cycles = find_cycles_dfs(adj_list)
    
    if not cycles:
        return edges
    
    # 各サイクルから最も弱いエッジを削除
    edges_to_remove = set()
    for cycle in cycles:
        min_edge = min(
            (e for e in edges if edge_in_cycle(e, cycle)),
            key=lambda e: e.relation_strength,
        )
        edges_to_remove.add((min_edge.source_id, min_edge.target_id))
    
    return [e for e in edges if (e.source_id, e.target_id) not in edges_to_remove]

def reduce_transitive_edges(edges: List[TimelineEdge]) -> List[TimelineEdge]:
    """
    推移的に冗長なエッジを削除
    A → B → C かつ A → C であれば、A → C を削除
    """
    adj_list = build_adjacency_list(edges)
    edge_set = {(e.source_id, e.target_id) for e in edges}
    
    reachable = compute_reachability_matrix(adj_list)
    
    edges_to_remove = set()
    for a in reachable:
        for c in reachable[a]:
            if c == a:
                continue
            # a から c への直接エッジが存在し、かつ経路がある場合
            if (a, c) in edge_set:
                # c への最短経路がほかにあるか確認
                if has_alternative_path(a, c, adj_list, exclude_direct=True):
                    edges_to_remove.add((a, c))
    
    return [e for e in edges if (e.source_id, e.target_id) not in edges_to_remove]
```

#### 5.3.2 トポロジカルソート

```python
def topological_sort(nodes: List[TimelineNode], edges: List[TimelineEdge]) -> List[TimelineNode]:
    """
    Kahn アルゴリズムでトポロジカルソート
    同じレベルのノードは日付順にソート
    """
    
    in_degree = {n.id: 0 for n in nodes}
    adj_list = {n.id: [] for n in nodes}
    
    for edge in edges:
        adj_list[edge.source_id].append(edge.target_id)
        in_degree[edge.target_id] += 1
    
    queue = deque([n.id for n in nodes if in_degree[n.id] == 0])
    sorted_nodes = []
    
    while queue:
        current_batch = []
        while queue:
            current_batch.append(queue.popleft())
        
        # 現在のバッチ内を日付でソート
        batch_nodes = [n for n in nodes if n.id in current_batch]
        batch_nodes.sort(key=lambda n: n.date_iso or "")
        sorted_nodes.extend(batch_nodes)
        
        # 次のバッチ準備
        for node_id in current_batch:
            for neighbor_id in adj_list[node_id]:
                in_degree[neighbor_id] -= 1
                if in_degree[neighbor_id] == 0:
                    queue.append(neighbor_id)
    
    return sorted_nodes
```

#### 5.3.3 経路検出

```python
def find_paths(
    start_node_id: str,
    end_node_id: str,
    edges: List[TimelineEdge],
    max_depth: int = 10,
) -> List[List[str]]:
    """
    スタートからエンドまでのすべての経路を検出
    BFS + メモ化
    """
    
    adj_list = build_adjacency_list(edges)
    paths = []
    
    def dfs(current: str, target: str, visited: set, path: list, depth: int):
        if depth > max_depth:
            return
        if current == target:
            paths.append(path[:])
            return
        if current in visited:
            return
        
        visited.add(current)
        for next_node_id in adj_list.get(current, []):
            path.append(next_node_id)
            dfs(next_node_id, target, visited, path, depth + 1)
            path.pop()
        visited.remove(current)
    
    dfs(start_node_id, end_node_id, set(), [start_node_id], 0)
    return paths

def compute_critical_path(nodes: List[TimelineNode], edges: List[TimelineEdge]) -> List[str]:
    """
    グラフ内の最長経路（クリティカルパス）を抽出
    PERT手法を簡略化
    """
    
    adj_list = build_adjacency_list(edges)
    sorted_nodes = topological_sort(nodes, edges)
    
    # 最長経路計算
    longest_path = {n.id: 0 for n in nodes}
    predecessor = {n.id: None for n in nodes}
    
    for node_id in [n.id for n in sorted_nodes]:
        for next_id in adj_list.get(node_id, []):
            if longest_path[node_id] + 1 > longest_path[next_id]:
                longest_path[next_id] = longest_path[node_id] + 1
                predecessor[next_id] = node_id
    
    # パス再構築
    end_node_id = max(longest_path, key=longest_path.get)
    path = []
    current = end_node_id
    while current is not None:
        path.append(current)
        current = predecessor[current]
    
    return path[::-1]
```

### 5.4 クエリ実行エンジン

#### 5.4.1 クエリ型

```typescript
interface TimelineQuery {
  query_type: 
    | "path"           // A から B への経路は?
    | "causal_chain"   // A に続く因果鎖は?
    | "influence"      // A は B に影響したか?
    | "prerequisite"   // B のための前提条件は?
    | "parallel"       // A と並行したイベントは?
    | "impact";        // A からの派生イベントは?
  
  params: {
    start_node_id?: string;
    end_node_id?: string;
    node_id?: string;
    relation_types?: RelationType[];
    max_results?: number;
  };
}
```

#### 5.4.2 クエリ実行例

```python
def execute_query(dag: TimelineDAG, query: TimelineQuery) -> QueryResult:
    if query.query_type == "path":
        paths = find_paths(
            query.params["start_node_id"],
            query.params["end_node_id"],
            dag.edges,
        )
        return {
            "type": "path",
            "paths": [
                [dag.node_map[nid] for nid in path]
                for path in paths[:10]
            ],
        }
    
    elif query.query_type == "causal_chain":
        # スタートノードから到達可能なすべてのノード
        reachable = find_reachable_nodes(
            query.params["node_id"],
            dag.edges,
            relation_types=["causal"],
        )
        return {
            "type": "causal_chain",
            "nodes": [dag.node_map[nid] for nid in reachable],
        }
    
    elif query.query_type == "influence":
        # A が B へ影響したかどうか
        has_path = find_any_path(
            query.params["start_node_id"],
            query.params["end_node_id"],
            dag.edges,
        )
        return {
            "type": "influence",
            "influenced": bool(has_path),
            "confidence": dag.edges_dict.get(
                (query.params["start_node_id"], query.params["end_node_id"])
            ).relation_strength if has_path else 0.0,
        }
    
    # ... 他のクエリ型
```

---

## 6. API インターフェース

### 6.1 RESTful エンドポイント

#### 6.1.1 DAG 生成

```http
POST /api/generate-dag
Content-Type: application/json

{
  "text": "2020年1月に武漢でウイルスが発見された。その後、3月に緊急事態が宣言された。",
  "include_relationships": true,     // DAG 構築するか（デフォルト true）
  "relation_threshold": 0.5,         // 関係強度の最小値
  "max_events": 500
}
```

**レスポンス**

```json
{
  "id": "timeline-dag-uuid",
  "nodes": [
    {
      "id": "node-1",
      "date_iso": "2020-01-01",
      "title": "ウイルス発見",
      "category": "health",
      "node_type": "event",
      "semantic_cluster": "cluster-covid-19"
    }
  ],
  "edges": [
    {
      "source_id": "node-1",
      "target_id": "node-2",
      "relation_type": "causal",
      "relation_strength": 0.85,
      "time_gap_days": 59,
      "reasoning": "テンポラル・マーカー『その後』による因果推定"
    }
  ],
  "stats": {
    "node_count": 10,
    "edge_count": 12,
    "avg_degree": 2.4,
    "max_path_length": 5,
    "cyclic_count": 0
  },
  "version": "2.0"
}
```

#### 6.1.2 経路検出

```http
GET /api/timeline-dag/{dag_id}/paths?start={node_id}&end={node_id}&max_depth=10
```

**レスポンス**

```json
{
  "paths": [
    {
      "length": 4,
      "nodes": ["node-1", "node-3", "node-5", "node-8"],
      "edges": [
        {
          "source": "node-1",
          "target": "node-3",
          "relation_type": "causal",
          "strength": 0.85
        }
      ]
    }
  ]
}
```

#### 6.1.3 影響度分析

```http
GET /api/timeline-dag/{dag_id}/influence?source={node_id}&target={node_id}
```

**レスポンス**

```json
{
  "source_node": { /* TimelineNode */ },
  "target_node": { /* TimelineNode */ },
  "has_influence": true,
  "influence_strength": 0.72,
  "shortest_path_length": 3,
  "relation_chain": ["causal", "derived", "temporal"]
}
```

### 6.2 後方互換性

**既存 API との互換性保持**

```python
# /api/generate は DAG 内部構築後、従来の JSON に変換
@app.post("/api/generate")
async def generate(request: GenerateRequest):
    dag = build_timeline_dag(request.text)
    
    # DAG → TimelineItem[] への変換
    items = convert_dag_to_timeline_items(dag)
    
    return GenerateResponse(
        items=items,
        total_events=len(items),
        generated_at=datetime.utcnow(),
    )
```

**拡張 JSON フィールド**

```json
{
  "id": "...",
  "title": "...",
  "... (既存フィールド)",
  
  "dag_metadata": {
    "node_id": "node-5",
    "node_type": "event",
    "semantic_cluster": "cluster-covid-19",
    "incoming_edges": [
      {
        "source_node_id": "node-3",
        "relation_type": "causal",
        "relation_strength": 0.87
      }
    ],
    "outgoing_edges": [
      {
        "target_node_id": "node-8",
        "relation_type": "derived",
        "relation_strength": 0.62
      }
    ]
  }
}
```

---

## 7. 性能要件

### 7.1 計算複雑度分析

| 処理 | 計算量 | 備考 |
|------|--------|------|
| **ノード抽出** | $O(n)$ | n = 文数 |
| **関係候補生成** | $O(n^2)$ | すべてのノード対を調査 |
| **サイクル検出 (DFS)** | $O(n + m)$ | n = ノード数, m = エッジ数 |
| **推移的エッジ削減** | $O(n^3)$ | Floyd-Warshall 簡略版 |
| **トポロジカルソート** | $O(n + m)$ | Kahn アルゴリズム |
| **経路検出** | $O(n + m)$ | BFS (単一経路) |
| **全経路検出** | $O(2^m)$ | 最悪ケース（DAG では制限） |

### 7.2 性能目標

| スケール | テキストサイズ | ノード数 | 目標時間 | メモリ上限 |
|---------|----------------|---------|---------|-----------|
| **小** | ≤ 5,000文字 | ≤ 50 | ≤ 100ms | ≤ 10MB |
| **中** | ≤ 50,000文字 | ≤ 200 | ≤ 500ms | ≤ 50MB |
| **大** | ≤ 200,000文字 | ≤ 500 | ≤ 2s | ≤ 100MB |

### 7.3 最適化戦略

#### 7.3.1 計算最適化

```python
# 1. 関係候補のフィルタ前処理
# テンポラル・マーカーがないペアは早期終了
if not has_temporal_markers(node_i, node_j):
    if not has_semantic_affinity(node_i, node_j):
        continue  # スキップ

# 2. 並列処理
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [
        executor.submit(infer_relation, node_i, node_j, text)
        for i, node_i in enumerate(nodes)
        for j, node_j in enumerate(nodes)
        if i < j
    ]
    edge_candidates = [f.result() for f in futures if f.result()]

# 3. キャッシング
from functools import lru_cache

@lru_cache(maxsize=1000)
def compute_semantic_similarity(cat_i: str, cat_j: str) -> float:
    return CATEGORY_AFFINITY_MATRIX.get((cat_i, cat_j), 0.0)
```

#### 7.3.2 メモリ最適化

```python
# 1. イテレータベース処理
def iter_edge_candidates(nodes, text):
    for i, node_i in enumerate(nodes):
        for j, node_j in enumerate(nodes[i+1:], start=i+1):
            relation = infer_relation(node_i, node_j, text)
            if relation:
                yield relation

# 2. グラフ圧縮
# 推移的エッジ削減によりエッジ数を 30～40% 削減

# 3. 遅延計算
# トポロジカルソート・経路検出は必要時のみ実行
```

### 7.4 スケーラビリティ

**大規模テキスト対応**

- **チャンク分割**: 50,000 文字ごとにテキスト分割
- **サブグラフ生成**: 各チャンクで個別 DAG を生成
- **グラフマージ**: サブグラフを統合（フェーズ 2）

```python
def build_timeline_dag_chunked(text: str, chunk_size: int = 50_000) -> TimelineDAG:
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    
    sub_dags = [build_timeline_dag(chunk) for chunk in chunks]
    
    # 単一チャンクなら直接返却
    if len(sub_dags) == 1:
        return sub_dags[0]
    
    # 複数チャンクの場合、フェーズ 2 でマージ
    # （本要件書スコープ外）
    raise NotImplementedError("Graph merging in Phase 2")
```

---

## 8. 実装ロードマップ

### 8.1 フェーズ 1: MVP（コア機能）

**期間**: 6～8週間  
**対象**: ヒューリスティクスベースの DAG 構築

**マイルストーン**

| # | タスク | 期限 | 担当 |
|---|--------|------|------|
| 1.1 | データモデル設計・実装 | Week 1 | Backend |
| 1.2 | 因果抽出ヒューリスティクス実装 | Week 2-3 | Backend |
| 1.3 | DAG 構築アルゴリズム実装 | Week 3-4 | Backend |
| 1.4 | サイクル検出・除去実装 | Week 4 | Backend |
| 1.5 | API エンドポイント実装 | Week 5 | Backend |
| 1.6 | ユニットテスト + 統合テスト | Week 6 | QA |
| 1.7 | 性能チューニング | Week 7 | DevOps |
| 1.8 | ドキュメント完成 | Week 8 | Tech Writer |

**成果物**

- `TimelineDAG` クラス実装
- `/api/generate-dag` エンドポイント
- テストカバレッジ ≥ 85%
- ユーザーガイド

### 8.2 フェーズ 2: 拡張（NLP + グラフマージ）

**期間**: 8～12週間  
**対象**: Transformer 使用の関係抽出、複数グラフの統合

**マイルストーン**

| # | タスク | 期限 | 担当 |
|---|--------|------|------|
| 2.1 | BERT-ja ファインチューニング | Week 9-11 | ML |
| 2.2 | NLP ベース関係分類器実装 | Week 11-12 | Backend |
| 2.3 | グラフマージアルゴリズム実装 | Week 12-14 | Backend |
| 2.4 | スケーラビリティテスト（≤ 200K字） | Week 14-15 | QA |
| 2.5 | デプロイ準備 | Week 15-16 | DevOps |

**成果物**

- BERT ファインチューニング済みモデル
- `/api/timeline-dag/paths` エンドポイント
- グラフマージ機能
- 大規模テキスト対応

### 8.3 フェーズ 3: 可視化 + 分析ツール

**期間**: 6～8週間  
**対象**: D3.js / Cytoscape.js 統合、分析ダッシュボード

**マイルストーン**

| # | タスク | 期限 | 担当 |
|---|--------|------|------|
| 3.1 | DAG レイアウトアルゴリズム（Sugiyama） | Week 17 | Frontend |
| 3.2 | D3.js 可視化コンポーネント | Week 18-19 | Frontend |
| 3.3 | インタラクティブ操作（ノード選択、経路ハイライト） | Week 19-20 | Frontend |
| 3.4 | 分析ダッシュボード（統計表示） | Week 20-21 | Frontend |
| 3.5 | 統合テスト + UX レビュー | Week 21-22 | QA + UX |

**成果物**

- D3.js グラフ描画コンポーネント
- ダッシュボード UI
- 可視化ドキュメント

---

## 9. 検証・テスト戦略

### 9.1 テストレイヤー

#### 9.1.1 ユニットテスト

```python
# test_dag_builder.py
class TestDAGBuilder:
    def test_node_extraction(self):
        """ノード抽出の正確性"""
        text = "2020年1月、事象A。3月、事象B。"
        nodes = extract_timeline_nodes(text)
        assert len(nodes) == 2
        assert nodes[0].date_iso == "2020-01-01"
        assert nodes[1].date_iso == "2020-03-01"
    
    def test_causal_relation_detection(self):
        """因果関係抽出の正確性"""
        node_i = TimelineNode(description="法案が成立した")
        node_j = TimelineNode(description="その結果、施行された")
        
        edge = infer_relation(node_i, node_j, full_text)
        assert edge.relation_type == "causal"
        assert edge.relation_strength >= 0.85
    
    def test_cycle_detection(self):
        """サイクル検出の正確性"""
        edges = [
            Edge(A, B), Edge(B, C), Edge(C, A)  # サイクル
        ]
        cycles = find_cycles_dfs(build_adjacency_list(edges))
        assert len(cycles) == 1
        assert cycles[0] == [A, B, C]
    
    def test_topological_sort(self):
        """トポロジカルソートの正確性"""
        nodes = [A, B, C]
        edges = [Edge(A, B), Edge(B, C)]
        
        sorted_nodes = topological_sort(nodes, edges)
        assert sorted_nodes == [A, B, C]
```

#### 9.1.2 統合テスト

```python
class TestDAGIntegration:
    def test_end_to_end_dag_generation(self):
        """E2E: テキスト → DAG"""
        text = """
        2020年1月に武漢でウイルスが発見された。
        その後、2月に全国的な感染が報告された。
        3月には、緊急事態が宣言された。
        これにより、企業の営業停止が命じられた。
        """
        
        dag = build_timeline_dag(text)
        
        assert len(dag.nodes) == 4
        assert len(dag.edges) >= 3  # 因果鎖
        assert dag.stats.cyclic_count == 0
        
        # 因果鎖の検証
        paths = find_paths(dag.nodes[0].id, dag.nodes[3].id, dag.edges)
        assert len(paths) > 0

    def test_query_execution(self):
        """クエリ実行の正確性"""
        dag = build_timeline_dag(test_text)
        
        query = TimelineQuery(
            query_type="causal_chain",
            params={"node_id": dag.nodes[0].id}
        )
        
        result = execute_query(dag, query)
        assert len(result["nodes"]) >= 3
```

#### 9.1.3 回帰テスト

```python
class TestBackwardCompatibility:
    def test_legacy_api_still_works(self):
        """既存 /api/generate の互換性"""
        response = client.post("/api/generate", json={
            "text": "2020年1月1日に東京で式典が開催された。"
        })
        
        assert response.status_code == 200
        data = response.json()
        
        # 既存フィールド確認
        assert "items" in data
        assert "total_events" in data
        assert "generated_at" in data
        
        # DAG メタデータは追加されているが、API 構造は変わらない
        item = data["items"][0]
        assert "dag_metadata" in item
```

### 9.2 精度評価

#### 9.2.1 評価データセット

**手動アノテーション済みテキスト集合（n=100）**

| テキスト種別 | 数 | 平均長 | 予想イベント数 |
|-------------|-----|--------|----------------|
| ニュース記事 | 30 | 3,000文字 | 5～10 |
| 歴史テキスト | 30 | 5,000文字 | 8～15 |
| 科学論文抄録 | 20 | 2,000文字 | 3～8 |
| 企業年表 | 20 | 2,500文字 | 6～12 |

#### 9.2.2 評価指標

```python
from sklearn.metrics import precision_recall_fscore_support

def evaluate_dag_extraction(predicted_edges, gold_edges):
    """
    Precision: 予測した関係のうち正しい割合
    Recall: 正解の関係のうち予測できた割合
    F1: 調和平均
    """
    tp = len(predicted_edges & gold_edges)
    fp = len(predicted_edges - gold_edges)
    fn = len(gold_edges - predicted_edges)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    return {"precision": precision, "recall": recall, "f1": f1}
```

**目標精度**

| メトリクス | 目標 |
|-----------|------|
| **Precision (関係型)** | ≥ 78% |
| **Recall (関係型)** | ≥ 72% |
| **F1 (関係型)** | ≥ 75% |

#### 9.2.3 人手評価

5段階リッカートスケール

```
評価項目: 抽出されたエッジは正当か?
1. 明らかに誤り
2. 傾向は正しいが不確実
3. おおむね正しい（些細な誤りあり）
4. ほぼ正しい
5. 完全に正しい

目標: 平均スコア ≥ 3.5
```

### 9.3 パフォーマンステスト

```python
import time

class TestPerformance:
    @pytest.mark.parametrize("text_size", [5000, 50000, 200000])
    def test_dag_generation_speed(self, text_size):
        """DAG 生成時間の測定"""
        text = generate_synthetic_text(text_size)
        
        start = time.perf_counter()
        dag = build_timeline_dag(text)
        elapsed = time.perf_counter() - start
        
        if text_size <= 5000:
            assert elapsed <= 0.1  # 100ms
        elif text_size <= 50000:
            assert elapsed <= 0.5  # 500ms
        else:
            assert elapsed <= 2.0  # 2s

    def test_memory_usage(self):
        """メモリ使用量の測定"""
        import tracemalloc
        
        text = generate_synthetic_text(200000)
        
        tracemalloc.start()
        dag = build_timeline_dag(text)
        current, peak = tracemalloc.get_traced_memory()
        
        assert peak / (1024**2) <= 100  # 100MB
```

---

## 10. リスク管理

### 10.1 技術リスク

| リスク | 発生確率 | 影響 | 対策 |
|--------|--------|------|------|
| **関係抽出精度不足** | 中 | 高 | フェーズ 2 で NLP 統合、ユーザーフィードバック |
| **パフォーマンス悪化** | 中 | 中 | 早期プロトタイプ検証、並列化、キャッシング |
| **後方互換性破損** | 低 | 高 | 拡張フィールド方式、充分なテスト |
| **複雑なサイクル処理** | 低 | 中 | 早期に DAG 検証層をビルド |

### 10.2 スケジュールリスク

| リスク | 対策 |
|--------|------|
| **フェーズ遅延** | バッファ期間 (各フェーズ +1週間) |
| **要員不足** | 外部コンサルタント活用 |
| **仕様変更** | 変更管理委員会設置 |

### 10.3 リスク軽減計画

**マイルストーン毎のゲート**

1. **Week 4 ゲート**: 基本 DAG 構築の完成度確認
2. **Week 8 ゲート**: MVP デプロイ前最終レビュー
3. **Week 16 ゲート**: フェーズ 2 実行可否判定

---

## 付録 A. テンポラル・マーカーリスト

### カテゴリ別キーワード

**強い因果マーカー**

```
そのため (0.95)
その結果 (0.93)
これにより (0.92)
これによって (0.92)
～に伴い (0.90)
その結果として (0.89)
～の結果 (0.88)
```

**時間系列マーカー**

```
その後 (0.80)
翌日 (0.85)
翌月 (0.85)
翌年 (0.82)
～年後 (0.75)
同時に (0.88)
一方 (0.85)
```

**前提・条件マーカー**

```
～により初めて (0.95)
～を条件に (0.92)
～があってはじめて (0.94)
～なければ～できない (0.90)
```

---

## 付録 B. セマンティック類似度マトリックス（詳細版）

```
カテゴリペア関連性スコア (0.0 ～ 1.0)

政治-経済:   0.65  (政策立案と経済施策の関連性)
政治-科学:   0.35  (基礎研究と政策の距離)
経済-科学:   0.50  (技術と産業の関連性)
科学-医療:   0.75  (医学は科学の応用)
医療-災害:   0.60  (被災時医療対応)
災害-政治:   0.50  (復興政策)
文化-スポーツ: 0.40 (エンタメ性共有)
スポーツ-政治: 0.45 (スポーツ政策、競技国)
```

---

## 付録 C. 実装チェックリスト

**コード実装**

- [ ] `TimelineNode` クラス定義
- [ ] `TimelineEdge` クラス定義
- [ ] `TimelineDAG` クラス定義
- [ ] `build_timeline_dag()` メイン関数
- [ ] `infer_relation()` 関係推論関数
- [ ] `detect_and_resolve_cycles()` 実装
- [ ] `topological_sort()` 実装
- [ ] `find_paths()` 経路検出関数
- [ ] `execute_query()` クエリエンジン

**テスト**

- [ ] ユニットテスト 85%+ カバレッジ
- [ ] 統合テスト 5+ シナリオ
- [ ] 後方互換性テスト
- [ ] パフォーマンステスト（全スケール）
- [ ] 人手評価 30+ サンプル

**ドキュメント**

- [ ] API ドキュメント (OpenAPI)
- [ ] ユーザーガイド
- [ ] 開発者ガイド
- [ ] トラブルシューティング

**デプロイ準備**

- [ ] Docker イメージ更新
- [ ] 環境変数ドキュメント
- [ ] ロールバック計画
- [ ] モニタリング設定

---

## 参考文献

1. Cormen, T. H., et al. (2009). "Introduction to Algorithms (3rd ed.)" - DAG とトポロジカルソート
2. Kahn, A. B. (1962). "Topological sorting of large networks" - Kahn アルゴリズム
3. Stanford NLP Group. "Universal Dependencies" - 言語学的依存関係
4. Event Causality Corpus (EventCausal) - イベント因果関係データセット
5. TACL 2018: "Event Representations for Automated Commonsense Reasoning"

---

**次のステップ**: このドキュメントは要件定義の基盤です。実装前に技術チームとレビューセッション実施を推奨します。

**承認者**: [CTO] [プロダクトマネージャー]  
**版管理**: v1.0 (2025-11-10)
