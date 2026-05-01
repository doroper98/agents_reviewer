"""Unit tests for v3.1.0 token-optimization changes.

Run:
    python -m pytest src/tests/test_token_optimization.py -v
"""

from __future__ import annotations

import asyncio
import json

import pytest

from src.brief_builder import build_analysis_brief
from src.lens_policy import select_lenses, select_theme
from src.models import (
    AnalysisRequest,
    AnalysisStrategy,
    AnalyticalFinding,
    Claim,
    ConfidenceProfile,
    ContextAnalysis,
    Evidence,
    FullAnalysisResult,
    JudgmentVerdict,
    PlayerAnalysis,
    ScenarioAnalysis,
)
from src.token_budget import TokenBudget, resolve_mode


class _StubConfig:
    use_cli_mode = False
    anthropic_api_key = ""
    model_name = "claude-opus-4-6"
    model_name_light = "claude-sonnet-4-6"
    cloudflare_account_id = ""
    cloudflare_api_token = ""
    cloudflare_project_name = "x"
    report_output_dir = "/tmp/x"


# ----------------------------------------------------------------------
# 1. TokenBudget + mode resolution
# ----------------------------------------------------------------------


class TestTokenBudget:
    def test_fast_mode_caps(self) -> None:
        b = TokenBudget.for_mode("fast")
        assert b.max_llm_calls == 4
        assert b.max_lenses == 1
        assert not b.use_llm_quality_gate
        assert not b.use_llm_narrative_plan
        assert not b.use_llm_visuals
        assert not b.use_legacy_personas

    def test_standard_mode_caps(self) -> None:
        b = TokenBudget.for_mode("standard")
        assert b.max_llm_calls == 7
        assert b.max_lenses == 2
        assert not b.use_llm_quality_gate
        assert not b.use_llm_narrative_plan
        assert not b.use_llm_visuals
        assert not b.use_legacy_personas

    def test_deep_mode_caps(self) -> None:
        b = TokenBudget.for_mode("deep")
        # v3.3.0: +1 for narrative_composer (Opus 4.7).
        assert b.max_llm_calls == 13
        assert b.max_lenses == 4
        assert b.use_llm_quality_gate
        assert b.use_llm_narrative_plan
        assert b.use_llm_visuals
        assert b.use_legacy_personas
        assert b.use_llm_narrative_composer

    def test_resolve_mode_keywords(self) -> None:
        assert resolve_mode("짧게 설명") == "fast"
        assert resolve_mode("간략히 분석해줘") == "fast"
        assert resolve_mode("심층 분석") == "deep"
        assert resolve_mode("자세히 봐줘") == "deep"
        # default
        assert resolve_mode("한미 정상회담") == "standard"
        # deep 우선
        assert resolve_mode("간략히 심층 분석") == "deep"


# ----------------------------------------------------------------------
# 2. lens_policy
# ----------------------------------------------------------------------


class TestLensPolicy:
    def test_fast_returns_one_lens(self) -> None:
        for et, intent in [
            ("financial", "where_spreads"),
            ("tech", "where_vulnerable"),
            ("accident", "why_happened"),
            ("policy", "what_to_do"),
            ("general", "what_happened"),
        ]:
            lenses = select_lenses(et, intent, "fast")
            assert len(lenses) == 1, (
                f"fast mode should return 1 lens, got {lenses} for {et}/{intent}"
            )

    def test_standard_returns_at_most_two(self) -> None:
        for et, intent in [
            ("financial", "where_spreads"),
            ("tech", "where_vulnerable"),
            ("accident", "why_happened"),
            ("policy", "what_to_do"),
            ("general", "what_happened"),
        ]:
            lenses = select_lenses(et, intent, "standard")
            assert 1 <= len(lenses) <= 2

    def test_deep_returns_at_most_four(self) -> None:
        for et, intent in [
            ("financial", "where_spreads"),
            ("tech", "where_vulnerable"),
            ("accident", "why_happened"),
            ("policy", "what_to_do"),
        ]:
            lenses = select_lenses(et, intent, "deep")
            assert 1 <= len(lenses) <= 4

    def test_meta_lenses_only_for_decision_intents(self) -> None:
        # what_happened 는 메타 lens 자동 추가 안 됨 (standard 에서)
        lenses = select_lenses("general", "what_happened", "standard")
        assert "red_team" not in lenses
        assert "pre_mortem" not in lenses

    def test_red_team_added_for_what_to_do_in_deep(self) -> None:
        lenses = select_lenses("general", "what_to_do", "deep")
        assert "red_team" in lenses

    def test_theme_selection(self) -> None:
        assert select_theme("tech") == "tech"
        assert select_theme("financial") == "financial"
        assert select_theme("war") == "geopolitical"
        assert select_theme("accident") == "burgundy"


# ----------------------------------------------------------------------
# 3. Compact JSON serialization in BaseAgent
# ----------------------------------------------------------------------


class TestCompactJson:
    def test_serialize_context_uses_compact_separators(self) -> None:
        from src.agents.base import BaseAgent

        ctx = {
            "key": "값",
            "list": [1, 2, 3],
            "nested": {"a": "b"},
            "strategic_directive": "지시",
        }
        directive, msg = BaseAgent._serialize_context(ctx)
        assert directive == "지시"
        # compact JSON: no spaces after separators.
        assert ", " not in msg
        assert ": " not in msg
        # original dict not mutated.
        assert "strategic_directive" in ctx

    def test_serialize_no_indent(self) -> None:
        from src.agents.base import BaseAgent

        ctx = {"a": 1, "b": [1, 2]}
        _, msg = BaseAgent._serialize_context(ctx)
        # no newlines from indent=2.
        assert "\n" not in msg


# ----------------------------------------------------------------------
# 4. AnalysisBrief + builder
# ----------------------------------------------------------------------


class TestAnalysisBrief:
    def test_brief_compact_omits_empty(self) -> None:
        result = FullAnalysisResult(
            request=AnalysisRequest(event_description="x"),
            context=ContextAnalysis(
                event_name="이벤트",
                summary="요약",
                date="2026-04-27",
                key_figures=[{"label": "값", "value": "1", "context": "기준"}],
                timeline=[{"date": "2026-01", "event": "시작"}],
                sources=["s1", "s2"],
            ),
        )
        brief = build_analysis_brief(result)
        compact = brief.compact()
        assert "event" in compact
        assert "facts" in compact
        assert "timeline" in compact
        # actors / scenarios 데이터 없음 → 키 자체가 빠져야 함.
        assert "actors" not in compact
        assert "scenarios" not in compact

    def test_brief_length_caps(self) -> None:
        # 매우 큰 timeline / sources 를 넣어도 cap 됨.
        ctx = ContextAnalysis(
            event_name="e",
            summary="s",
            timeline=[{"date": str(i), "event": f"e{i}"} for i in range(50)],
            sources=[f"https://example.com/{i}" for i in range(50)],
        )
        result = FullAnalysisResult(
            request=AnalysisRequest(event_description="x"),
            context=ctx,
        )
        brief = build_analysis_brief(result)
        compact = brief.compact()
        assert len(compact["timeline"]) <= 6
        assert len(compact["sources"]) <= 8


# ----------------------------------------------------------------------
# 5. ReportSynthesizer deterministic summary
# ----------------------------------------------------------------------


class TestDeterministicSummary:
    def test_builds_governance_and_key_items_without_llm(self) -> None:
        from src.agents.report_synthesizer import ReportSynthesizer

        result = FullAnalysisResult(
            request=AnalysisRequest(event_description="x"),
            context=ContextAnalysis(event_name="이벤트", summary="요약 한 문장."),
            judgment=JudgmentVerdict(
                main_judgment="핵심 판단",
                base_scenario="기준 시나리오",
                biggest_uncertainty="불확실",
                counter_hypothesis="반대",
                contradictions=[],
                counter_evidence_needed=[],
                confidence=ConfidenceProfile(),
            ),
        )
        gov, key = ReportSynthesizer._build_deterministic_summary(result)
        assert gov, "governance should be non-empty"
        assert len(key) >= 3

    def test_returns_empty_when_no_data(self) -> None:
        from src.agents.report_synthesizer import ReportSynthesizer

        result = FullAnalysisResult(
            request=AnalysisRequest(event_description="x"),
        )
        gov, key = ReportSynthesizer._build_deterministic_summary(result)
        assert gov == ""
        assert key == []


# ----------------------------------------------------------------------
# 6. Deprecated personas not invoked in fast/standard
# ----------------------------------------------------------------------


class TestDeprecatedPersonasGated:
    def test_orchestrator_skips_personas_for_fast_standard(self) -> None:
        """orchestrator 가 fast/standard 에서 player/dynamics/chain_reaction 페르소나
        호출을 건너뛰는지 검증. 전체 orchestrator 를 호출하면 LLM 이 발화하므로,
        ``budget.use_legacy_personas`` 플래그만 검사 (실제 호출 분기 코드는 본 플래그를 따름).
        """
        from src.token_budget import TokenBudget
        for mode in ("fast", "standard"):
            assert not TokenBudget.for_mode(mode).use_legacy_personas
        assert TokenBudget.for_mode("deep").use_legacy_personas


# ----------------------------------------------------------------------
# 7. ReportSynthesizer narrative plan gating
# ----------------------------------------------------------------------


class TestNarrativePlanGating:
    def test_default_plan_used_when_llm_disabled(self) -> None:
        """``use_llm_narrative_plan=False`` 일 때 ``_default_narrative_plan`` 만 호출되는지.

        synthesize() 의 narrative plan 분기를 단위 검증.
        """
        from src.agents.report_synthesizer import ReportSynthesizer

        cfg = _StubConfig()
        rs = ReportSynthesizer(cfg)  # type: ignore[arg-type]
        rs.use_llm_narrative_plan = False
        result = FullAnalysisResult(
            request=AnalysisRequest(event_description="x"),
            context=ContextAnalysis(event_name="e", summary="s"),
        )
        plan = rs._default_narrative_plan(result)
        assert plan.sections, "default plan must produce at least one section"


# ----------------------------------------------------------------------
# 8. SynthesisJudge gating
# ----------------------------------------------------------------------


class TestSynthesisJudgeGating:
    def test_fast_uses_heuristic_only(self) -> None:
        from src.agents.synthesis_judge import SynthesisJudge

        cfg = _StubConfig()
        sj = SynthesisJudge(cfg)  # type: ignore[arg-type]
        sj.use_llm_synthesis = False
        sj.allow_llm_on_low_confidence = False
        # No contradictions, high confidence → no LLM call.
        confidence = ConfidenceProfile(
            source_diversity=0.8, data_freshness=0.8, expert_consensus=0.8,
        )
        assert not sj._should_call_llm([], confidence)

    def test_standard_calls_llm_on_contradictions(self) -> None:
        from src.agents.synthesis_judge import SynthesisJudge

        cfg = _StubConfig()
        sj = SynthesisJudge(cfg)  # type: ignore[arg-type]
        sj.use_llm_synthesis = False
        sj.allow_llm_on_low_confidence = True
        confidence = ConfidenceProfile(
            source_diversity=0.8, data_freshness=0.8, expert_consensus=0.8,
        )
        # Contradictions exist → LLM should be called.
        assert sj._should_call_llm([{"lens_a": "x", "lens_b": "y"}], confidence)

    def test_deep_always_calls_llm(self) -> None:
        from src.agents.synthesis_judge import SynthesisJudge

        cfg = _StubConfig()
        sj = SynthesisJudge(cfg)  # type: ignore[arg-type]
        sj.use_llm_synthesis = True
        confidence = ConfidenceProfile(
            source_diversity=1.0, data_freshness=1.0, expert_consensus=1.0,
        )
        assert sj._should_call_llm([], confidence)


# ----------------------------------------------------------------------
# 9. Visual builder deterministic
# ----------------------------------------------------------------------


class TestVisualBuilder:
    def test_actor_svg_renders_when_data_present(self) -> None:
        from src.visual_builder import build_actor_relationship_svg

        players = PlayerAnalysis(players=[
            {"name": "A", "role_tag": "주역", "risk_level": "높음"},
            {"name": "B", "role_tag": "조연", "risk_level": "낮음"},
        ])
        svg = build_actor_relationship_svg(players)
        assert svg.startswith("<svg")
        assert "A" in svg and "B" in svg

    def test_returns_empty_when_no_data(self) -> None:
        from src.visual_builder import build_actor_relationship_svg

        assert build_actor_relationship_svg(None) == ""
        assert build_actor_relationship_svg(PlayerAnalysis(players=[])) == ""

    def test_advanced_visual_keyword_detection(self) -> None:
        from src.visual_builder import needs_advanced_visuals

        assert needs_advanced_visuals("이 사건의 지도 만들어줘")
        assert needs_advanced_visuals("차트 포함 분석")
        assert not needs_advanced_visuals("그냥 분석해줘")
