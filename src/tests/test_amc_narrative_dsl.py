"""PR3 (v3.4.6) tests — AMC + Narrative DSL.

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
from src.archetypes.mechanism_decomp import ARCHETYPE as MECHANISM_DECOMP
from src.archetypes.scenario_first import ARCHETYPE as SCENARIO_FIRST
from src.models import (
    AnalysisMethodContract,
    AnalysisStrategy,
    NarrativeStage,
    ReportSectionPlan,
)


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
    커버하는지 검증. 이게 깨지면 archetype 작성 자체가 잘못된 것."""

    def test_scenario_first_covers_mandatory(self, sample_strategy) -> None:
        plan = SCENARIO_FIRST.section_plan(sample_strategy)
        stages = {s.narrative_stage for s in plan if s.narrative_stage}
        for required in SCENARIO_FIRST.contract().mandatory_stages:
            assert required in stages, (
                f"scenario_first archetype 의 section_plan 이 mandatory stage "
                f"{required!r} 를 커버하지 않음"
            )

    def test_decision_brief_covers_mandatory(self, sample_strategy) -> None:
        plan = DECISION_BRIEF.section_plan(sample_strategy)
        stages = {s.narrative_stage for s in plan if s.narrative_stage}
        for required in DECISION_BRIEF.contract().mandatory_stages:
            assert required in stages

    def test_mechanism_decomp_covers_mandatory(self, sample_strategy) -> None:
        plan = MECHANISM_DECOMP.section_plan(sample_strategy)
        stages = {s.narrative_stage for s in plan if s.narrative_stage}
        for required in MECHANISM_DECOMP.contract().mandatory_stages:
            assert required in stages

    def test_accident_forensic_covers_mandatory(self, sample_strategy) -> None:
        plan = ACCIDENT_FORENSIC.section_plan(sample_strategy)
        stages = {s.narrative_stage for s in plan if s.narrative_stage}
        for required in ACCIDENT_FORENSIC.contract().mandatory_stages:
            assert required in stages

    def test_financial_transmission_covers_mandatory(self, sample_strategy) -> None:
        plan = FINANCIAL_TRANSMISSION.section_plan(sample_strategy)
        stages = {s.narrative_stage for s in plan if s.narrative_stage}
        for required in FINANCIAL_TRANSMISSION.contract().mandatory_stages:
            assert required in stages


# ----------------------------------------------------------------------
# 5. forbidden_blocks 가 자기 section_plan 안에 들어있지 않음 (자가 모순 방지)
# ----------------------------------------------------------------------


class TestArchetypeNoSelfViolation:
    def test_scenario_first_does_not_request_forbidden(self, sample_strategy) -> None:
        plan = SCENARIO_FIRST.section_plan(sample_strategy)
        all_blocks = {bt for s in plan for bt in s.block_types}
        for forbidden in SCENARIO_FIRST.contract().forbidden_blocks:
            assert forbidden not in all_blocks, (
                f"scenario_first 가 자기 forbidden_blocks 의 {forbidden!r} 를 요청"
            )

    def test_mechanism_decomp_does_not_request_forbidden(self, sample_strategy) -> None:
        plan = MECHANISM_DECOMP.section_plan(sample_strategy)
        all_blocks = {bt for s in plan for bt in s.block_types}
        for forbidden in MECHANISM_DECOMP.contract().forbidden_blocks:
            assert forbidden not in all_blocks
