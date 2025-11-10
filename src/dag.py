from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Literal, Optional, Tuple, Set
from uuid import uuid4

try:
    # ローカル相対インポート（アプリ内実行）
    from .models import TimelineItem
    from .timeline_generator import generate_timeline
except ImportError:  # pragma: no cover - script 直実行フォールバック
    from models import TimelineItem
    from timeline_generator import generate_timeline

from pydantic import BaseModel, Field


# --- DAG モデル -------------------------------------------------------------


class TimelineNode(BaseModel):
    id: str
    date_text: str
    date_iso: Optional[str] = None
    title: str
    description: str
    people: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    category: str = "general"
    importance: float = 0.0
    confidence: float = 0.0

    # DAG 拡張
    node_type: Literal["event", "fact", "concept"] = "event"
    semantic_cluster: Optional[str] = None
    temporal_precision: int = 0  # 0: 日, 1: 月, 2: 年（粗さの目安）
    is_parent: bool = False


RelationType = Literal[
    "causal",
    "temporal",
    "prerequisite",
    "parallel",
    "derived",
    "dependency",
    "correlated",
]


class TimelineEdge(BaseModel):
    source_id: str
    target_id: str
    relation_type: RelationType = "temporal"
    relation_strength: float = Field(..., ge=0.0, le=1.0)
    time_gap_days: Optional[int] = None
    reasoning: str = ""
    evidence_sentences: List[str] = Field(default_factory=list)


class TimelineDAG(BaseModel):
    id: str
    title: str = ""
    text: str = ""
    nodes: List[TimelineNode]
    edges: List[TimelineEdge]

    stats: Dict[str, float] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    version: str = "2.0"


class GenerateDAGRequest(BaseModel):
    text: str = Field(..., max_length=200_000)
    include_relationships: bool = True
    relation_threshold: float = Field(0.5, ge=0.0, le=1.0)
    max_events: int = Field(500, ge=1, le=5000)


# --- ユーティリティ ---------------------------------------------------------


# マーカー辞書（要件定義の付録Aを簡略反映）
_MARKERS: Dict[str, Tuple[RelationType, float]] = {
    # 因果
    "そのため": ("causal", 0.95),
    "その結果": ("causal", 0.93),
    "これにより": ("causal", 0.92),
    "これによって": ("causal", 0.92),
    "結果として": ("causal", 0.89),
    # 時間
    "その後": ("temporal", 0.80),
    "翌日": ("temporal", 0.85),
    "翌月": ("temporal", 0.85),
    "翌年": ("temporal", 0.82),
    # 並行
    "同時に": ("parallel", 0.88),
    "一方": ("parallel", 0.85),
}


def _iso_to_date(iso: Optional[str]) -> Optional[date]:
    if not iso:
        return None
    try:
        y, m, d = (int(p) for p in iso.split("-"))
        return date(y, m, d)
    except Exception:
        return None


def _temporal_precision_from_iso(iso: Optional[str]) -> int:
    if not iso:
        return 2
    # yyyy-mm-dd を前提にし、常に日精度 0 とする（簡易版）
    return 0


def _time_gap_days(a: Optional[str], b: Optional[str]) -> Optional[int]:
    da, db = _iso_to_date(a), _iso_to_date(b)
    if da and db:
        return (db - da).days
    return None


def _has_marker(text: str, markers: Tuple[str, ...]) -> bool:
    return any(m in text for m in markers)


def _entity_overlap(a: TimelineItem, b: TimelineItem) -> int:
    return len(set(a.people) & set(b.people)) + len(set(a.locations) & set(b.locations))


def _detect_temporal_markers(prev_text: str, cur_text: str) -> Tuple[RelationType, float, Optional[str]]:
    """前後のテキストから最も強いマーカーを検出し、関係型とスコア、該当語を返す。"""
    best: Tuple[RelationType, float, Optional[str]] = ("temporal", 0.0, None)
    # 現在文面を優先的に検索
    for phrase, (rtype, score) in _MARKERS.items():
        if phrase in cur_text:
            if score > best[1]:
                best = (rtype, score, phrase)
    # 次に前文面も参照（並行など）
    for phrase, (rtype, score) in _MARKERS.items():
        if phrase in prev_text and score > best[1]:
            best = (rtype, score, phrase)
    return best


def _infer_relation_type(prev: TimelineItem, cur: TimelineItem) -> Tuple[RelationType, float, Optional[str]]:
    prev_text = (prev.description or "") + "\n" + (prev.title or "")
    cur_text = (cur.description or "") + "\n" + (cur.title or "")
    rtype, score, phrase = _detect_temporal_markers(prev_text, cur_text)
    return rtype, score, phrase


_CATEGORY_AFFINITY: Dict[Tuple[str, str], float] = {
    ("politics", "economy"): 0.65,
    ("economy", "politics"): 0.65,
    ("science", "health"): 0.75,
    ("health", "science"): 0.75,
    ("disaster", "health"): 0.60,
    ("health", "disaster"): 0.60,
    ("economy", "science"): 0.50,
    ("science", "economy"): 0.50,
    ("politics", "science"): 0.35,
    ("science", "politics"): 0.35,
}


def _semantic_similarity(prev: TimelineItem, cur: TimelineItem) -> float:
    if prev.category == cur.category:
        if prev.category == "general":
            return 0.2
        return 0.8
    return _CATEGORY_AFFINITY.get((prev.category, cur.category), 0.3)


def _relation_strength(prev: TimelineItem, cur: TimelineItem, marker_score: float) -> float:
    # 要件式: 0.5*wt + 0.3*sc + 0.2*tg
    wt = max(0.0, min(1.0, marker_score))
    sc = _semantic_similarity(prev, cur)
    gap = _time_gap_days(prev.date_iso, cur.date_iso)
    tg = math.exp(-abs(gap) / 365.0) if isinstance(gap, int) else 0.8
    score = 0.5 * wt + 0.3 * sc + 0.2 * tg
    return round(max(0.0, min(1.0, score)), 3)


def _compute_stats(nodes: List[TimelineNode], edges: List[TimelineEdge]) -> Dict[str, float]:
    if not nodes:
        return {"node_count": 0, "edge_count": 0, "avg_degree": 0.0, "max_path_length": 0, "cyclic_count": 0}
    deg = (2 * len(edges)) / max(1, len(nodes))
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "avg_degree": round(deg, 3),
        "max_path_length": 0,
        "cyclic_count": 0,
    }


# --- 公開API: DAG 構築 ------------------------------------------------------


def build_timeline_dag(
    text: str,
    *,
    relation_threshold: float = 0.5,
    max_events: int = 500,
) -> TimelineDAG:
    """本文から TimelineItem を生成し、隣接イベント間の有向エッジを付与して DAG を構築する。

    注意: MVP のため、因果推論はヒューリスティクス最小限、サイクルは時間順制約で不発生。
    """

    items: List[TimelineItem] = generate_timeline(text, max_events=max_events)
    # すでに generate_timeline は時系列ソート済み
    nodes: List[TimelineNode] = []
    for it in items:
        nodes.append(
            TimelineNode(
                id=it.id,
                date_text=it.date_text,
                date_iso=it.date_iso,
                title=it.title,
                description=it.description,
                people=it.people,
                locations=it.locations,
                category=it.category,
                importance=it.importance,
                confidence=it.confidence,
                node_type="event",
                temporal_precision=_temporal_precision_from_iso(it.date_iso),
                is_parent=False,
            )
        )

    window = 3  # 先読みウィンドウ（調整可能）
    edges: List[TimelineEdge] = []
    for i in range(len(items)):
        for j in range(i + 1, min(i + 1 + window, len(items))):
            prev, cur = items[i], items[j]
            # 時間順制約
            d1, d2 = _iso_to_date(prev.date_iso), _iso_to_date(cur.date_iso)
            if d1 and d2 and d1 > d2:
                continue
            rel_type, marker_score, phrase = _infer_relation_type(prev, cur)
            strength = _relation_strength(prev, cur, marker_score)
            if strength < relation_threshold:
                continue
            gap = _time_gap_days(prev.date_iso, cur.date_iso)
            reasoning = (
                f"マーカー『{phrase}』による推定" if (rel_type == "causal" and phrase) else "時間順と類似度による推定"
            )
            edges.append(
                TimelineEdge(
                    source_id=prev.id,
                    target_id=cur.id,
                    relation_type=rel_type,
                    relation_strength=strength,
                    time_gap_days=gap,
                    reasoning=reasoning,
                    evidence_sentences=[cur.title],
                )
            )

    # サイクル除去（弱いエッジから間引き）
    edges = detect_and_resolve_cycles(edges)
    # 軽量な推移的削減
    edges = reduce_transitive_edges(edges)

    dag = TimelineDAG(
        id=str(uuid4()),
        title="",
        text=text[:200_000],
        nodes=nodes,
        edges=edges,
        stats=_compute_stats(nodes, edges),
    )
    return dag


# --- トポロジカルソート / 経路探索（簡易版） -------------------------------


def topological_sort(nodes: List[TimelineNode], edges: List[TimelineEdge]) -> List[TimelineNode]:
    in_deg: Dict[str, int] = {n.id: 0 for n in nodes}
    adj: Dict[str, List[str]] = {n.id: [] for n in nodes}
    for e in edges:
        adj[e.source_id].append(e.target_id)
        in_deg[e.target_id] = in_deg.get(e.target_id, 0) + 1

    queue = [nid for nid, d in in_deg.items() if d == 0]
    ordered: List[str] = []
    while queue:
        nid = queue.pop(0)
        ordered.append(nid)
        for nxt in adj.get(nid, []):
            in_deg[nxt] -= 1
            if in_deg[nxt] == 0:
                queue.append(nxt)

    id_to_node = {n.id: n for n in nodes}
    return [id_to_node[i] for i in ordered if i in id_to_node]


def find_paths(
    start_node_id: str,
    end_node_id: str,
    edges: List[TimelineEdge],
    *,
    max_depth: int = 10,
) -> List[List[str]]:
    adj: Dict[str, List[str]] = {}
    for e in edges:
        adj.setdefault(e.source_id, []).append(e.target_id)

    results: List[List[str]] = []

    def dfs(cur: str, target: str, path: List[str], depth: int) -> None:
        if depth > max_depth:
            return
        if cur == target:
            results.append(path[:])
            return
        for nxt in adj.get(cur, []):
            if nxt in path:
                continue
            path.append(nxt)
            dfs(nxt, target, path, depth + 1)
            path.pop()

    dfs(start_node_id, end_node_id, [start_node_id], 0)
    return results


# --- サイクル検出と推移的エッジ削減 -----------------------------------------


def build_adjacency_list(edges: List[TimelineEdge]) -> Dict[str, List[str]]:
    adj: Dict[str, List[str]] = {}
    for e in edges:
        adj.setdefault(e.source_id, []).append(e.target_id)
    return adj


def _find_cycle(adj: Dict[str, List[str]]) -> Optional[List[str]]:
    visited: Set[str] = set()
    stack: Set[str] = set()
    parent: Dict[str, Optional[str]] = {}

    def dfs(u: str) -> Optional[List[str]]:
        visited.add(u)
        stack.add(u)
        for v in adj.get(u, []):
            if v not in visited:
                parent[v] = u
                res = dfs(v)
                if res:
                    return res
            elif v in stack:
                # サイクル復元
                cycle = [v]
                cur = u
                while cur != v and cur is not None:
                    cycle.append(cur)
                    cur = parent.get(cur)
                cycle.reverse()
                return cycle
        stack.remove(u)
        return None

    for node in list(adj.keys()):
        if node not in visited:
            parent[node] = None
            res = dfs(node)
            if res:
                return res
    return None


def detect_and_resolve_cycles(edges: List[TimelineEdge]) -> List[TimelineEdge]:
    adj = build_adjacency_list(edges)
    cycle = _find_cycle(adj)
    if not cycle:
        return edges
    # 1サイクルずつ最弱エッジを除去し、安定まで繰り返す
    edge_map: Dict[Tuple[str, str], TimelineEdge] = {(e.source_id, e.target_id): e for e in edges}
    while cycle:
        # サイクル上のエッジ候補
        candidates = []
        for i in range(len(cycle)):
            a = cycle[i]
            b = cycle[(i + 1) % len(cycle)]
            e = edge_map.get((a, b))
            if e:
                candidates.append(e)
        if not candidates:
            break
        weakest = min(candidates, key=lambda e: e.relation_strength)
        edge_map.pop((weakest.source_id, weakest.target_id), None)
        # 再評価
        adj = build_adjacency_list(list(edge_map.values()))
        cycle = _find_cycle(adj)
    return list(edge_map.values())


def _has_alternative_path(src: str, dst: str, adj: Dict[str, List[str]], *, exclude: Tuple[str, str]) -> bool:
    # 直接エッジ exclude を除いた到達可能性
    stack = [src]
    seen: Set[str] = set()
    while stack:
        u = stack.pop()
        if u in seen:
            continue
        seen.add(u)
        for v in adj.get(u, []):
            if (u, v) == exclude:
                continue
            if v == dst:
                return True
            stack.append(v)
    return False


def reduce_transitive_edges(edges: List[TimelineEdge]) -> List[TimelineEdge]:
    adj = build_adjacency_list(edges)
    keep: List[TimelineEdge] = []
    for e in edges:
        if _has_alternative_path(e.source_id, e.target_id, adj, exclude=(e.source_id, e.target_id)):
            # 冗長（A→B→C があり A→C もある）
            continue
        keep.append(e)
    return keep
