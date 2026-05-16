"""compact-strip 렌더링 + overflow root-fix 회귀 가드 (v5.2.5).

기능 SSOT (CLAUDE.md Change Propagation Matrix 의 다음 갱신 시 함께):
- ``src/templates/static/charts.css`` — `.compact-strip` / `.compact-row` 의
  ROOT-FIX 주석 + min-width:0 + minmax(0, 1fr).
- ``src/templates/static/charts.js`` — `drawSparkline` + `renderSparklines` +
  `init()` 의 `renderSparklines()` 호출.
- ``src/templates/archetypes/freeform_essay.html`` — `_compact_split` 분기.
- ``src/orchestrator.py`` — `_build_compact_strip_row` / `_ensure_market_strip` /
  `_composer_instruments` 의 role='compact' 인식.

본 회귀의 catch:
1. v5.2.4 P0-Patch7 의 `minmax(220px, 1fr)` 회귀 — flex 자식 min-width 합산
   274px > 220px → 셀 강제 확장 → 옆 셀 침범. 본 테스트는 fix 키워드를 lock.
2. `role='compact'` payload 가 일반 chart-card 로 잘못 emit 되는 회귀.
3. `_ensure_market_strip` 이 idempotent 하지 않으면 중복 emit (스트립 다수).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CSS = _REPO_ROOT / "src" / "templates" / "static" / "charts.css"
_JS = _REPO_ROOT / "src" / "templates" / "static" / "charts.js"
_TPL = _REPO_ROOT / "src" / "templates" / "archetypes" / "freeform_essay.html"


def test_compact_strip_css_uses_minmax_zero_fr_root_fix() -> None:
    """ROOT-FIX 1: grid track 의 minimum 이 0 이어야 flex 자식이 셀 확장 못함."""
    css = _CSS.read_text(encoding="utf-8")
    assert ".compact-strip {" in css, "compact-strip CSS 누락"
    # 핵심: minmax(0, 1fr) — auto/220px 등 콘텐츠 기반 min 은 회귀
    assert "minmax(0, 1fr)" in css, (
        "compact-strip grid-template-columns 의 minmax min 이 0 이어야 함. "
        "minmax(220px, 1fr) 같은 회귀가 들어가면 274px 콘텐츠가 셀을 확장 → "
        "옆 셀 침범 (v5.2.4 P0-Patch7 의 첫 catch)."
    )


def test_compact_strip_css_flex_children_have_min_width_zero() -> None:
    """ROOT-FIX 2~3: row + value/change/spark 의 min-width:0 가 모두 있어야.

    하나라도 빠지면 해당 자식이 콘텐츠로 셀을 부풀려서 옆 셀 침범 회귀.
    """
    css = _CSS.read_text(encoding="utf-8")
    # 단순 substring 으로 4개 .compact-* selector 가 min-width:0 갖고 있는지 확인
    for selector in (
        ".compact-row {",
        ".compact-row .compact-value {",
        ".compact-row .compact-change {",
        ".compact-row .compact-spark {",
    ):
        idx = css.find(selector)
        assert idx >= 0, f"{selector} 누락"
        # 다음 `}` 까지가 해당 selector 의 declaration block
        block = css[idx : css.find("}", idx)]
        assert "min-width: 0" in block, (
            f"{selector} declaration 에 min-width: 0 없음 — overflow 회귀."
        )


def test_compact_strip_css_sparkline_overflow_hidden() -> None:
    """spark 가 squeeze 시 SVG 가 옆 셀로 escape 못하도록 overflow:hidden 명시."""
    css = _CSS.read_text(encoding="utf-8")
    idx = css.find(".compact-row .compact-spark {")
    block = css[idx : css.find("}", idx)]
    assert "overflow: hidden" in block, (
        "compact-spark 에 overflow: hidden 없음 — sparkline SVG 가 옆 셀 침범 위험."
    )


def test_charts_js_has_sparkline_renderer() -> None:
    """drawSparkline + renderSparklines + init() 호출 3종 모두 존재해야."""
    js = _JS.read_text(encoding="utf-8")
    assert "function drawSparkline" in js, "drawSparkline 함수 누락"
    assert "function renderSparklines" in js, "renderSparklines 함수 누락"
    # init() 안에서 renderSparklines 호출
    init_idx = js.find("function init()")
    assert init_idx >= 0
    init_block = js[init_idx : js.find("\n  }", init_idx) + 4]
    assert "renderSparklines()" in init_block, (
        "init() 안에서 renderSparklines() 호출 누락 — strip SVG 가 빈 채로 렌더."
    )


def test_freeform_template_splits_compact_charts() -> None:
    """role='compact' 차트는 compact-strip 으로, 나머지는 chart-card 로 분리 렌더."""
    tpl = _TPL.read_text(encoding="utf-8")
    assert "_compact_split" in tpl, "freeform_essay 가 role 별 split 안 함"
    assert "class=\"compact-strip\"" in tpl
    assert "class=\"compact-row\"" in tpl
    assert "_compact_split.c" in tpl and "_compact_split.f" in tpl


def test_build_compact_strip_row_value_formatting() -> None:
    """_format_compact_value 의 instrument 별 분기 — 회귀 시 즉시 catch."""
    from src.orchestrator import _format_compact_value
    assert _format_compact_value(4.52, "미국채 10Y") == "4.52%"
    assert _format_compact_value(105.58, "달러인덱스") == "105.58"
    assert _format_compact_value(72273.45, "비트코인") == "$72,273"
    assert _format_compact_value(3200.5, "코스피") == "3,200"
    assert _format_compact_value(2.5, "WTI 유가") == "2.50"  # 유가는 rate 가 아님


def test_build_compact_strip_row_emits_required_fields() -> None:
    """payload 가 template 이 읽는 6개 필드 (role/instrument/last_value/change_day_*)
    + sparkline 가 그릴 data 갖춰야."""
    from src.orchestrator import _build_compact_strip_row
    row = _build_compact_strip_row({
        "instrument": "달러인덱스", "source": "FRED",
        "start_date": "2026-02-23", "end_date": "2026-05-15",
        "data": [
            {"date": "2026-02-23", "close": 104.39},
            {"date": "2026-05-15", "close": 105.58},
        ],
    })
    assert row is not None
    assert row["role"] == "compact"
    assert row["type"] == "line"
    assert row["instrument"] == "달러인덱스"
    assert row["last_value_formatted"] == "105.58"
    assert "change_day_pct" in row
    assert row["change_day_pct_formatted"].endswith("%")
    assert len(row["data"]) == 2
    assert row["data"][0] == {"x": "2026-02-23", "y": 104.39}


def test_build_compact_strip_row_skips_insufficient_data() -> None:
    """data 가 2 점 미만이면 row 자체 emit 안 함 (빈 sparkline 회귀 차단)."""
    from src.orchestrator import _build_compact_strip_row
    assert _build_compact_strip_row({"instrument": "X", "data": []}) is None
    assert _build_compact_strip_row(
        {"instrument": "X", "data": [{"date": "d", "close": 1.0}]}
    ) is None


def test_ensure_market_strip_threshold_3() -> None:
    """instrument 3 개↑ 일 때만 strip emit. <3 은 풀 차트가 더 정보 밀도 높음."""
    from src.orchestrator import _ensure_market_strip

    def _ctx(n):
        return SimpleNamespace(time_series=[
            {"instrument": f"종목{i}", "start_date": "2026-02-23",
             "end_date": "2026-05-15", "source": "FRED",
             "data": [{"date": "2026-02-23", "close": 100.0},
                      {"date": "2026-05-15", "close": 105.0}]}
            for i in range(n)
        ])

    for n_below in (0, 1, 2):
        composed = SimpleNamespace(sections=[SimpleNamespace(charts=[])])
        _ensure_market_strip(composed, _ctx(n_below))
        assert composed.sections[0].charts == [], f"n={n_below} 에서 strip emit 됨"

    composed = SimpleNamespace(sections=[SimpleNamespace(charts=[])])
    _ensure_market_strip(composed, _ctx(3))
    assert len(composed.sections[0].charts) == 3
    assert all(c["role"] == "compact" for c in composed.sections[0].charts)


def test_ensure_market_strip_idempotent() -> None:
    """두 번 호출해도 중복 emit 없음 (이미 role='compact' 있으면 skip)."""
    from src.orchestrator import _ensure_market_strip
    context = SimpleNamespace(time_series=[
        {"instrument": f"종목{i}", "start_date": "2026-02-23",
         "end_date": "2026-05-15", "source": "FRED",
         "data": [{"date": "2026-02-23", "close": 100.0},
                  {"date": "2026-05-15", "close": 105.0}]}
        for i in range(3)
    ])
    composed = SimpleNamespace(sections=[SimpleNamespace(charts=[])])
    _ensure_market_strip(composed, context)
    _ensure_market_strip(composed, context)
    _ensure_market_strip(composed, context)
    assert len(composed.sections[0].charts) == 3, "중복 emit 됨"


def test_composer_instruments_picks_up_compact_role() -> None:
    """_composer_instruments 가 compact strip row 도 dedupe 집합에 포함해야
    _ensure_time_series_chart 가 같은 instrument 풀 차트로 중복 emit 안 함."""
    from src.orchestrator import _composer_instruments
    composed = SimpleNamespace(sections=[SimpleNamespace(charts=[
        {"role": "compact", "type": "line", "instrument": "미국채 10Y",
         "data": [{"x": "d", "y": 1}]},
        {"role": "compact", "type": "line", "instrument": "달러인덱스",
         "data": [{"x": "d", "y": 1}]},
    ])])
    seen = _composer_instruments(composed)
    assert "미국채 10Y" in seen
    assert "달러인덱스" in seen
