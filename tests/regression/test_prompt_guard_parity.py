"""CHART-AP-44 재발 차단 — 프롬프트 문서 모양 ↔ validator 가드 parity (v8.5.11).

composer SYSTEM_PROMPT 의 [type 별 data 스키마] 섹션이 문서화한 *정확한* 데이터
모양이 모든 등록 type 에 대해 ``validate_chart_data`` 를 통과하는지 검증한다.

배경: stakeholder_map (CHART-AP-38, v8.2.10) 에 이어 heatmap·stacked 도
프롬프트가 가르치는 모양과 가드가 요구하는 모양이 어긋나 **100% silent drop**
되고 있었다 (CHART-AP-44, v8.5.11). 세 사고 모두 "가드는 자기 모양으로만
테스트되고, 프롬프트 모양으로는 한 번도 검증되지 않아" 발생 — 본 파일이 그
클래스를 통째로 차단한다.

규칙:
- ``_TYPE_TO_GUARD`` 에 새 type 을 등록하면 본 파일의 ``PROMPT_SHAPES`` 에도
  프롬프트가 문서화한 모양 그대로의 fixture 를 추가해야 한다 (완전성 테스트가
  강제). SYSTEM_PROMPT 의 스키마 라인을 고치면 여기 fixture 도 함께 고칠 것.
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.visual.schemas import (
    _TYPE_TO_GUARD,
    chart_renderable,
    validate_chart_data,
    validate_chart_options,
)

# SYSTEM_PROMPT [type 별 data 스키마] 가 문서화한 모양 그대로.
# key = chart type, value = 그 type 의 대표 data payload (list 는 여러 변형).
PROMPT_SHAPES: dict[str, list] = {
    "bar": [
        [{"label": "A", "value": 10}, {"label": "B", "value": 20}],
        # v8.6.1 §4.1 — 행 단위 prior (F6 Paired Rungs)
        [{"label": "A", "value": 10, "prior": 7}, {"label": "B", "value": 20, "prior": 22}],
    ],
    "donut": [[
        {"label": "A", "value": 40}, {"label": "B", "value": 35}, {"label": "C", "value": 25},
    ]],
    "line": [[{"x": "2026-05-13", "y": 7900}, {"x": "2026-05-14", "y": 8002.66}]],
    "candle": [[
        {"date": "2026-05-13", "open": 92000, "high": 93500, "low": 91500, "close": 93000},
        {"date": "2026-05-14", "open": 93000, "high": 94200, "low": 92800, "close": 94000},
    ]],
    "area": [[{"x": "2026-05-13", "y": 61.2}, {"x": "2026-05-14", "y": 63.4}]],
    "gantt": [[
        {"label": "협상", "start": "2026-01", "end": "2026-03"},
        {"label": "비준", "start": "2026-03", "end": "2026-06"},
    ]],
    "stakeholder_map": [{
        "nodes": [
            {"id": "kr", "label": "한국", "col": "left", "flag": "KR"},
            {"id": "us", "label": "미국", "col": "right", "flag": "US"},
        ],
        "edges": [{"source": "kr", "target": "us", "type": "동맹"}],
    }],
    # CHART-AP-44 — 프롬프트 계약 {scenarios} (구 가드는 {categories, series} 를 요구해 100% drop)
    "stacked": [{
        "scenarios": [
            {"name": "낙관", "segments": [{"label": "수출", "value": 40}, {"label": "내수", "value": 30}]},
            {"name": "비관", "segments": [{"label": "수출", "value": 22}, {"label": "내수", "value": 18}]},
        ],
    }],
    "bubble": [[
        {"label": "A", "x": 0.3, "y": 0.7, "size": 12},
        {"label": "B", "x": 0.6, "y": 0.4, "size": 8},
        {"label": "C", "x": 0.8, "y": 0.9, "size": 20},
    ]],
    # CHART-AP-44 — 양형: 강도 트랙형 (v7.1.0 렌더러 계약) + 격자형 (결정 트리 §6)
    "heatmap": [
        [{"title": "공급 차질", "severity": "high"}, {"title": "수요 둔화", "severity": "low"}],
        [
            {"x": "대만", "y": "파운드리", "value": 5},
            {"x": "대만", "y": "패키징", "value": 4},
            {"x": "한국", "y": "파운드리", "value": 3},
            {"x": "한국", "y": "패키징", "value": 2},
        ],
    ],
    "dual_line": [{
        "left": {"label": "원유", "unit": "$/bbl", "series": [{"x": "1", "y": 60}, {"x": "2", "y": 62}]},
        "right": {"label": "환율", "unit": "USD/KRW", "series": [{"x": "1", "y": 1400}, {"x": "2", "y": 1380}]},
    }],
    "forecast": [{
        "actual": [{"x": "2025", "y": 100}, {"x": "2026", "y": 110}],
        "forecast": [{"x": "2027", "mid": 120, "low": 110, "high": 130}],
        "fork_at": "2026",
    }],
    "choropleth": [[
        {"country_code": "KR", "value": 12.4},
        {"country_code": "JP", "value": 10.8},
        {"country_code": "US", "value": 8.1},
    ]],
    "scatter": [[
        {"label": "한국", "x": 1.2, "y": 3.4},
        {"label": "일본", "x": 0.8, "y": 2.1, "accent": True},
        {"label": "미국", "x": 2.4, "y": 4.0},
    ]],
    "stacked_area": [{
        "series": [
            {"name": "A", "values": [{"x": i, "y": 10 + i} for i in range(6)]},
            {"name": "B", "values": [{"x": i, "y": 5 + i} for i in range(6)]},
        ],
    }],
    "lollipop": [[{"label": f"항목{i}", "value": 100 - i * 7} for i in range(8)]],
    "slope": [{
        "left_label": "2020", "right_label": "2025",
        "items": [
            {"label": "IT", "a": 14, "b": 24},
            {"label": "에너지", "a": 9, "b": 6},
            {"label": "금융", "a": 12, "b": 11},
        ],
    }],
    "small_multiples": [{
        "panels": [
            {"label": f"국가{p}", "series": [{"x": i, "y": p + i} for i in range(6)]}
            for p in range(4)
        ],
    }],
    "waterfall": [[
        {"label": "시작", "value": 100, "type": "total"},
        {"label": "증가", "value": 30, "type": "pos"},
        {"label": "감소", "value": 12, "type": "neg"},
        {"label": "종료", "value": 118, "type": "total"},
    ]],
    "range_bar": [
        [
            {"label": "A", "low": 10, "high": 20},
            {"label": "B", "low": 12, "high": 30},
            {"label": "C", "low": 8, "high": 15},
        ],
        # v8.6.1 §4.6 — mode:"before_after" 행 형식 (감소도 정상)
        [
            {"label": "A", "before": 14, "after": 6},
            {"label": "B", "before": 19, "after": 9},
            {"label": "C", "before": 17, "after": 21},
        ],
    ],
    "sankey": [{
        "nodes": [
            {"id": "rev", "label": "총매출"},
            {"id": "ds", "label": "DS 반도체"},
            {"id": "op", "label": "영업이익", "accent": True},
        ],
        "links": [
            {"source": "rev", "target": "ds", "value": 81.7},
            {"source": "ds", "target": "op", "value": 53.7},
        ],
    }],
    "bump": [{
        "periods": ["2023", "2024", "2025"],
        "items": [
            {"name": "A사", "ranks": [2, 1, 1], "accent": True},
            {"name": "B사", "ranks": [1, 2, 2]},
            {"name": "C사", "ranks": [3, 3, 3]},
        ],
    }],
    "bullet": [[
        {"label": "매출", "value": 82, "target": 100},
        {"label": "이익", "value": 45, "target": 40, "ranges": [30, 40, 55]},
    ]],
    "connected_scatter": [[
        {"x": 1.0, "y": 2.0, "label": "2023"},
        {"x": 1.4, "y": 2.6},
        {"x": 2.1, "y": 2.4},
        {"x": 2.8, "y": 3.1, "label": "2026"},
    ]],
    "combo": [{
        "bars": {"label": "거래대금", "unit": "조원", "series": [{"x": "1", "y": 10}, {"x": "2", "y": 14}, {"x": "3", "y": 9}]},
        "line": {"label": "코스피", "unit": "pt", "series": [{"x": "1", "y": 9000}, {"x": "2", "y": 9100}, {"x": "3", "y": 9050}]},
    }],
    "diverging_bar": [[
        {"label": "20대", "neg": 42, "pos": 51},
        {"label": "30대", "neg": 47, "pos": 45},
    ]],
    "pyramid": [[
        {"bracket": "0-19", "left": 380, "right": 360},
        {"bracket": "20-39", "left": 620, "right": 590},
        {"bracket": "40-59", "left": 800, "right": 790},
        {"bracket": "60+", "left": 540, "right": 660},
    ]],
    "dot_matrix": [[
        {"label": "비정규직", "value": 38, "accent": True},
        {"label": "정규직", "value": 62},
    ]],
}

# _TYPE_TO_GUARD 의 별칭 (동일 가드 공유) — fixture 는 대표 이름으로만 둔다.
_ALIASES = {"stacked_bar": "stacked"}


def test_every_guarded_type_has_prompt_fixture() -> None:
    """_TYPE_TO_GUARD 에 등록된 모든 type 은 PROMPT_SHAPES fixture 필수.

    새 type 을 가드에 등록하면서 여기 fixture 를 빠뜨리면 본 테스트가 실패한다
    — 프롬프트 모양 검증 없이 랜딩되는 것을 차단 (CHART-AP-38/44 클래스).
    """
    guarded = {(_ALIASES.get(t) or t) for t in _TYPE_TO_GUARD}
    missing = guarded - set(PROMPT_SHAPES)
    assert not missing, f"PROMPT_SHAPES fixture 누락: {sorted(missing)}"


def test_prompt_documented_shapes_pass_validation() -> None:
    """프롬프트가 문서화한 모양 그대로가 모든 type 에서 guard 를 통과해야 한다."""
    failures = []
    for chart_type, payloads in PROMPT_SHAPES.items():
        for i, data in enumerate(payloads):
            ok, reason = validate_chart_data(chart_type, data)
            if not ok:
                failures.append(f"{chart_type}[{i}]: {reason}")
    assert not failures, "프롬프트 모양이 가드에서 drop 됨:\n" + "\n".join(failures)


def test_alias_types_share_guard() -> None:
    """stacked_bar 별칭도 동일 (scenarios) 계약으로 통과."""
    ok, reason = validate_chart_data("stacked_bar", PROMPT_SHAPES["stacked"][0])
    assert ok, reason


def test_prompt_shapes_pass_template_gate() -> None:
    """v8.5.14 — parity 를 **3중** 으로: 가드 통과 → *템플릿 has_data 게이트도 통과*.

    v8.5.12 는 이 층을 검증하지 않아, `chart_renderable` 에 gantt 를 dict{rows}
    전용으로 등록하는 순간 프롬프트 준수 gantt(list 계약)가 전량 카드에서 사라졌다
    (Codex 리뷰 P1 catch — CHART-AP-38/44 와 같은 클래스를 수리하면서 재생산).
    가드만 보면 통과하므로 이 테스트 없이는 영원히 안 보인다.
    """
    failures = []
    for chart_type, payloads in PROMPT_SHAPES.items():
        for i, data in enumerate(payloads):
            if not chart_renderable({"type": chart_type, "data": data}):
                failures.append(f"{chart_type}[{i}]")
    assert not failures, (
        "가드는 통과하는데 템플릿 has_data 게이트에서 카드가 사라지는 type:\n"
        + "\n".join(failures)
    )


def test_empty_data_never_renders() -> None:
    """빈 데이터는 어떤 type 이든 카드를 만들지 않는다 (CHART-AP-28 빈 프레임)."""
    for chart_type in PROMPT_SHAPES:
        for empty in ([], {}, None):
            assert not chart_renderable({"type": chart_type, "data": empty}), (
                f"{chart_type}: 빈 데이터({empty!r})인데 렌더 허용"
            )


# ─── v8.6.1 — payload 표현 옵션 parity (플랜 §4) ─────────────────────────
# 프롬프트가 가르치는 옵션 값이 옵션 가드를 통과하는지, 계약 밖 값은 막히는지.
PROMPT_OPTIONS: dict[str, list[dict]] = {
    "bar": [
        {"unit_label": "건"},
        {"orientation": "vertical"},
        {"texture": "tick"}, {"texture": "dot"},
        {"texture": "capsule"}, {"texture": "rung"},
        {"unit": 5},
    ],
    "lollipop": [{"texture": "dot"}, {"texture": "stem"}, {"unit_label": "건"}],
    "line": [{"marks": "none"}],
    "area": [{"fill": "gradient"}],
    "scatter": [{"marks": "none"}, {"x_low_label": "낮음", "x_high_label": "높음"}],
    "range_bar": [{"mode": "before_after"}, {"mode": "range"},
                  {"low_label": "최저", "high_label": "최고"}],
    "heatmap": [{"cells": "grid"}],
}

REJECTED_OPTIONS: list[tuple[str, dict]] = [
    ("bar", {"texture": "zigzag"}),
    ("bar", {"orientation": "diagonal"}),
    ("bar", {"unit": 0}),
    ("bar", {"unit": -3}),
    ("lollipop", {"texture": "capsule"}),
    ("line", {"marks": "daily"}),
    ("area", {"fill": "solid"}),
    ("range_bar", {"mode": "delta"}),
    ("heatmap", {"cells": "round-ish"}),
]


def test_prompt_documented_options_pass_option_guard() -> None:
    failures = []
    for chart_type, payloads in PROMPT_OPTIONS.items():
        for i, opts in enumerate(payloads):
            ok, reason = validate_chart_options(chart_type, dict(opts, type=chart_type))
            if not ok:
                failures.append(f"{chart_type}[{i}] {opts}: {reason}")
    assert not failures, "프롬프트가 가르치는 옵션이 가드에서 drop 됨:\n" + "\n".join(failures)


def test_out_of_contract_options_are_rejected() -> None:
    for chart_type, opts in REJECTED_OPTIONS:
        ok, _ = validate_chart_options(chart_type, dict(opts, type=chart_type))
        assert not ok, f"{chart_type} {opts} 가 통과했다 — 옵션 Literal 계약 구멍"


def test_option_guard_is_noop_without_options() -> None:
    """v8.6.0 이전 payload 는 옵션이 없으므로 항상 통과 (additive-by-construction)."""
    for chart_type in PROMPT_SHAPES:
        ok, _ = validate_chart_options(chart_type, {"type": chart_type, "title": "t"})
        assert ok, chart_type
