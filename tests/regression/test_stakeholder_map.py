"""v8.0.0 — 르포 stakeholder_map 차트 타입 회귀.

가드 무결성 + production wiring (KNOWN_CHART_TYPES / _TYPE_TO_GUARD / registry).
force/hairball 금지(CHART-AP-36)는 렌더러 속성 — 가드는 데이터 무결성만 검증.
"""

from __future__ import annotations

import pytest

from src.visual.schemas import guard_for_type, StakeholderMapGuard
from src.visual.usage_log import KNOWN_CHART_TYPES


def _valid() -> dict:
    return {
        "nodes": [
            {"id": "gov", "label": "국방부", "col": "left", "flag": "UA"},
            {"id": "uav", "label": "드론 전력", "col": "center"},
            {"id": "west", "label": "서방 후원", "col": "right", "flag": "US"},
        ],
        "edges": [
            {"source": "gov", "target": "uav", "type": "동맹", "label": "예산"},
            {"source": "west", "target": "uav", "type": "동맹", "label": "자금"},
        ],
    }


def test_registered_in_known_types() -> None:
    assert "stakeholder_map" in KNOWN_CHART_TYPES


def test_guard_resolves() -> None:
    assert guard_for_type("stakeholder_map") is StakeholderMapGuard


def test_valid_passes() -> None:
    g = StakeholderMapGuard(**_valid())
    assert len(g.nodes) == 3 and len(g.edges) == 2


def test_links_alias_accepted() -> None:
    d = {"nodes": [{"id": "a"}, {"id": "b"}], "links": [{"source": "a", "target": "b"}]}
    assert StakeholderMapGuard(**d) is not None


def test_too_few_nodes_rejected() -> None:
    with pytest.raises(Exception):
        StakeholderMapGuard(nodes=[{"id": "a"}])


def test_too_many_nodes_rejected() -> None:
    with pytest.raises(Exception):
        StakeholderMapGuard(nodes=[{"id": f"n{i}"} for i in range(13)])


def test_duplicate_id_rejected() -> None:
    with pytest.raises(Exception):
        StakeholderMapGuard(nodes=[{"id": "a"}, {"id": "a"}])


def test_dangling_edge_rejected() -> None:
    bad = _valid()
    bad["edges"].append({"source": "gov", "target": "ghost"})
    with pytest.raises(Exception):
        StakeholderMapGuard(**bad)


def test_registry_marks_guarded() -> None:
    from src.visual.capability_registry import list_guarded_types
    assert "stakeholder_map" in list_guarded_types()


def test_charts_js_registers_renderer() -> None:
    """charts.js RENDERERS 에 stakeholder_map 이 등록돼 있어야 (production wiring)."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2]
          / "src" / "templates" / "static" / "charts.js").read_text(encoding="utf-8")
    assert "stakeholder_map: drawStakeholderMap" in js
    assert "function drawStakeholderMap" in js


def test_charts_js_label_deconfliction_and_legend() -> None:
    """CHART-AP-40 — 엣지 라벨이 카드/다른 라벨과 겹치지 않게 밀어내는
    de-confliction 패스 + 선 스타일 범례가 drawStakeholderMap 에 배선돼 있어야."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2]
          / "src" / "templates" / "static" / "charts.js").read_text(encoding="utf-8")
    # 카드+기존 라벨 장애물 회피 (de-confliction)
    assert "labelObstacles" in js
    assert "placedLabels" in js
    assert "rectsHit" in js
    # 멀리 밀린 라벨의 연결선 + CHART-AP-40 마커
    assert "CHART-AP-40" in js
    # 선 스타일 범례
    assert "drawSmLegend" in js


def test_charts_js_edge_lane_router() -> None:
    """CHART-AP-41 — 교차 칼럼 엣지의 세로 구간을 칼럼 사이 gap 레인으로
    분배하는 라우터가 drawStakeholderMap 에 배선돼 있어야."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2]
          / "src" / "templates" / "static" / "charts.js").read_text(encoding="utf-8")
    assert "CHART-AP-41" in js
    assert "bendX" in js
    assert "smRouteLane" in js
    assert "GAP_BOUNDS" in js


def test_charts_js_node_assets() -> None:
    """CHART-AP-42 — 노드 자산: ISO 전 국가 국기(flagcdn + 인라인 KR 포함
    fallback) + 조직 로고(favicon) + 인물 흑백 사진(sm-gray) 슬롯, 원격 자산은
    프리로드 성공 시에만 오버레이."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2]
          / "src" / "templates" / "static" / "charts.js").read_text(encoding="utf-8")
    assert "CHART-AP-42" in js
    assert "sm-flag-KR" in js            # 인라인 태극기 (실발행 KR 강등 회귀)
    assert "flagcdn.com" in js           # ISO 전 국가 국기 CDN
    assert "logo.clearbit.com" in js     # 로고 1차 소스 (브랜드 로고, 미등록 404)
    assert "s2/favicons" in js           # 로고 2차 소스 (favicon)
    assert "minPx" in js                 # google 기본 지구본(16px) 거부 (v8.2.19)
    assert "naturalWidth" in js
    assert "sm-gray" in js               # 인물 사진 흑백 필터
    assert "smImgOverlay" in js          # 프리로드 성공 시에만 오버레이 (fallback 보존)
    assert "data-sm-base" in js          # base(국기/실루엣/이니셜) 태깅


def test_charts_js_obstacle_aware_routing() -> None:
    """CHART-AP-43 — 엣지가 카드 뒤를 관통하지 않는 장애물 인지형 직교 라우팅
    (교차 엣지 수평 코리더 + 같은 칼럼 skip 바깥 레인) + 라벨의 타 엣지
    세그먼트 회피."""
    from pathlib import Path
    js = (Path(__file__).resolve().parents[2]
          / "src" / "templates" / "static" / "charts.js").read_text(encoding="utf-8")
    assert "CHART-AP-43" in js
    assert "CHANNELS" in js              # 세로 레인 채널 (outL/gapA/gapB/outR)
    assert "smWaypoints" in js           # waypoint 라우트 골격
    assert "segHit" in js                # 라벨이 타 엣지 선/교차점 위 금지
    assert "edgeSegs" in js


def test_node_logo_photo_fields_accepted() -> None:
    """CHART-AP-42 — StakeholderNode 의 logo(공식 도메인)/photo(인물 사진 URL)
    필드가 가드를 통과해야 (렌더러 fallback 이 안전망이므로 가드는 관용)."""
    d = _valid()
    d["nodes"][0]["logo"] = "mnd.go.kr"
    d["nodes"][1]["kind"] = "person"
    d["nodes"][1]["photo"] = "https://upload.wikimedia.org/example.jpg"
    d["nodes"][2]["flag"] = "KR"
    g = StakeholderMapGuard(**d)
    assert g.nodes[0].logo == "mnd.go.kr"
    assert g.nodes[1].photo == "https://upload.wikimedia.org/example.jpg"
    assert g.nodes[2].flag == "KR"
