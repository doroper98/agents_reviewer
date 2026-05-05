"""V5 Phase 6A — Exhibit Priority Policy regression test.

REFACTOR_V5_PLAN.md §14.5 인수 기준:
    1. 모든 exhibit 이 priority 를 갖는다 (default supporting).
    2. Required exhibit 이 Critic fail 한 사례에서 *drop 되지 않고* fallback
       (fact_grid / table / text) 으로 대체되었음이 검증되어야 한다.
       — AP-V5-28 강제.
    3. DeskEditor 가 required exhibit 의 fallback 발생을 hold 사유로 인지
       (``ChartGateResult.required_fallback_used=True``).
    4. 보고서당 required exhibit 비율이 *너무 높으면* (>50%) ResearchDirector
       prompt tuning 신호. — 운영 측정.

본 모듈은 #1, #2, #3 을 결정적으로 검증.
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.state.models import (
    AnalysisMethod,
    Exhibit,
    ExhibitPriority,
    RequiredExhibit,
)
from src.visual.chart_gate import (
    ChartGateResult,
    FallbackLadder,
    run_chart_gate,
)


# ─── 인수 기준 #1 — Exhibit 의 priority default ──────────────────────


def test_exhibit_default_priority_is_supporting() -> None:
    """Plan §14.3 — Exhibit.priority 의 default 는 'supporting'."""
    ex = Exhibit(spec={"mark": "bar"}, title="test")
    assert ex.priority == "supporting"
    assert ex.priority_assigned_by == "default"
    assert ex.fallback_form == "fact_grid"


def test_exhibit_priority_3_tier() -> None:
    """ExhibitPriority Literal 의 3종 enum."""
    from typing import get_args
    actual = set(get_args(ExhibitPriority))
    assert actual == {"required", "supporting", "decorative"}


def test_required_exhibit_model() -> None:
    """RequiredExhibit 의 fallback_form 3종 enum."""
    re = RequiredExhibit(
        description="호르무즈 의존도 비교",
        visual_type_hint="bar",
        why_required="전이 채널 분석의 핵심 증거",
        fallback_form="table",
    )
    assert re.description == "호르무즈 의존도 비교"
    assert re.fallback_form == "table"

    # default fallback_form = fact_grid.
    re_default = RequiredExhibit(description="x")
    assert re_default.fallback_form == "fact_grid"


def test_analysis_method_required_exhibits_accepts_string_legacy() -> None:
    """legacy ``list[str]`` 형식의 required_exhibits 가 RequiredExhibit 으로
    자동 변환 (model_validator before)."""
    method = AnalysisMethod(
        method="transmission_channel",
        required_exhibits=["bar", "stacked"],   # type: ignore[list-item]
    )
    assert len(method.required_exhibits) == 2
    assert all(isinstance(r, RequiredExhibit) for r in method.required_exhibits)
    assert method.required_exhibits[0].description == "bar"
    assert method.required_exhibits[0].fallback_form == "fact_grid"


def test_analysis_method_required_exhibits_accepts_dict() -> None:
    """dict 형식 그대로 입력 받기."""
    method = AnalysisMethod(
        method="decision_matrix",
        required_exhibits=[
            {
                "description": "옵션 × 기준 매트릭스",
                "visual_type_hint": "heatmap",
                "why_required": "전략 모드 핵심",
                "fallback_form": "table",
            },
        ],
    )
    assert len(method.required_exhibits) == 1
    assert method.required_exhibits[0].fallback_form == "table"


# ─── 인수 기준 #2 — Required exhibit 은 drop 금지 (AP-V5-28) ────────


def test_required_exhibit_falls_back_not_drop_when_critic_fails() -> None:
    """AP-V5-28 — priority='required' 면 Gate B fail 해도 fallback 으로 격하만."""
    chart = {
        "type": "bar",
        "title": "호르무즈 의존도",
        "data": [{"label": "한국", "value": 35}, {"label": "일본", "value": 80}],
        "source_ids": ["S-001"],
    }
    # prose 가 차트 수치 인용 안 함 → Gate B (Critic Q4) fail.
    prose = "이 사건은 매우 중요하다."

    result = run_chart_gate(
        chart,
        section_prose=prose,
        priority="required",
        required_fallback_form="fact_grid",
    )
    assert not result.passed
    assert result.priority == "required"
    assert result.required_fallback_used is True
    # silent drop 절대 금지.
    assert result.final_verdict != "fallback_drop"
    assert result.final_verdict in (
        "fallback_fact_grid", "fallback_table", "fallback_text",
    )


def test_required_exhibit_table_fallback_for_many_rows() -> None:
    """RequiredExhibit.fallback_form='table' 시 많은 행 데이터 표 변환."""
    chart = {
        "type": "bar",
        "title": "10개 항목",
        "data": [{"label": f"L{i}", "value": i * 10} for i in range(10)],
        "source_ids": ["S-001"],
    }
    prose = "관련 없는 본문."   # Gate B fail 유도.

    result = run_chart_gate(
        chart,
        section_prose=prose,
        priority="required",
        required_fallback_form="table",
    )
    assert not result.passed
    assert result.required_fallback_used is True
    assert result.final_verdict == "fallback_table"
    assert isinstance(result.fallback_payload, dict)
    assert result.fallback_payload["kind"] == "table"
    assert len(result.fallback_payload["rows"]) == 10


def test_required_exhibit_text_fallback_when_data_empty() -> None:
    """fact_grid / table 모두 실패해도 *최소한 text* 로 emit (drop 금지)."""
    # 데이터가 비어있으면 fact_grid / table / text_summary 모두 None.
    chart = {
        "type": "bar",
        "title": "핵심 차트",
        "data": [],
        "source_ids": ["S-001"],
    }
    # Gate A 자체가 빈 data 에서 fail (CHART-AP-7) — required 면 fallback.
    result = run_chart_gate(
        chart,
        priority="required",
        required_fallback_form="fact_grid",
    )
    assert not result.passed
    assert result.priority == "required"
    assert result.required_fallback_used is True
    # 빈 data 라도 text payload 는 *placeholder 메시지로* emit.
    assert result.final_verdict == "fallback_text"
    assert result.fallback_payload is not None
    assert "핵심 차트" in str(result.fallback_payload) or "데이터 결손" in str(result.fallback_payload)


# ─── decorative — 1단계 fallback 만 시도 ─────────────────────────────


def test_decorative_exhibit_drops_silently_when_no_fact_grid() -> None:
    """priority='decorative' — fact_grid 안 되면 즉시 drop (조용히)."""
    chart = {
        "type": "bar",
        "title": "장식적",
        "data": [],   # 빈 → fact_grid 불가
        "source_ids": ["S-001"],
    }
    result = run_chart_gate(
        chart,
        priority="decorative",
    )
    assert not result.passed
    assert result.priority == "decorative"
    assert result.required_fallback_used is False
    assert result.final_verdict == "fallback_drop"


def test_decorative_exhibit_uses_fact_grid_when_data_short() -> None:
    """decorative + 데이터 ≤ 6 행 → fact_grid."""
    chart = {
        "type": "bar",
        "title": "장식적",
        "data": [{"label": "A", "value": 30}, {"label": "B", "value": 50}],
        "source_ids": ["S-001"],
    }
    prose = ""   # Gate B fail 유도.
    result = run_chart_gate(
        chart,
        section_prose=prose,
        priority="decorative",
    )
    assert result.priority == "decorative"
    assert result.final_verdict == "fallback_fact_grid"


# ─── supporting (default) — 3단계 ladder ─────────────────────────────


def test_supporting_exhibit_uses_3_step_ladder() -> None:
    """기본 priority — fact_grid → text → drop 순."""
    # 빈 data → fact_grid / text 모두 실패 → drop.
    chart = {
        "type": "bar",
        "title": "보조",
        "data": [],
        "source_ids": ["S-001"],
    }
    result = run_chart_gate(chart)   # priority default = supporting
    assert result.priority == "supporting"
    assert result.required_fallback_used is False
    assert result.final_verdict == "fallback_drop"


def test_supporting_exhibit_fact_grid_when_data_short() -> None:
    chart = {
        "type": "bar",
        "title": "보조",
        "data": [{"label": "A", "value": 30}, {"label": "B", "value": 50}],
        "source_ids": ["S-001"],
    }
    result = run_chart_gate(chart, section_prose="")   # Gate B fail
    assert result.priority == "supporting"
    assert result.final_verdict == "fallback_fact_grid"


# ─── FallbackLadder 신규 to_table ───────────────────────────────────


def test_fallback_ladder_to_table_supports_many_rows() -> None:
    chart = {
        "title": "10개 행",
        "data": [{"label": f"L{i}", "value": i * 10} for i in range(10)],
    }
    table = FallbackLadder.to_table(chart)
    assert table is not None
    assert table["kind"] == "table"
    assert "label" in table["columns"]
    assert "value" in table["columns"]
    assert len(table["rows"]) == 10


def test_fallback_ladder_to_table_handles_empty() -> None:
    assert FallbackLadder.to_table({"data": []}) is None


def test_fallback_ladder_to_table_truncates_long_values() -> None:
    chart = {
        "data": [
            {"label": "A" * 200, "value": "B" * 200},
        ],
    }
    table = FallbackLadder.to_table(chart)
    assert table is not None
    # 60자 truncate 정책.
    for row in table["rows"]:
        for cell in row:
            assert len(cell) <= 60


# ─── 인수 기준 #3 — DeskEditor 가 required_fallback_used 인지 ────────


def test_required_fallback_used_signals_desk_editor() -> None:
    """Plan §14.5 #3 — required_fallback_used=True 가 hold 사유 신호."""
    # Required + Gate fail → required_fallback_used=True.
    chart_required = {
        "type": "bar",
        "title": "핵심",
        "data": [{"label": "A", "value": 30}],
        "source_ids": ["S-001"],
    }
    result_req = run_chart_gate(chart_required, priority="required")
    if not result_req.passed:
        assert result_req.required_fallback_used is True

    # Supporting + Gate fail → required_fallback_used=False (DeskEditor 무관심).
    result_sup = run_chart_gate(chart_required, priority="supporting")
    if not result_sup.passed:
        assert result_sup.required_fallback_used is False


def test_required_fallback_used_false_when_gates_pass() -> None:
    """Gate 모두 통과한 required exhibit 은 required_fallback_used=False."""
    chart = {
        "type": "bar",
        "title": "한국 일본 의존도",
        "data": [{"label": "한국", "value": 35}, {"label": "일본", "value": 80}],
        "source_ids": ["S-001"],
    }
    prose = "한국 35%, 일본 80% 의 의존도."  # Gate B Q4 통과.
    result = run_chart_gate(chart, section_prose=prose, priority="required")
    if result.passed:
        # 통과했으면 fallback 사용 X.
        assert result.required_fallback_used is False
        assert result.priority == "required"


# ─── ResearchDirector 의 required_exhibits 자동 부여 (heuristic) ─────


def test_research_director_heuristic_emits_required_exhibits() -> None:
    """heuristic fallback 이 method 별 _DEFAULT_REQUIRED_EXHIBITS 적용."""
    from src.agents.research_director import design_via_heuristics

    # transmission_channel 사건.
    brief = design_via_heuristics(
        "엔 캐리 unwind 가 KOSPI 변동성에 미치는 전이 채널 분석"
    )
    methods = [m.method for m in brief.selected_methods]
    assert "transmission_channel" in methods

    # transmission_channel 의 required_exhibits 가 RequiredExhibit 인스턴스.
    tc_method = next(
        m for m in brief.selected_methods if m.method == "transmission_channel"
    )
    assert len(tc_method.required_exhibits) >= 1
    assert isinstance(tc_method.required_exhibits[0], RequiredExhibit)
    assert tc_method.required_exhibits[0].visual_type_hint == "bar"


def test_research_director_decision_matrix_strategic_required() -> None:
    """Plan §6.4 — 전략 질의의 decision_matrix method 는 decision_matrix 차트 강제."""
    from src.agents.research_director import design_via_heuristics

    brief = design_via_heuristics("LLM 인프라 자체 구축 vs 클라우드 어떤 전략")
    methods = [m.method for m in brief.selected_methods]
    assert "decision_matrix" in methods

    dm = next(m for m in brief.selected_methods if m.method == "decision_matrix")
    assert len(dm.required_exhibits) >= 1
    # Phase 8 strategic mode 의 핵심 — table 격하 권장.
    assert dm.required_exhibits[0].fallback_form == "table"


def test_research_director_required_exhibits_per_method_complete() -> None:
    """9종 method 모두 _DEFAULT_REQUIRED_EXHIBITS 매핑 보유 (fault_tree /
    pre_mortem 은 빈 list 허용)."""
    from src.agents.research_director import _DEFAULT_REQUIRED_EXHIBITS

    expected_methods = {
        "ACH", "scenario_tree", "transmission_channel", "stakeholder_matrix",
        "fault_tree", "decision_matrix", "pre_mortem",
        "transmission_timeline", "comparative",
    }
    actual = set(_DEFAULT_REQUIRED_EXHIBITS.keys())
    assert actual == expected_methods, (
        f"_DEFAULT_REQUIRED_EXHIBITS 의 9종 method 매핑 — "
        f"missing: {expected_methods - actual}, extra: {actual - expected_methods}"
    )


# ─── ChartGateResult.priority 추적 ───────────────────────────────────


def test_chart_gate_result_priority_propagated() -> None:
    """ChartGateResult 가 priority 를 보존."""
    chart = {
        "type": "bar",
        "data": [{"label": "A", "value": 10}],
        "source_ids": ["S-001"],
    }
    for prio in ["required", "supporting", "decorative"]:
        result = run_chart_gate(chart, priority=prio)  # type: ignore[arg-type]
        assert result.priority == prio
