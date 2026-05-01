"""PR3/PR4 (v3.4.6/v3.4.7) tests — AMC + Narrative DSL.

Run:
    python -m pytest src/tests/test_amc_narrative_dsl.py -v
"""

from __future__ import annotations

import pytest

from src.archetypes import get_archetype
from src.archetypes.accident_forensic import ARCHETYPE as ACCIDENT_FORENSIC
from src.archetypes.base import default_contract
from src.archetypes.decision_brief import ARCHETYPE as DECISION_BRIEF
from src.archetypes.financial_transmission import ARCHETYPE as FINANCIAL_TRANSMISSION
from src.archetypes.freeform_essay import ARCHETYPE as FREEFORM_ESSAY
from src.archetypes.geopolitical_strategic import ARCHETYPE as GEOPOLITICAL_STRATEGIC
from src.archetypes.industry_value_chain import ARCHETYPE as INDUSTRY_VALUE_CHAIN
from src.archetypes.mechanism_decomp import ARCHETYPE as MECHANISM_DECOMP
from src.archetypes.policy_implementation import ARCHETYPE as POLICY_IMPLEMENTATION
from src.archetypes.scenario_first import ARCHETYPE as SCENARIO_FIRST
from src.archetypes.six_act_theater import ARCHETYPE as SIX_ACT_THEATER
from src.archetypes.tech_decomposition import ARCHETYPE as TECH_DECOMPOSITION
from src.archetypes.timeline_first import ARCHETYPE as TIMELINE_FIRST
from src.models import (
    AnalysisMethodContract,
    AnalysisRequest,
    AnalysisStrategy,
    ContextAnalysis,
    FullAnalysisResult,
    NarrativeStage,
    PlayerAnalysis,
    ReportSectionPlan,
    ScenarioAnalysis,
)


def _empty_result(**kwargs) -> FullAnalysisResult:
    """FullAnalysisResult 는 request 가 필수. 테스트용 helper."""
    return FullAnalysisResult(
        request=AnalysisRequest(event_description="test"),
        **kwargs,
    )


# 11개 archetype + freeform = 12개. 강한 contract 검증 대상은 freeform 제외 11개.
ALL_ARCHETYPES = [
    SCENARIO_FIRST, DECISION_BRIEF, MECHANISM_DECOMP, ACCIDENT_FORENSIC,
    FINANCIAL_TRANSMISSION, GEOPOLITICAL_STRATEGIC, INDUSTRY_VALUE_CHAIN,
    POLICY_IMPLEMENTATION, TECH_DECOMPOSITION, TIMELINE_FIRST, SIX_ACT_THEATER,
]
STRICT_ARCHETYPES = [a for a in ALL_ARCHETYPES if a.archetype_id != "freeform_essay"]


# ----------------------------------------------------------------------
# 1. NarrativeStage Literal + ReportSectionPlan extension
# ----------------------------------------------------------------------


class TestNarrativeStageField:
    def test_section_plan_accepts_stage(self) -> None:
        plan = ReportSectionPlan(
            section_id="s1", title="t", narrative_stage="fact",
        )
        assert plan.narrative_stage == "fact"

    def test_section_plan_stage_optional(self) -> None:
        plan = ReportSectionPlan(section_id="s1", title="t")
        assert plan.narrative_stage is None

    def test_section_plan_rejects_invalid_stage(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ReportSectionPlan(
                section_id="s1", title="t", narrative_stage="invalid_stage",  # type: ignore
            )

    def test_all_5_stages_valid(self) -> None:
        for stage in ("fact", "mechanism", "divergence", "decision", "trigger"):
            plan = ReportSectionPlan(section_id="s", title="t", narrative_stage=stage)
            assert plan.narrative_stage == stage


# ----------------------------------------------------------------------
# 2. AnalysisMethodContract model
# ----------------------------------------------------------------------


class TestAnalysisMethodContract:
    def test_minimal_contract(self) -> None:
        c = AnalysisMethodContract(method_id="x")
        assert c.method_id == "x"
        assert c.required_inputs == []
        assert c.mandatory_stages == []
        assert c.forbidden_blocks == []

    def test_full_contract(self) -> None:
        c = AnalysisMethodContract(
            method_id="decision_brief",
            required_inputs=["judgment"],
            mandatory_stages=["fact", "decision"],
            forbidden_blocks=["scenario_table"],
            rationale="결정 브리프",
        )
        assert c.mandatory_stages == ["fact", "decision"]
        assert c.forbidden_blocks == ["scenario_table"]

    def test_default_contract_helper(self) -> None:
        c = default_contract("xyz")
        assert c.method_id == "xyz"
        assert c.mandatory_stages == []
        assert c.forbidden_blocks == []


# ----------------------------------------------------------------------
# 3. Archetype contracts — 5개 archetype 이 contract() 선언
# ----------------------------------------------------------------------


class TestArchetypeContracts:
    """PR3-B: 5개 archetype 이 contract() 메서드를 선언함."""

    def test_scenario_first_contract(self) -> None:
        c = SCENARIO_FIRST.contract()
        assert c.method_id == "scenario_first"
        assert "fact" in c.mandatory_stages
        assert "divergence" in c.mandatory_stages
        assert "trigger" in c.mandatory_stages
        assert "decision_matrix" in c.forbidden_blocks

    def test_decision_brief_contract(self) -> None:
        c = DECISION_BRIEF.contract()
        assert c.method_id == "decision_brief"
        assert "decision" in c.mandatory_stages
        assert "trigger" in c.mandatory_stages

    def test_mechanism_decomp_contract(self) -> None:
        c = MECHANISM_DECOMP.contract()
        assert c.method_id == "mechanism_decomp"
        assert "mechanism" in c.mandatory_stages
        # mechanism_decomp 는 미래 시나리오 금지
        assert "scenario_table" in c.forbidden_blocks

    def test_accident_forensic_contract(self) -> None:
        c = ACCIDENT_FORENSIC.contract()
        assert "fact" in c.mandatory_stages
        assert "decision" in c.mandatory_stages

    def test_financial_transmission_contract(self) -> None:
        c = FINANCIAL_TRANSMISSION.contract()
        assert c.method_id == "financial_transmission"
        assert "trigger" in c.mandatory_stages


# ----------------------------------------------------------------------
# 4. Section plans 가 narrative_stage 태깅됨
# ----------------------------------------------------------------------


@pytest.fixture
def sample_strategy() -> AnalysisStrategy:
    return AnalysisStrategy(
        event_type="test",
        user_intent="what_next",
        intent_confidence=0.8,
        core_questions=["q1"],
        recommended_lenses=["red_team"],
    )


class TestArchetypeStageCoverage:
    """각 archetype 의 section_plan 이 자기 contract 의 mandatory_stages 를 모두
    커버하는지 검증. 이게 깨지면 archetype 작성 자체가 잘못된 것.

    PR4: 11개 strict archetype (freeform 제외) 전체 검증으로 확장.
    """

    @pytest.mark.parametrize("archetype", STRICT_ARCHETYPES, ids=lambda a: a.archetype_id)
    def test_archetype_covers_mandatory_stages(self, archetype, sample_strategy) -> None:
        contract = archetype.contract()
        if not contract.mandatory_stages:
            pytest.skip(f"{archetype.archetype_id}: no mandatory_stages declared")
        plan = archetype.section_plan(sample_strategy)
        stages = {s.narrative_stage for s in plan if s.narrative_stage}
        for required in contract.mandatory_stages:
            assert required in stages, (
                f"{archetype.archetype_id} 의 section_plan 이 mandatory stage "
                f"{required!r} 를 커버하지 않음. 현재 stages: {sorted(stages)}"
            )

    def test_freeform_essay_has_loose_contract(self, sample_strategy) -> None:
        # freeform_essay 는 composer 가 stage 자율 결정 → mandatory_stages 비어있어야 함.
        contract = FREEFORM_ESSAY.contract()
        assert contract.mandatory_stages == []
        # section_plan 도 빈 list (composer 가 SSOT)
        assert FREEFORM_ESSAY.section_plan(sample_strategy) == []


# ----------------------------------------------------------------------
# 5. forbidden_blocks 가 자기 section_plan 안에 들어있지 않음 (자가 모순 방지)
# ----------------------------------------------------------------------


class TestArchetypeNoSelfViolation:
    """PR4: 11개 strict archetype 전체에 대해 자가 모순 검증."""

    @pytest.mark.parametrize("archetype", STRICT_ARCHETYPES, ids=lambda a: a.archetype_id)
    def test_archetype_does_not_request_forbidden(self, archetype, sample_strategy) -> None:
        contract = archetype.contract()
        if not contract.forbidden_blocks:
            pytest.skip(f"{archetype.archetype_id}: no forbidden_blocks declared")
        plan = archetype.section_plan(sample_strategy)
        all_blocks = {bt for s in plan for bt in s.block_types}
        for forbidden in contract.forbidden_blocks:
            assert forbidden not in all_blocks, (
                f"{archetype.archetype_id} 가 자기 forbidden_blocks 의 {forbidden!r} 를 요청 — 자가 모순"
            )


# ----------------------------------------------------------------------
# 6. 모든 archetype 이 contract() 메서드를 노출
# ----------------------------------------------------------------------


class TestAllArchetypesHaveContract:
    """PR4: 모든 archetype 에 contract() 가 있는지 + AnalysisMethodContract 인스턴스 반환."""

    @pytest.mark.parametrize("archetype", ALL_ARCHETYPES, ids=lambda a: a.archetype_id)
    def test_archetype_has_callable_contract(self, archetype) -> None:
        assert hasattr(archetype, "contract"), (
            f"{archetype.archetype_id} 에 contract() 메서드 부재"
        )
        c = archetype.contract()
        assert isinstance(c, AnalysisMethodContract)
        assert c.method_id == archetype.archetype_id


# ----------------------------------------------------------------------
# 7. Synthesizer required_inputs 검증 (PR4)
# ----------------------------------------------------------------------


class TestRequiredInputsCheck:
    """PR4: ReportSynthesizer._check_required_inputs 동작 검증."""

    def test_missing_when_none(self) -> None:
        from src.agents.report_synthesizer import ReportSynthesizer
        result = _empty_result()  # 모든 분석 필드 None
        missing = ReportSynthesizer._check_required_inputs(
            result, ["context", "scenarios"],
        )
        assert "context" in missing
        assert "scenarios" in missing

    def test_missing_when_empty_pydantic_model(self) -> None:
        from src.agents.report_synthesizer import ReportSynthesizer
        # ScenarioAnalysis() 인스턴스이지만 모든 list 필드 비어있음
        result = _empty_result(scenarios=ScenarioAnalysis())
        missing = ReportSynthesizer._check_required_inputs(result, ["scenarios"])
        assert "scenarios" in missing

    def test_present_when_pydantic_has_data(self) -> None:
        from src.agents.report_synthesizer import ReportSynthesizer
        result = _empty_result(
            scenarios=ScenarioAnalysis(scenarios=[{"name": "S1"}]),
        )
        missing = ReportSynthesizer._check_required_inputs(result, ["scenarios"])
        assert missing == []

    def test_partial_missing(self) -> None:
        from src.agents.report_synthesizer import ReportSynthesizer
        result = _empty_result(
            context=ContextAnalysis(event_name="x"),
        )
        missing = ReportSynthesizer._check_required_inputs(
            result, ["context", "players"],
        )
        assert "context" not in missing
        assert "players" in missing
