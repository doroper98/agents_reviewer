"""Unit tests for V3 Step 4 — Quality Gates + Claim/Evidence + Synthesis Judge.

Run:
    python -m pytest src/tests/test_quality_gates.py -v
"""

from __future__ import annotations

import asyncio

import pydantic
import pytest

from src.models import (
    AnalysisStrategy,
    AnalyticalFinding,
    Claim,
    ConfidenceProfile,
    Evidence,
    JudgmentVerdict,
)


# ----------------------------------------------------------------------
# Claim validator (Anti-pattern #4)
# ----------------------------------------------------------------------


class TestClaimEvidenceContract:
    def test_empty_evidence_ids_raises(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            Claim(
                claim_id="C-1", statement="x", claim_type="fact",
                evidence_ids=[],
            )

    def test_single_evidence_id_passes(self) -> None:
        c = Claim(
            claim_id="C-1", statement="x", claim_type="fact",
            evidence_ids=["E-1"],
        )
        assert c.evidence_ids == ["E-1"]

    def test_evidence_smoke(self) -> None:
        e = Evidence(
            evidence_id="E-1", source_url="https://x", quote_or_data="q",
            reliability="primary", timestamp="2026",
        )
        assert e.evidence_id == "E-1"
        assert e.reliability == "primary"


# ----------------------------------------------------------------------
# ConfidenceProfile (Anti-pattern #10 — 3-axis decomposition)
# ----------------------------------------------------------------------


class TestConfidenceProfile:
    def test_aggregate_weighted_average(self) -> None:
        cp = ConfidenceProfile(
            source_diversity=1.0, data_freshness=0.5, expert_consensus=0.0,
        )
        # 0.4*1.0 + 0.3*0.5 + 0.3*0.0 = 0.55
        assert abs(cp.aggregate - 0.55) < 1e-9

    def test_aggregate_all_max(self) -> None:
        cp = ConfidenceProfile(
            source_diversity=1.0, data_freshness=1.0, expert_consensus=1.0,
        )
        assert abs(cp.aggregate - 1.0) < 1e-9

    def test_axis_bounds_enforced(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            ConfidenceProfile(source_diversity=1.5, data_freshness=0.5, expert_consensus=0.5)


# ----------------------------------------------------------------------
# Quality Gate 1 — Plan Sanity heuristics
# ----------------------------------------------------------------------


def _make_strategy(
    core_questions: list[str] | None = None,
    recommended_lenses: list[str] | None = None,
) -> AnalysisStrategy:
    return AnalysisStrategy(
        event_type="test",
        user_intent="what_happened",
        intent_confidence=0.9,
        core_questions=core_questions or ["사건의 핵심 사실?"],
        recommended_lenses=recommended_lenses or ["context"],
        evidence_plan=[],
        report_archetype="six_act_theater",
        section_plan=[],
        visualization_plan=[],
    )


def _make_inspector():
    """Build a QualityInspector with a stub config."""
    from src.agents.quality_inspector import QualityInspector

    class _Cfg:
        use_cli_mode = False  # disables LLM-as-judge → heuristic-only fast path
        model_name = "claude-opus-4-6"
        model_name_light = "claude-sonnet-4-6"
        anthropic_api_key = ""

    return QualityInspector(_Cfg())  # type: ignore[arg-type]


class TestGate1PlanSanity:
    def test_pass_minimal_strategy(self) -> None:
        insp = _make_inspector()
        passed, _ = asyncio.run(insp.gate_1_plan_sanity(_make_strategy()))
        assert passed is True

    def test_fail_strategy_none(self) -> None:
        insp = _make_inspector()
        passed, reason = asyncio.run(insp.gate_1_plan_sanity(None))
        assert passed is False
        assert "None" in reason

    def test_fail_short_question(self) -> None:
        insp = _make_inspector()
        # min_length=1 lets it construct, but heuristic flags too-short ones.
        s = _make_strategy(core_questions=["x"])
        passed, reason = asyncio.run(insp.gate_1_plan_sanity(s))
        assert passed is False
        assert "core_question" in reason


# ----------------------------------------------------------------------
# Quality Gate 2 — Coverage Check heuristics
# ----------------------------------------------------------------------


def _make_finding(
    lens_id: str, question: str, statement: str = "valid statement",
    counter: str = "valid counter",
) -> AnalyticalFinding:
    ev = Evidence(
        evidence_id="E-1", source_url="", quote_or_data="q",
        reliability="secondary", timestamp="2026-01-01",
    )
    cl = Claim(
        claim_id=f"C-{lens_id}-1", statement=statement,
        claim_type="inference", evidence_ids=["E-1"],
    )
    return AnalyticalFinding(
        finding_id=f"F-{lens_id}-1", lens_id=lens_id,
        answers_question=question, main_claim=cl, evidence=[ev],
        confidence=ConfidenceProfile(
            source_diversity=0.6, data_freshness=0.7, expert_consensus=0.7,
        ),
        counter_hypothesis=counter,
    )


def _make_judgment(
    contradictions: list[dict] | None = None,
    main_judgment: str = "종합 판단",
    counter_hypothesis: str = "반대 가설",
) -> JudgmentVerdict:
    return JudgmentVerdict(
        main_judgment=main_judgment,
        base_scenario="기준",
        biggest_uncertainty="X",
        contradictions=contradictions or [],
        counter_hypothesis=counter_hypothesis,
        counter_evidence_needed=[],
        confidence=ConfidenceProfile(
            source_diversity=0.5, data_freshness=0.5, expert_consensus=0.5,
        ),
    )


class TestGate2Coverage:
    def test_pass_when_all_questions_answered(self) -> None:
        insp = _make_inspector()
        s = _make_strategy(core_questions=["Q1", "Q2"])
        findings = [_make_finding("a", "Q1"), _make_finding("b", "Q2")]
        passed, _ = asyncio.run(
            insp.gate_2_coverage_check(s, findings, _make_judgment()),
        )
        assert passed is True

    def test_fail_when_question_unanswered(self) -> None:
        insp = _make_inspector()
        s = _make_strategy(core_questions=["Q1", "Q2"])
        findings = [_make_finding("a", "Q1")]  # Q2 unanswered
        passed, reason = asyncio.run(
            insp.gate_2_coverage_check(s, findings, _make_judgment()),
        )
        assert passed is False
        assert "미답변" in reason

    def test_fail_when_judgment_missing(self) -> None:
        insp = _make_inspector()
        s = _make_strategy()
        passed, reason = asyncio.run(
            insp.gate_2_coverage_check(s, [_make_finding("a", "사건의 핵심 사실?")], None),
        )
        assert passed is False
        assert "judgment" in reason

    def test_fail_when_main_judgment_blank(self) -> None:
        insp = _make_inspector()
        s = _make_strategy()
        passed, reason = asyncio.run(
            insp.gate_2_coverage_check(
                s, [_make_finding("a", "사건의 핵심 사실?")],
                _make_judgment(main_judgment=""),
            )
        )
        assert passed is False
        assert "main_judgment" in reason

    def test_fail_when_counter_hypothesis_blank(self) -> None:
        insp = _make_inspector()
        s = _make_strategy()
        passed, reason = asyncio.run(
            insp.gate_2_coverage_check(
                s, [_make_finding("a", "사건의 핵심 사실?")],
                _make_judgment(counter_hypothesis=""),
            )
        )
        assert passed is False
        assert "counter_hypothesis" in reason


# ----------------------------------------------------------------------
# Synthesis Judge — Anti-pattern #5 (모순 봉합 금지)
# ----------------------------------------------------------------------


def _make_judge():
    from src.agents.synthesis_judge import SynthesisJudge

    class _Cfg:
        use_cli_mode = False  # disables LLM call → heuristic synth path
        model_name = "claude-opus-4-6"
        model_name_light = "claude-sonnet-4-6"
        anthropic_api_key = ""

    return SynthesisJudge(_Cfg())  # type: ignore[arg-type]


class TestSynthesisJudgeContradictions:
    def test_lexical_conflict_surfaces(self) -> None:
        judge = _make_judge()
        a = _make_finding("lens_a", "Q1", statement="환율은 강한 상승 흐름")
        b = _make_finding("lens_b", "Q1", statement="환율은 분명한 하락 추세")
        verdict = asyncio.run(judge.judge([a, b]))
        # Anti-pattern #5: 모순은 contradictions 에 *드러나야* 함, 봉합 금지.
        assert len(verdict.contradictions) >= 1
        c = verdict.contradictions[0]
        assert "lens_a" in {c.get("lens_a"), c.get("lens_b")}
        assert "lens_b" in {c.get("lens_a"), c.get("lens_b")}
        # resolution 은 "봉합" 이 아니라 어느 쪽 채택인지 명시 + counter_hypothesis 보존.
        assert "채택" in c.get("resolution", "") or "더 무게" in c.get("resolution", "")

    def test_no_findings_returns_marked_empty_verdict(self) -> None:
        judge = _make_judge()
        verdict = asyncio.run(judge.judge([]))
        assert verdict.contradictions == []
        # main_judgment 가 명시적으로 "분석 finding 없음" 표기 — gate 2 에서 reject 가능.
        assert "finding 없음" in verdict.main_judgment

    def test_consensus_no_contradictions(self) -> None:
        judge = _make_judge()
        a = _make_finding("lens_a", "Q1", statement="시장은 안정적 상태")
        b = _make_finding("lens_b", "Q1", statement="안정 흐름이 지속")
        verdict = asyncio.run(judge.judge([a, b]))
        # 어휘 충돌 없으므로 contradictions 비어있어야 함.
        assert verdict.contradictions == []
        # 빈 contradictions 도 *명시적 빈* (Anti-pattern #5 와는 별개) — main_judgment / counter 채워짐.
        assert verdict.main_judgment.strip() != ""
        assert verdict.counter_hypothesis.strip() != ""


# ----------------------------------------------------------------------
# Smoke: full claim → evidence → finding → judgment chain
# ----------------------------------------------------------------------


def test_chain_smoke() -> None:
    ev = Evidence(
        evidence_id="E-1", source_url="https://x", quote_or_data="q",
        reliability="primary", timestamp="2026",
    )
    claim = Claim(
        claim_id="C-1", statement="결론 A", claim_type="inference",
        evidence_ids=["E-1"],
    )
    finding = AnalyticalFinding(
        finding_id="F-1", lens_id="context",
        answers_question="Q1", main_claim=claim, evidence=[ev],
        confidence=ConfidenceProfile(),
    )
    assert finding.main_claim.evidence_ids == ["E-1"]
    assert finding.evidence[0].evidence_id == "E-1"
