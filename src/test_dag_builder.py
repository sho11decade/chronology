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
    assert dag.stats["max_path_length"] >= 1, "最長経路が計算されていない"
    assert dag.stats["cyclic_count"] >= 0


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


def test_prerequisite_relation_detection():
    text = (
        "2020年1月に基盤工事が完了した。"
        "これにより初めて2020年2月に新サービスが運用を開始した。"
    )
    dag = build_timeline_dag(text)
    assert any(e.relation_type == "prerequisite" for e in dag.edges), "前提条件エッジが検出されていない"


def test_is_parent_flag():
    dag = build_timeline_dag(_sample_text())
    parents = [n for n in dag.nodes if n.is_parent]
    assert parents, "親ノードが設定されていない"
    if len(dag.nodes) > 1:
        tail = dag.nodes[-1]
        assert not tail.is_parent, "終端ノードは親フラグが立たないはず"


def test_derived_relation_marker_detection():
    text = (
        "1868年1月3日、京都御所で王政復古の大号令が出された。"
        "1868年1月27日、これを契機に旧幕府軍は各地で敗退した。"
    )
    dag = build_timeline_dag(text)
    assert any(e.relation_type == "derived" for e in dag.edges), "派生関係が検出されていない"


def test_dag_handles_bce_events():
    text = (
        "紀元前660年、神武天皇が即位したとされる。"
        "その後、紀元前600年に各地で国家の萌芽が生まれた。"
    )
    dag = build_timeline_dag(text)
    assert dag.nodes
    assert any(node.date_iso and node.date_iso.startswith("-") for node in dag.nodes)
    assert dag.edges, "BCE イベント間のエッジが生成されていない"
