from __future__ import annotations

from datetime import datetime
from typing import List

from .dag import build_timeline_dag, find_paths, topological_sort


def _sample_text() -> str:
    return (
        "2020年1月に新製品が発表された。その結果、2020年2月に売上が急増した。さらに、2020年3月に増産体制が構築された。"
    )


def test_build_timeline_dag_basic():
    text = _sample_text()
    dag = build_timeline_dag(text)
    assert dag.nodes, "ノード生成に失敗"
    assert len(dag.nodes) >= 3, "想定よりノードが少ない"
    assert dag.edges, "エッジ生成に失敗"
    # 連続イベント間の少なくとも1本のエッジ
    assert any(e.relation_type in ("causal", "temporal") for e in dag.edges)
    assert dag.stats["node_count"] == len(dag.nodes)
    assert dag.stats["edge_count"] == len(dag.edges)


def test_topological_sort_order():
    text = _sample_text()
    dag = build_timeline_dag(text)
    ordered = topological_sort(dag.nodes, dag.edges)
    # generate_timeline が時系列順なので、topological_sort 結果も最初の日付が早いはず
    dates = [n.date_iso or "" for n in ordered]
    assert dates, "ソート結果が空"
    assert dates[0] == sorted(dates)[0], "最初のノードが最小日付でない"


def test_find_paths():
    text = _sample_text()
    dag = build_timeline_dag(text)
    if len(dag.nodes) < 2:
        return  # ノードが極端に少ない場合はスキップ
    if not dag.edges:
        return
    e = dag.edges[0]
    paths = find_paths(e.source_id, e.target_id, dag.edges, max_depth=5)
    assert paths, "経路検出に失敗"
    # 直接エッジがあるため、少なくとも [source, target] が存在する
    assert any(path == [e.source_id, e.target_id] for path in paths)
