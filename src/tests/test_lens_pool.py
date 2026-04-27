"""Unit tests for V3 Step 5-A — Lens Pool.

Run:
    python -m pytest src/tests/test_lens_pool.py -v
"""

from __future__ import annotations

import asyncio

import pytest

from src.archetypes.registry import list_archetypes, get_archetype
from src.lenses import LensRunner
from src.lenses.registry import get_lens, list_lenses
from src.models import (
    AnalysisRequest,
    AnalysisStrategy,
    Evidence,
    FullAnalysisResult,
)


# ----------------------------------------------------------------------
# Stub config — disables CLI calls so all lens runs hit the heuristic fallback.
# ----------------------------------------------------------------------


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
# Lens registry / Protocol contract
# ----------------------------------------------------------------------


class TestLensRegistry:
    def test_lens_count_v3(self) -> None:
        """V3 Step 5-C 후 11종: 분야 6 + 메타 2 + 페르소나 이전 3."""
        lenses = list_lenses()
        assert len(lenses) == 11
        expected = {
            # Step 5-A
            "geopolitical", "financial_transmission", "tech_architecture",
            "policy_implementation", "accident_causality", "market_structure",
            "red_team", "pre_mortem",
            # Step 5-C — 페르소나 이전
            "stakeholder", "structural", "cascade",
        }
        assert set(lenses) == expected

    def test_all_lenses_implement_runner(self) -> None:
        cfg = _StubConfig()
        for lid in list_lenses():
            lens = get_lens(lid, cfg)  # type: ignore[arg-type]
            assert isinstance(lens, LensRunner), f"{lid} not LensRunner"
            assert lens.lens_id == lid
            assert lens.name
            assert lens.system_prompt
            assert lens.method_steps
            assert lens.failure_modes

    def test_unknown_lens_falls_back_to_red_team(self) -> None:
        cfg = _StubConfig()
        lens = get_lens("does_not_exist", cfg)  # type: ignore[arg-type]
        assert lens.lens_id == "red_team"


# ----------------------------------------------------------------------
# Single-lens execution (heuristic fallback path — no LLM call)
# ----------------------------------------------------------------------


class TestLensExecution:
    def test_each_lens_produces_finding_in_fallback(self) -> None:
        """fallback path 가 모든 lens 에서 Anti-pattern #4 가드 통과 + 1 finding 산출."""
        cfg = _StubConfig()
        evidence = [Evidence(
            evidence_id="E-001", source_url="https://example.com",
            quote_or_data="sample quote", reliability="secondary",
            timestamp="2026-04-26",
        )]
        for lid in list_lenses():
            lens = get_lens(lid, cfg)  # type: ignore[arg-type]
            findings = asyncio.run(lens.run(
                evidence=evidence, directive="",
                event_meta={"event_name": "T", "summary": "S", "category": "C"},
                answers_question="Q1?",
            ))
            assert len(findings) == 1, f"{lid} did not produce 1 finding"
            f = findings[0]
            assert f.lens_id == lid
            assert f.main_claim.evidence_ids, (
                f"{lid} produced empty evidence_ids — Anti-pattern #4 violation"
            )

    def test_lens_with_empty_evidence_uses_inferred(self) -> None:
        """Evidence 풀이 비어도 finding 산출 — model_inference Evidence 자동 생성."""
        cfg = _StubConfig()
        lens = get_lens("red_team", cfg)  # type: ignore[arg-type]
        findings = asyncio.run(lens.run(
            evidence=[], directive="",
            event_meta={"event_name": "T"}, answers_question="",
        ))
        assert len(findings) == 1
        f = findings[0]
        assert f.evidence
        assert f.evidence[0].reliability == "model_inference"


# ----------------------------------------------------------------------
# Archetype registry — Step 5-A 추가된 3종 검증
# ----------------------------------------------------------------------


class TestArchetypeExtension:
    def test_archetype_count_v3(self) -> None:
        """V3 Step 5-C 후 11종 archetype."""
        ids = list_archetypes()
        assert len(ids) == 11
        for new_id in (
            "geopolitical_strategic", "accident_forensic", "policy_implementation",
            "decision_brief", "timeline_first", "scenario_first",
            "mechanism_decomp", "industry_value_chain",
        ):
            assert new_id in ids

    def test_new_archetypes_use_block_dispatcher(self) -> None:
        for aid in ("geopolitical_strategic", "accident_forensic", "policy_implementation"):
            arch = get_archetype(aid)
            assert arch.template_path() == "report_block.html"

    def test_new_archetypes_section_plans_have_block_types(self) -> None:
        from src.models import AnalysisStrategy
        s = AnalysisStrategy(
            event_type="t", user_intent="why_happened", intent_confidence=0.9,
            core_questions=["Q1"], recommended_lenses=["red_team"],
            evidence_plan=[], report_archetype="six_act_theater",
            section_plan=[], visualization_plan=[],
        )
        for aid in ("geopolitical_strategic", "accident_forensic", "policy_implementation"):
            arch = get_archetype(aid)
            plan = arch.section_plan(s)
            assert len(plan) >= 5, f"{aid} section_plan too short"
            for sec in plan:
                assert sec.block_types, f"{aid}.{sec.section_id} block_types empty"


# ----------------------------------------------------------------------
# Orchestrator lens-cap enforcement (Anti-pattern #6)
# ----------------------------------------------------------------------


class TestLensCap:
    def test_pydantic_caps_lenses_at_four_at_construction(self) -> None:
        """AnalysisStrategy.recommended_lenses 가 max_length=4 — 5개 입력 시 ValidationError.
        모델 레벨 1차 가드 (Anti-pattern #6).
        """
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            AnalysisStrategy(
                event_type="financial", user_intent="where_spreads", intent_confidence=0.9,
                core_questions=["Q1"],
                recommended_lenses=[
                    "geopolitical", "financial_transmission", "tech_architecture",
                    "policy_implementation", "market_structure",  # 5 requested
                ],
                evidence_plan=[], report_archetype="six_act_theater",
                section_plan=[], visualization_plan=[],
            )

    def test_orchestrator_runtime_cap_guards_post_mutation(self) -> None:
        """런타임 mutation (e.g. 외부 코드가 list 에 append) 으로 cap 우회 시도 시,
        _run_lenses 의 LENS_CAP_PER_EVENT 가 2차 가드로 작동.
        """
        from src.orchestrator import Orchestrator

        cfg = _StubConfig()
        orch = Orchestrator.__new__(Orchestrator)
        orch.config = cfg  # type: ignore[assignment]
        assert orch.LENS_CAP_PER_EVENT == 4

        req = AnalysisRequest(event_description="t")
        strat = AnalysisStrategy(
            event_type="financial", user_intent="where_spreads", intent_confidence=0.9,
            core_questions=["Q1"],
            recommended_lenses=[
                "geopolitical", "financial_transmission", "tech_architecture",
                "policy_implementation",  # 4 — Pydantic 통과
            ],
            evidence_plan=[], report_archetype="six_act_theater",
            section_plan=[], visualization_plan=[],
        )
        # 사후 mutation 으로 5번째 추가 (defensive 2차 가드 검증용)
        strat.recommended_lenses.append("market_structure")
        result = FullAnalysisResult(request=req, strategy=strat)

        async def _noop(_msg: str) -> None:
            pass

        evidence = [Evidence(
            evidence_id="E-001", source_url="", quote_or_data="q",
            reliability="secondary", timestamp="2026",
        )]
        findings = asyncio.run(orch._run_lenses(result, evidence, _noop))
        # 4 cap 가 _run_lenses 단계에서 작동: 5번째 (market_structure) 잘림.
        assert len(findings) == 4
        seen_lenses = {f.lens_id for f in findings}
        assert "market_structure" not in seen_lenses, (
            "5번째 lens 가 런타임 cap 을 우회했음 — Anti-pattern #6"
        )

    def test_unknown_lens_id_filtered(self) -> None:
        """미등록 lens_id 는 _run_lenses 단계에서 걸러짐 (registry fallback 까지 가지 않음)."""
        from src.orchestrator import Orchestrator

        cfg = _StubConfig()
        orch = Orchestrator.__new__(Orchestrator)
        orch.config = cfg  # type: ignore[assignment]

        req = AnalysisRequest(event_description="t")
        strat = AnalysisStrategy(
            event_type="t", user_intent="what_happened", intent_confidence=0.5,
            core_questions=["Q1"],
            recommended_lenses=["red_team", "totally_unknown_lens"],
            evidence_plan=[], report_archetype="six_act_theater",
            section_plan=[], visualization_plan=[],
        )
        result = FullAnalysisResult(request=req, strategy=strat)

        async def _noop(_msg: str) -> None:
            pass

        evidence = [Evidence(
            evidence_id="E-001", source_url="", quote_or_data="q",
            reliability="secondary", timestamp="2026",
        )]
        findings = asyncio.run(orch._run_lenses(result, evidence, _noop))
        # red_team 만 통과 — totally_unknown_lens 는 filter 단계에서 제거.
        assert len(findings) == 1
        assert findings[0].lens_id == "red_team"
