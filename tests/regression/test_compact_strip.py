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


def test_compact_strip_css_breaks_out_of_narrow_container() -> None:
    """ROOT-FIX: 모크업 (samples/market_charts_mockup.html) 의 wider context 재현.

    .freeform-section .container 는 max-width 780px → 752px / 3 cols = 244px 셀
    로 모크업 콘텐츠 274px 가 안 들어감. strip 만 viewport 폭 (max 1100px) 으로
    break-out 시켜 모크업 1200px wrap 의 시각 정합 회복. ``left:50% + translateX``
    조합 + ``width: min(1100px, ...)`` 가 모두 있어야.
    """
    css = _CSS.read_text(encoding="utf-8")
    idx = css.find(".compact-strip {")
    assert idx >= 0
    block = css[idx : css.find("}", idx)]
    assert "min(1100px," in block, (
        ".compact-strip 의 width 가 min(1100px, ...) 아니면 break-out 안 됨 "
        "— 모크업 wider context 재현 불가."
    )
    assert "left: 50%" in block and "translateX(-50%)" in block, (
        ".compact-strip 의 viewport 중앙 정렬 (left:50% + translateX) 누락 "
        "— breakout 이 .container 왼쪽 정렬 상태로 어긋남."
    )
    assert "minmax(0, 1fr)" in block, (
        "grid-template-columns 의 minmax min 이 0 이어야 셀이 콘텐츠로 부풀지 않음 "
        "— 회귀 차단의 safety net."
    )


def test_compact_strip_css_mockup_values_preserved() -> None:
    """모크업 (market_charts_mockup.html L121~124) 의 값을 글자 그대로 보존.

    사용자 명시 요청: "이 유첨 양식이랑 동일하게 적용". 회귀 시 lock 만으로
    값 drift 차단.
    """
    css = _CSS.read_text(encoding="utf-8")
    name_block = css[css.find(".compact-row .compact-name {"):]
    name_block = name_block[: name_block.find("}")]
    assert "width: 64px" in name_block and "flex-shrink: 0" in name_block, (
        ".compact-name 모크업 값 (width:64px, flex-shrink:0) 보존 안 됨."
    )
    value_block = css[css.find(".compact-row .compact-value {"):]
    value_block = value_block[: value_block.find("}")]
    assert "min-width: 70px" in value_block, ".compact-value min-width:70px 회귀."
    chg_block = css[css.find(".compact-row .compact-change {"):]
    chg_block = chg_block[: chg_block.find("}")]
    assert "min-width: 50px" in chg_block, ".compact-change min-width:50px 회귀."
    spark_block = css[css.find(".compact-row .compact-spark {"):]
    spark_block = spark_block[: spark_block.find("}")]
    assert "flex: 1" in spark_block and "min-width: 60px" in spark_block, (
        ".compact-spark 모크업 값 (flex:1, min-width:60px) 보존 안 됨."
    )
    assert "overflow: hidden" in spark_block, (
        ".compact-spark 의 overflow:hidden 누락 — squeeze 시 SVG escape 위험."
    )


def test_compact_strip_css_row_min_width_zero_safety() -> None:
    """`.compact-row { min-width: 0 }` — break-out 이 동작 안 하는 edge case
    (viewport < 모크업 wrap) 에서도 행이 grid cell 폭에 conform 하도록."""
    css = _CSS.read_text(encoding="utf-8")
    idx = css.find(".compact-row {")
    block = css[idx : css.find("}", idx)]
    assert "min-width: 0" in block, (
        ".compact-row min-width:0 누락 — break-out 이 작동 안 하는 edge case 에서 "
        "flex auto min-content 가 grid cell 강제 확장 → overflow 회귀."
    )


def test_compact_strip_css_responsive_fallback() -> None:
    """좁은 viewport (모크업 wrap 미만) 에선 cols 자동 축소.

    920px ↓ → 2 cols, 600px ↓ → 1 col. 콘텐츠가 셀에 못 들어가는 viewport 에선
    overflow 보다 stack 이 항상 더 가독성 좋음.
    """
    css = _CSS.read_text(encoding="utf-8")
    assert "max-width: 920px" in css, "920px breakpoint 누락 — 2-col fallback 회귀."
    assert "max-width: 600px" in css, "600px breakpoint 누락 — 1-col stack fallback 회귀."


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
