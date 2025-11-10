from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Literal, Optional, Tuple
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


_CAUSAL_MARKERS = (
    "そのため",
    "その結果",
    "これにより",
    "これによって",
    "結果として",
)
_TEMPORAL_MARKERS = (
    "その後",
    "翌日",
    "翌月",
    "翌年",
)


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


def _infer_relation_type(prev: TimelineItem, cur: TimelineItem) -> RelationType:
    desc = (cur.description or "") + "\n" + (cur.title or "")
    if _has_marker(desc, _CAUSAL_MARKERS):
        return "causal"
    return "temporal"


def _relation_strength(prev: TimelineItem, cur: TimelineItem) -> float:
    # 簡易スコア: マーカー, カテゴリ一致, エンティティ重複, 時間減衰
    desc = (cur.description or "") + "\n" + (cur.title or "")
    marker = 1.0 if _has_marker(desc, _CAUSAL_MARKERS) else (0.6 if _has_marker(desc, _TEMPORAL_MARKERS) else 0.0)
    same_cat = 1.0 if (prev.category == cur.category and prev.category != "general") else 0.0
    overlap = 1.0 if _entity_overlap(prev, cur) > 0 else 0.0
    gap = _time_gap_days(prev.date_iso, cur.date_iso)
    decay = math.exp(-abs(gap) / 365.0) if isinstance(gap, int) else 0.8

    score = 0.5 * marker + 0.2 * same_cat + 0.2 * overlap + 0.1 * decay
    return max(0.0, min(1.0, round(score, 3)))


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

    edges: List[TimelineEdge] = []
    for i in range(len(items) - 1):
        prev, cur = items[i], items[i + 1]
        # 時間順制約: 同一または後続のみ
        rel_type: RelationType = _infer_relation_type(prev, cur)
        strength = _relation_strength(prev, cur)
        if strength < relation_threshold:
            continue
        gap = _time_gap_days(prev.date_iso, cur.date_iso)
        reasoning = ""
        if rel_type == "causal":
            reasoning = "テンポラル・マーカーに基づく因果推定"
        else:
            reasoning = "時系列上の後続イベント"
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
