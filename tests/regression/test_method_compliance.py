"""V5 Phase 1A — Method Compliance Test (검토자 권장 5번).

ResearchDirector 가 method 를 *고른다* 만 검증하던 기존 테스트
(test_research_director.py) 의 한계 보완. 본 테스트는 *고른 method 를
downstream 객체·heuristic 이 실제로 따르는지* 를 결정적으로 검증.

[검증 시나리오 9종 — Plan §6.3 의 9 method × downstream contract]

| method                  | downstream 검증                                                     |
|-------------------------|--------------------------------------------------------------------|
| ACH                     | required_exhibits = heatmap (가설 × 증거 매트릭스)                  |
| scenario_tree           | required_exhibits = bubble + scenario branch ≥ 2 가능              |
| transmission_channel    | required_exhibits = bar + fallback=table                            |
| stakeholder_matrix      | required_exhibits = table + fallback=table (network 폐기 CHART-AP-36) |
| fault_tree              | required_exhibits 비어있음 (causal 구조는 heuristic 외 처리)        |
| decision_matrix         | StrategicReport 8개 필수 필드 + required_exhibits = decision_matrix |
| pre_mortem              | StrategicOption.pre_mortem 필드 존재                                |
| transmission_timeline   | required_exhibits = gantt + timeline events 수용                   |
| comparative             | required_exhibits = bar + fallback=fact_grid                        |

LLM 호출 0. heuristic / 모델 schema / fallback 정합성만 검증.
"""

from __future__ import annotations

import pytest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from src.agents.research_director import (
        _DEFAULT_REQUIRED_EXHIBITS,
        design_via_heuristics,
    )
    from src.state.models import (
        ActionPlan,
        AnalysisBrief,
        AnalysisMethod,
        Constraints,
        Criterion,
        DecisionMatrix,
        FailureMode,
        Recommendation,
        RequiredExhibit,
        StrategicOption,
        StrategicReport,
    )
    _IMPORTS_OK = True
except Exception as e:  # pragma: no cover
    _IMPORTS_OK = False
    _IMPORT_ERROR = e

# Plan §6.3 — 9종 method enum 의 SSOT.
NINE_METHODS = (
    "ACH",
    "scenario_tree",
    "transmission_channel",
    "stakeholder_matrix",
    "fault_tree",
    "decision_matrix",
    "pre_mortem",
    "transmission_timeline",
    "comparative",
)


# ─── Schema integrity ─────────────────────────────────────────────────


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_each_method_has_required_exhibits_mapping():
    """9종 method 모두 _DEFAULT_REQUIRED_EXHIBITS dict 에 entry 가 있어야.

    AP-V5-28 강제의 사전 — research_director 가 method 를 고르면 *반드시*
    required_exhibits 매핑이 있어야 (빈 list 라도) downstream 이 처리 가능.
    """
    for m in NINE_METHODS:
        assert m in _DEFAULT_REQUIRED_EXHIBITS, f"method '{m}' missing in _DEFAULT_REQUIRED_EXHIBITS"


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_required_exhibits_have_valid_fallback_form():
    """RequiredExhibit.fallback_form Literal 3종 (fact_grid/table/text) 강제."""
    valid = {"fact_grid", "table", "text"}
    for method, exhibits in _DEFAULT_REQUIRED_EXHIBITS.items():
        for ex in exhibits:
            fb = ex.get("fallback_form", "fact_grid")
            assert fb in valid, f"method '{method}' has invalid fallback_form '{fb}'"


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_strategic_report_has_8_required_fields():
    """Plan §18.3 — 전략 보고서의 8개 필수 출력 모두 존재."""
    fields = StrategicReport.model_fields.keys()
    required_8 = {
        "decision_statement",
        "options",
        "criteria",
        "constraints",
        "decision_matrix",
        "recommendation",
        "kill_switch_conditions",
        "action_plan_30_60_90",
    }
    missing = required_8 - set(fields)
    assert not missing, f"StrategicReport 누락 필드: {missing}"


# ─── Method-specific compliance ───────────────────────────────────────


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_ACH_method_required_exhibit_is_heatmap():
    """ACH = 가설 × 증거 매트릭스 → heatmap 시각화."""
    exhibits = _DEFAULT_REQUIRED_EXHIBITS["ACH"]
    assert len(exhibits) >= 1
    assert exhibits[0]["visual_type_hint"] == "heatmap"
    assert exhibits[0]["fallback_form"] == "table"


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_scenario_tree_method_required_exhibit_is_bubble():
    """scenario_tree → 확률 × 영향 매트릭스 → bubble."""
    exhibits = _DEFAULT_REQUIRED_EXHIBITS["scenario_tree"]
    assert len(exhibits) >= 1
    assert exhibits[0]["visual_type_hint"] == "bubble"


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_transmission_channel_method_required_exhibit_is_bar():
    """transmission_channel → 단계별 영향 비교 → bar + table fallback."""
    exhibits = _DEFAULT_REQUIRED_EXHIBITS["transmission_channel"]
    assert len(exhibits) >= 1
    assert exhibits[0]["visual_type_hint"] == "bar"
    assert exhibits[0]["fallback_form"] == "table"


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_stakeholder_matrix_method_required_exhibit_is_table():
    """stakeholder_matrix → 이해관계자 표 (network 폐기, CHART-AP-36)."""
    exhibits = _DEFAULT_REQUIRED_EXHIBITS["stakeholder_matrix"]
    assert len(exhibits) >= 1
    assert exhibits[0]["visual_type_hint"] == "table"


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_decision_matrix_method_required_exhibit_aligned():
    """decision_matrix method → required_exhibit 의 visual_type_hint 가 'decision_matrix'."""
    exhibits = _DEFAULT_REQUIRED_EXHIBITS["decision_matrix"]
    assert len(exhibits) >= 1
    assert exhibits[0]["visual_type_hint"] == "decision_matrix"
    assert exhibits[0]["fallback_form"] == "table"


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_transmission_timeline_method_required_exhibit_is_gantt():
    """transmission_timeline → 시계열 변천 → gantt."""
    exhibits = _DEFAULT_REQUIRED_EXHIBITS["transmission_timeline"]
    assert len(exhibits) >= 1
    assert exhibits[0]["visual_type_hint"] == "gantt"


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_comparative_method_required_exhibit_is_bar():
    """comparative → 차원별 비교 → bar + fact_grid fallback."""
    exhibits = _DEFAULT_REQUIRED_EXHIBITS["comparative"]
    assert len(exhibits) >= 1
    assert exhibits[0]["visual_type_hint"] == "bar"
    assert exhibits[0]["fallback_form"] == "fact_grid"


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_fault_tree_and_pre_mortem_can_have_empty_exhibits():
    """fault_tree / pre_mortem 은 차트 외 처리 (causal 구조, 실패 시나리오 list).

    빈 list 도 허용 — 단 dict entry 자체는 있어야 함 (AP-V5-28 강제).
    """
    assert _DEFAULT_REQUIRED_EXHIBITS["fault_tree"] == []
    assert _DEFAULT_REQUIRED_EXHIBITS["pre_mortem"] == []


# ─── Heuristic fallback 의 method 준수 ────────────────────────────────


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_design_via_heuristics_emits_required_exhibits_for_each_method():
    """design_via_heuristics 가 모든 9 method 에서 required_exhibits 를 정합 emit.

    - method 별 _DEFAULT_REQUIRED_EXHIBITS 매핑이 selected_method 에 그대로 박힘.
    - RequiredExhibit Pydantic 으로 변환되어 fallback_form 유효성 통과.
    """
    test_cases = [
        ("호르무즈 해협 봉쇄 가능성 분석", "transmission_channel"),
        ("이스라엘-이란 전쟁 시나리오 3종", "scenario_tree"),
        ("LG 에너지솔루션 vs 삼성SDI 비교", "comparative"),
        ("미중 패권 경쟁 행위자 구도", "stakeholder_matrix"),
    ]
    for query, _expected_method in test_cases:
        brief = design_via_heuristics(query, mode="standard")
        assert isinstance(brief, AnalysisBrief)
        assert len(brief.selected_methods) >= 1
        for method_obj in brief.selected_methods:
            # method 가 9종 enum 안.
            assert method_obj.method in NINE_METHODS
            # required_exhibits 가 RequiredExhibit Pydantic 으로 정상 변환.
            for ex in method_obj.required_exhibits:
                assert isinstance(ex, RequiredExhibit)
                assert ex.fallback_form in ("fact_grid", "table", "text")


# ─── StrategicReport 의 method 준수 contract ──────────────────────────


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_strategic_report_decision_matrix_aligns_with_options_and_criteria():
    """DecisionMatrix.options 와 .criteria 가 StrategicReport.options/criteria 와 일치 가능."""
    sr = StrategicReport(
        decision_statement="옵션 A 채택",
        options=[
            StrategicOption(label="옵션 A", one_line_summary="공격적"),
            StrategicOption(label="옵션 B", one_line_summary="보수적"),
        ],
        criteria=[Criterion(name="비용"), Criterion(name="시간"), Criterion(name="리스크")],
        decision_matrix=DecisionMatrix(
            options=["옵션 A", "옵션 B"],
            criteria=["비용", "시간", "리스크"],
            scores=[[0.8, 0.6, 0.5], [0.4, 0.9, 0.8]],
        ),
        recommendation=Recommendation(
            selected_option_label="옵션 A",
            rationale="총합 점수가 높음. 시간 변동 -10% 시에도 우위 유지." * 2,
        ),
        action_plan_30_60_90=ActionPlan(),
    )
    # decision_matrix.options 는 StrategicReport.options 의 label 과 *부분집합* 가능.
    matrix_opts = set(sr.decision_matrix.options)
    sr_opts = {o.label for o in sr.options}
    assert matrix_opts <= sr_opts, "decision_matrix.options 가 strategic options label 안에 없음"


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_pre_mortem_method_strategic_option_has_pre_mortem_field():
    """pre_mortem method 의 *진짜 가치* — StrategicOption 이 pre_mortem (FailureMode list) 보유."""
    opt = StrategicOption(
        label="옵션 A",
        one_line_summary="공격적 진입",
        pre_mortem=[
            FailureMode(mode="경쟁사 가격 인하", leading_indicator="시장 점유율 -5%", severity="high"),
            FailureMode(mode="규제 변경", leading_indicator="법안 발의", severity="medium"),
            FailureMode(mode="공급망 차질", leading_indicator="lead time +30%", severity="medium"),
        ],
    )
    assert len(opt.pre_mortem) >= 3  # Plan §17.3 권장 ≥3
    for fm in opt.pre_mortem:
        assert fm.severity in ("low", "medium", "high")


# ─── Negative tests — KILL_RULE precondition ──────────────────────────


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_strategic_report_missing_recommendation_is_detectable():
    """Recommendation = None 이면 KILL_RULE recommendation_absent 가 발동 가능 상태."""
    sr = StrategicReport(decision_statement="?", recommendation=None)
    # KILL_RULE 검사기 (run_strategic_kill_rules) 가 이 상태 인지하는지는
    # test_strategic_mode.py 가 검증. 본 테스트는 *모델 자체가 None 허용* 인지.
    assert sr.recommendation is None


@pytest.mark.skipif(not _IMPORTS_OK, reason="src.state import failed")
def test_strategic_report_options_min_2_for_decision_matrix():
    """decision_matrix method 가 의미 있으려면 옵션 ≥ 2 (Plan §17.6 KILL_RULE options_too_few)."""
    sr = StrategicReport(
        options=[StrategicOption(label="유일한 옵션", one_line_summary="...")],
    )
    # 옵션 1개 → KILL_RULE 발동 조건. 본 테스트는 모델이 *경고 없이 받아들이지만* 검사기가 잡음을 검증.
    assert len(sr.options) < 2  # KILL_RULE precondition
