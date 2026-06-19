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
