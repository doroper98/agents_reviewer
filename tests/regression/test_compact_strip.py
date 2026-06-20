"""compact-strip 렌더링 + 본문 폭 정렬 회귀 가드 (v5.2.8).

기능 SSOT (CLAUDE.md Change Propagation Matrix 의 다음 갱신 시 함께):
- ``src/templates/static/charts.css`` — `.compact-strip` / `.compact-row` 의
  2-col grid + 본문 폭 conform + min-width:0 + minmax(0, 1fr).
- ``src/templates/static/charts.js`` — `drawSparkline` + `renderSparklines` +
  `init()` 의 `renderSparklines()` 호출.
- ``src/templates/archetypes/freeform_essay.html`` — `_compact_split` 분기.
- ``src/orchestrator.py`` — `_build_compact_strip_row` / `_ensure_market_strip` /
  `_composer_instruments` 의 role='compact' 인식.

본 회귀의 catch:
1. v5.2.4 P0-Patch7 의 `minmax(220px, 1fr)` 회귀 — flex 자식 min-width 합산
   274px > 220px → 셀 강제 확장 → 옆 셀 침범. 본 테스트는 fix 키워드를 lock.
2. v5.2.5~v5.2.7 의 break-out 회귀 — ``width: min(1100px, ...)`` +
   ``translateX(-50%)`` 로 본문 좌우를 넘어서는 동작. v5.2.8 에서 본문 폭 안에
   가두는 설계로 반전. 회귀 시 본 테스트가 catch.
3. `role='compact'` payload 가 일반 chart-card 로 잘못 emit 되는 회귀.
4. `_ensure_market_strip` 이 idempotent 하지 않으면 중복 emit (스트립 다수).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CSS = _REPO_ROOT / "src" / "templates" / "static" / "charts.css"
_JS = _REPO_ROOT / "src" / "templates" / "static" / "charts.js"
_TPL = _REPO_ROOT / "src" / "templates" / "archetypes" / "freeform_essay.html"


def test_compact_strip_css_stays_within_container_width() -> None:
    """v5.2.8: strip 은 본문 ``.container`` (max 960px) 폭 안에 머무른다.

    v5.2.5~v5.2.7 의 break-out (``width: min(1100px, ...)`` +
    ``translateX(-50%)``) 은 데스크탑/태블릿에서 본문 좌우를 넘어가는 회귀.
    본 테스트가 다음을 강제:
    1. ``width: 100%`` + ``max-width: 100%`` + ``box-sizing: border-box`` —
       본문 폭에 conform.
    2. ``translateX(-50%)`` / ``left: 50%`` / ``min(1100px,`` 금지 — break-out
       회귀 차단.
    3. ``minmax(0, 1fr)`` — 셀이 콘텐츠로 부풀지 않도록 safety net.
    """
    css = _CSS.read_text(encoding="utf-8")
    idx = css.find(".compact-strip {")
    assert idx >= 0
    block = css[idx : css.find("}", idx)]
    assert "width: 100%" in block, (
        ".compact-strip width:100% 누락 — 본문 폭 conform 안 됨."
    )
    assert "max-width: 100%" in block, (
        ".compact-strip max-width:100% 누락 — 본문보다 더 넓어질 위험."
    )
    assert "box-sizing: border-box" in block, (
        ".compact-strip box-sizing:border-box 누락 — padding 이 폭 계산에 빠지면 "
        "본문 폭 overflow 회귀."
    )
    assert "min(1100px," not in block, (
        "v5.2.5~v5.2.7 break-out 잔존 — width:min(1100px, ...) 제거 필요."
    )
    assert "translateX(-50%)" not in block and "left: 50%" not in block, (
        "v5.2.5~v5.2.7 break-out 잔존 — translateX/left:50% 제거 필요."
    )
    assert "minmax(0, 1fr)" in block, (
        "grid-template-columns 의 minmax min 이 0 이어야 셀이 콘텐츠로 부풀지 않음 "
        "— 회귀 차단의 safety net."
    )


def test_compact_strip_css_two_column_grid_on_desktop_tablet() -> None:
    """v5.2.8: desktop/tablet 공통 2-col grid. 차트 수 N 가변 (3/5/7…) 은 grid
    자연 wrap 으로 처리 — 마지막 행에 odd cell 1 개 남는 형태가 정상 동작.

    이전 (v5.2.5~v5.2.7) 의 3-col 은 본문 폭 안에서 셀이 너무 좁아 sparkline
    표시 불가. 2-col × ~454px 셀 이 본문 폭 932px 안의 최적 비율.
    """
    css = _CSS.read_text(encoding="utf-8")
    idx = css.find(".compact-strip {")
    block = css[idx : css.find("}", idx)]
    assert "repeat(2, minmax(0, 1fr))" in block, (
        ".compact-strip grid 가 repeat(2, ...) 가 아니면 본문 폭 안에서 sparkline "
        "표시 불가 — v5.2.5~v5.2.7 3-col 회귀."
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
    """좁은 viewport 에서 cols 축소. v5.2.8: desktop/tablet 모두 2-col 이 base
    이므로 분기는 600px (1-col stack) 만. 920px 분기는 더 이상 의미 없음."""
    css = _CSS.read_text(encoding="utf-8")
    assert "max-width: 600px" in css, "600px breakpoint 누락 — 1-col stack fallback 회귀."


def test_compact_strip_css_has_vertical_separator_between_cells() -> None:
    """셀 사이 세로 구분선 (::after pseudo) — Bloomberg/FT 스타일.

    사용자 catch (v5.2.5): "너무 구분이 안가. 가로로 뭔가 계속 나열만 되어 있으니까".
    gap 만으로는 시각 구분 부족 → ::after 로 1px line 명시. v5.2.8 부터 2-col
    기준 selector (nth-child(2n) 제외).
    """
    css = _CSS.read_text(encoding="utf-8")
    sep_sel = ".compact-strip > .compact-row:not(:nth-child(2n)):not(:last-child)::after"
    assert sep_sel in css, (
        f"세로 separator selector ({sep_sel}) 누락 — 셀 시각 구분 회귀."
    )
    idx = css.find(sep_sel)
    block = css[idx : css.find("}", idx)]
    assert "content:" in block and "background:" in block, (
        "::after 가 빈 content + background 가져야 1px line 그림."
    )


def test_compact_strip_css_internal_row_grouping() -> None:
    """행 내부: [name | value | change] 그룹 vs [sparkline] 사이 시각 호흡.

    사용자 catch: "간격에 대한 고려도 없고" — gap 8px 외에 sparkline 앞에 추가
    margin-left 6px 로 그룹 분리.
    """
    css = _CSS.read_text(encoding="utf-8")
    spark_block = css[css.find(".compact-row .compact-spark {"):]
    spark_block = spark_block[: spark_block.find("}")]
    assert "margin-left:" in spark_block, (
        ".compact-spark 의 margin-left 누락 — [라벨+수치] 그룹 과 sparkline "
        "사이 호흡 부재. 모든 필드가 같은 gap 으로 나열되어 그룹 인식 어려움."
    )


def test_compact_strip_css_mobile_stacked_with_row_separators() -> None:
    """≤600px viewport 1-col stack 에서 행 사이 border-bottom 으로 ticker 분리.

    세로 stack 일 때 ::after 세로선은 의미 없음 → 행 간 horizontal divider 로
    각 ticker 가 독립 단위로 보이도록.
    """
    css = _CSS.read_text(encoding="utf-8")
    # @media (max-width: 600px) 블록 안에 .compact-row 가 border-bottom 갖고 있는지
    mobile_idx = css.find("@media (max-width: 600px)")
    assert mobile_idx >= 0
    # 해당 media query 블록의 끝까지 (다음 '}' 두번 닫히는 지점) — 간단히 다음 1500자만 검사
    mobile_block = css[mobile_idx : mobile_idx + 2000]
    assert "border-bottom" in mobile_block, (
        "mobile 1-col stack 에서 .compact-row border-bottom 누락 — ticker 분리 안 됨."
    )
    assert "border-bottom: none" in mobile_block, (
        "마지막 행 :last-child 의 border-bottom: none reset 누락 — 마지막 ticker "
        "밑에 불필요한 선 잔존."
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


def test_build_compact_strip_row_excludes_nan_tail() -> None:
    """CHART-AP-29 — 마지막 봉이 NaN 이면 등락률·마지막값이 'nan%' 로 새지 않는다.

    2026-06 코스피 회귀: Yahoo 미완성 마지막 봉이 close=NaN 으로 흘러들어 감시
    스트립이 '코스피 nan%', 카드가 'X → nan' 으로 노출. 비유한 봉은 sparkline·등락률
    양쪽에서 배제돼야 한다.
    """
    from src.orchestrator import _build_compact_strip_row
    row = _build_compact_strip_row({
        "instrument": "코스피", "source": "KRX",
        "start_date": "2026-05-21", "end_date": "2026-06-20",
        "data": [
            {"date": "2026-05-21", "close": 7815.59},
            {"date": "2026-06-19", "close": 9063.84},
            {"date": "2026-06-20", "close": float("nan")},
        ],
    })
    assert row is not None
    for field in ("change_day_pct_formatted", "last_value_formatted", "subtitle"):
        assert "nan" not in row[field].lower(), f"{field} 에 nan 누수: {row[field]!r}"
    assert row["last_value_formatted"] == "9,064"
    assert all(isinstance(p["y"], (int, float)) and p["y"] == p["y"] for p in row["data"])


def test_sanitize_market_nan_drops_nonfinite_bars() -> None:
    """CHART-AP-29 — fetch 직후 합류 길목에서 NaN/inf 봉을 결정적 제거."""
    from src.orchestrator import _sanitize_market_nan
    ts = [{"instrument": "코스피", "data": [
        {"date": "2026-06-17", "close": 8900.0},
        {"date": "2026-06-18", "close": float("nan")},
        {"date": "2026-06-19", "close": 9063.84},
        {"date": "2026-06-20", "close": float("inf")},
    ]}]
    removed = _sanitize_market_nan(ts)
    assert removed == 2
    closes = [d["close"] for d in ts[0]["data"]]
    assert closes == [8900.0, 9063.84]


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


def test_compact_period_label_buckets() -> None:
    """v5.2.9 — _compact_period_label 의 일수 버킷 (24H/1W/3M/1Y 등).

    사용자 catch: "기간이 얼마나 되는지 안적혀 있으니까 그게 지난 24h 인지,
    1 week 인지 전혀 모르겠어". 회귀 시 버킷 경계 drift 차단.
    """
    from src.orchestrator import _compact_period_label
    assert _compact_period_label("2026-05-16", "2026-05-17", 2) == "24H"
    assert _compact_period_label("2026-05-15", "2026-05-17", 3) == "2D"
    assert _compact_period_label("2026-05-10", "2026-05-17", 7) == "1W"
    assert _compact_period_label("2026-05-01", "2026-05-17", 16) == "2W"
    assert _compact_period_label("2026-04-17", "2026-05-17", 22) == "1M"
    assert _compact_period_label("2026-02-17", "2026-05-17", 65) == "3M"
    assert _compact_period_label("2025-11-17", "2026-05-17", 130) == "6M"
    assert _compact_period_label("2025-05-17", "2026-05-17", 250) == "1Y"
    assert _compact_period_label("2024-05-17", "2026-05-17", 500) == "2Y"
    assert _compact_period_label("2023-05-17", "2026-05-17", 750) == "3Y"


def test_compact_period_label_fallback_on_missing_dates() -> None:
    """start/end_date 파싱 실패 시 n_points 로 fallback. 0/1 포인트면 ''."""
    from src.orchestrator import _compact_period_label
    # 빈 / 파싱 불가 → n_points 로 일수 추정
    assert _compact_period_label("", "", 7) == "1W"
    assert _compact_period_label("bad", "date", 23) == "1M"
    # 데이터 없으면 빈 라벨
    assert _compact_period_label("", "", 0) == ""
    assert _compact_period_label("", "", 1) == ""


def test_build_compact_strip_row_emits_period_label() -> None:
    """v5.2.9 — _build_compact_strip_row 가 period_label 필드 emit.

    template 의 `.compact-period` 가 읽음. 누락 시 사용자가 sparkline 기간을
    인지 못함 — 회귀 차단.
    """
    from src.orchestrator import _build_compact_strip_row
    row = _build_compact_strip_row({
        "instrument": "코스피", "source": "YAHOO",
        "start_date": "2026-02-17", "end_date": "2026-05-17",
        "data": [{"date": "2026-02-17", "close": 3000.0},
                 {"date": "2026-05-17", "close": 3200.0}],
    })
    assert row is not None
    assert "period_label" in row, (
        "compact strip row 가 period_label 필드 누락 — sparkline 기간 표시 불가."
    )
    assert row["period_label"] == "3M"


def test_freeform_template_emits_compact_period_span() -> None:
    """v5.2.9 — freeform_essay 가 compact-row 안에 ``.compact-period`` span 을
    emit. CSS / payload 모두 갖췄어도 template 분기가 빠지면 화면에 안 보임."""
    tpl = _TPL.read_text(encoding="utf-8")
    assert "class=\"compact-period\"" in tpl, (
        "freeform_essay.html 의 compact-row 가 compact-period span 누락 — "
        "사용자가 sparkline 기간 (24H/1W/3M/1Y) 알 수 없음."
    )
    assert "ch.period_label" in tpl, (
        "freeform_essay 가 ch.period_label 읽지 않음 — payload 가 있어도 "
        "template 출력 안 됨."
    )


def test_compact_strip_css_has_period_rules() -> None:
    """v5.2.9 — `.compact-row .compact-period` CSS 규칙 존재.

    font / min-width / muted color 가 빠지면 다른 셀과 시각 호흡 깨짐.
    """
    css = _CSS.read_text(encoding="utf-8")
    sel = ".compact-row .compact-period {"
    assert sel in css, ".compact-period CSS 규칙 누락 — 기간 라벨 스타일링 없음."
    block = css[css.find(sel):]
    block = block[: block.find("}")]
    assert "min-width:" in block, ".compact-period min-width 누락 — 좁아져서 wrap 위험."
    # muted color 인지 (var(--muted) 또는 fg-3)
    assert "muted" in block or "fg-3" in block, (
        ".compact-period 가 muted 톤 아님 — primary 톤이면 sparkline 보다 시선 과다."
    )


def test_sparkline_uses_linear_curve_not_monotone() -> None:
    """v5.2.9 — sparkline 이 curveLinear 사용. curveMonotoneX 는 일간 종가 변동
    을 베지에로 평탄화 → 실제 가격 흐름 (jaggedness) 이 시각적으로 사라짐.

    사용자 catch: "가격 흐름이 너무 부드러운 곡선으로만 보이는걸 실제 가격
    흐름을 알 수 있는 라인 형태로 보완". 회귀 시 curve 함수 drift 차단.
    """
    js = _JS.read_text(encoding="utf-8")
    spark_idx = js.find("function drawSparkline")
    assert spark_idx >= 0
    spark_block = js[spark_idx : js.find("\n  }", spark_idx) + 4]
    assert "d3.curveLinear" in spark_block, (
        "drawSparkline 이 curveLinear 안 씀 — 부드러운 곡선으로 실제 가격 변동 "
        "사라짐 회귀. monotone/cardinal/basis 등 smoothing curve 금지."
    )
    assert "d3.curveMonotoneX" not in spark_block, (
        "drawSparkline 에 curveMonotoneX 잔존 — v5.2.9 fix 의 회귀."
    )


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


# ─── v5.2.13 — 풀 카드 보장 회귀 가드 ────────────────────────────────────────


def _mk_ts_series(name: str, source: str, chart_type: str, code: str = "") -> dict:
    """헬퍼 — instrument 별 시계열 series dict (2-point OHLC)."""
    return {
        "instrument": name, "source": source, "chart_type": chart_type, "code": code,
        "start_date": "2026-02-17", "end_date": "2026-05-17",
        "data": [
            {"date": "2026-02-17", "close": 100.0, "open": 100, "high": 101, "low": 99},
            {"date": "2026-05-17", "close": 110.0, "open": 109, "high": 112, "low": 108},
        ],
    }


def test_count_existing_ts_charts_excludes_compact_strip() -> None:
    """v5.2.13 — _count_existing_ts_charts 가 strip row (role='compact') 를 제외.

    strip 의 type 도 ``line`` 이지만 sparkline 용 다른 시각 역할. 분자에 포함하면
    풀 카드 보장 (fallback 강제 emit 조건 = 0) 판정에서 v5.2.5 회귀가 영구화된다.
    """
    from src.orchestrator import _count_existing_ts_charts
    composed = SimpleNamespace(sections=[SimpleNamespace(charts=[
        {"role": "compact", "type": "line", "instrument": "코스피",
         "data": [{"x": "d", "y": 1}]},
        {"role": "compact", "type": "line", "instrument": "삼성전자",
         "data": [{"x": "d", "y": 1}]},
    ])])
    assert _count_existing_ts_charts(composed) == 0, (
        "compact strip row 가 풀 카드 카운트에 포함됨 — fallback 강제 emit 조건 "
        "(==0) 판정 깨짐. v5.2.13 fix 의 회귀."
    )
    # 풀 카드 1 개 추가 → 카운트 1
    composed.sections[0].charts.append(
        {"type": "candle", "title": "삼성전자 (005930)",
         "data": [{"date": "2026-02-17", "open": 70000, "high": 71000,
                   "low": 69500, "close": 70500}]}
    )
    assert _count_existing_ts_charts(composed) == 1
    # 비-시계열 (bar 등) 은 카운트 X
    composed.sections[0].charts.append({"type": "bar", "data": [{"label": "x", "value": 1}]})
    assert _count_existing_ts_charts(composed) == 1


def test_ensure_time_series_chart_guarantees_full_card_when_composer_emits_zero() -> None:
    """v5.2.13 — composer 풀 카드 0 + strip 3+ 일 때 fallback 이 ≥1 풀 카드 강제.

    사용자 catch (v5.2.5 회귀): '차트 관련 정보가 컴팩트 스트립 차트만 계속 나옴'.
    원인: _ensure_market_strip 이 모든 instrument 를 compact row 로 박은 후
    _composer_instruments 가 모두 covered 로 반환 → fallback 의 dedupe 가 모든
    instrument 를 잘라 no-op → 사용자가 strip 만 봄.

    본 테스트는 fallback 이 풀 카드 ≥1 보장하는지 lock. 회귀 시 catch.
    """
    from src.orchestrator import (
        _ensure_market_strip, _ensure_time_series_chart, _count_existing_ts_charts,
    )
    context = SimpleNamespace(
        time_series=[
            _mk_ts_series("코스피", "YAHOO", "line"),
            _mk_ts_series("삼성전자", "KRX", "candle", "005930"),
            _mk_ts_series("SK하이닉스", "KRX", "candle", "000660"),
            _mk_ts_series("WTI", "FRED", "area"),
        ],
        timeline=[], summary="", category="financial",
    )
    composed = SimpleNamespace(sections=[SimpleNamespace(heading="첫 섹션", charts=[])])
    _ensure_market_strip(composed, context)
    _ensure_time_series_chart(composed, context)
    full_n = _count_existing_ts_charts(composed)
    strip_n = sum(1 for c in composed.sections[0].charts if c.get("role") == "compact")
    assert full_n >= 1, (
        f"composer 풀 카드 0 + 4 instruments strip 후 풀 카드 = {full_n}. "
        "v5.2.13 fix 가 풀 카드 ≥1 강제 보장 실패 — 사용자가 strip 만 보게됨."
    )
    assert strip_n >= 1, "strip 도 함께 보존되어야 — 풀 카드와 분리된 시각 역할."


def test_ensure_time_series_chart_preserves_composer_full_card() -> None:
    """v5.2.13 — composer 가 풀 카드 1 개 emit 했으면 fallback 이 *추가 풀 카드*
    안 박음. strip 는 별개 시각 역할로 동시 존재 OK.

    composer 의 emit 의도 (narrative 핵심 instrument 만 강조) 보존. 모든 instrument
    풀 카드는 시각 혼잡 — strip 의 at-a-glance 역할과 중복.
    """
    from src.orchestrator import (
        _ensure_market_strip, _ensure_time_series_chart, _count_existing_ts_charts,
    )
    context = SimpleNamespace(
        time_series=[
            _mk_ts_series("코스피", "YAHOO", "line"),
            _mk_ts_series("삼성전자", "KRX", "candle", "005930"),
            _mk_ts_series("SK하이닉스", "KRX", "candle", "000660"),
            _mk_ts_series("WTI", "FRED", "area"),
        ],
        timeline=[], summary="", category="financial",
    )
    composer_candle = {
        "type": "candle", "title": "삼성전자 (005930)",
        "data": [{"date": "2026-02-17", "open": 70000, "high": 71000,
                  "low": 69500, "close": 70500}],
    }
    composed = SimpleNamespace(sections=[
        SimpleNamespace(heading="첫 섹션", charts=[composer_candle])
    ])
    _ensure_market_strip(composed, context)
    _ensure_time_series_chart(composed, context)
    full_n = _count_existing_ts_charts(composed)
    assert full_n == 1, (
        f"composer 풀 candle 1 + fallback 후 풀 카드 = {full_n}. fallback 이 "
        "composer 의도 무시하고 추가 풀 카드 박음 — 시각 혼잡 회귀."
    )


def test_ensure_time_series_chart_force_picks_data_richest() -> None:
    """v5.2.13 — 풀 카드 강제 emit 시 *data 가 가장 풍부한 series* 선택.

    여러 instrument 중 어떤 걸 강제 풀 카드로 만들지의 결정 규칙 lock. data
    포인트가 많은 series 가 더 정보 풍부 → 사용자 시각적 가치 큼.
    """
    from src.orchestrator import _ensure_market_strip, _ensure_time_series_chart
    # 코스피 = 5점, 삼성 = 10점, 하이닉스 = 3점 → 삼성이 풀 카드로 선택
    def _series(name, src, ctype, n_points, code=""):
        return {
            "instrument": name, "source": src, "chart_type": ctype, "code": code,
            "start_date": "2026-02-17", "end_date": "2026-05-17",
            "data": [{"date": f"2026-05-{i+1:02d}", "close": 100 + i,
                      "open": 100 + i, "high": 101 + i, "low": 99 + i}
                     for i in range(n_points)],
        }
    context = SimpleNamespace(
        time_series=[
            _series("코스피", "YAHOO", "line", 5),
            _series("삼성전자", "KRX", "candle", 10, "005930"),
            _series("SK하이닉스", "KRX", "candle", 3, "000660"),
        ],
        timeline=[], summary="", category="financial",
    )
    composed = SimpleNamespace(sections=[SimpleNamespace(heading="첫 섹션", charts=[])])
    _ensure_market_strip(composed, context)
    _ensure_time_series_chart(composed, context)
    full_cards = [c for c in composed.sections[0].charts if c.get("role") != "compact"]
    assert len(full_cards) >= 1
    # 첫 (가장 앞쪽) 풀 카드의 instrument 가 삼성전자여야
    primary_title = (full_cards[0].get("title") or "")
    assert "삼성전자" in primary_title, (
        f"data 가장 풍부한 instrument (삼성전자, 10 points) 가 풀 카드 강제 대상 "
        f"이어야. 실제 첫 풀 카드 title = {primary_title!r}"
    )
