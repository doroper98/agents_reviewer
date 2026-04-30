"""Unit tests for V3 Step 5-C — archetype selection matrix + 11종 등록 + 매칭 정확도.

Run:
    python -m pytest src/tests/test_archetype_selection.py -v
"""

from __future__ import annotations

import pytest

from src.archetypes.base import ReportArchetype
from src.archetypes.registry import (
    list_archetypes,
    get_archetype,
    select_archetype,
)
from src.models import AnalysisStrategy


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _make_strategy(intent: str, event_type: str) -> AnalysisStrategy:
    return AnalysisStrategy(
        event_type=event_type,
        user_intent=intent,  # type: ignore[arg-type]
        intent_confidence=0.9,
        core_questions=["Q1"],
        recommended_lenses=["red_team"],
        evidence_plan=[],
        report_archetype="six_act_theater",
        section_plan=[],
        visualization_plan=[],
    )


# ----------------------------------------------------------------------
# Registry shape (AC-1, AC-2)
# ----------------------------------------------------------------------


class TestArchetypeRegistry:
    def test_eleven_archetypes_registered(self) -> None:
        # v3.3.0: +freeform_essay (composer 전용) → 12종.
        ids = list_archetypes()
        assert len(ids) == 12
        expected = {
            "six_act_theater", "financial_transmission", "tech_decomposition",
            "geopolitical_strategic", "accident_forensic", "policy_implementation",
            "decision_brief", "timeline_first", "scenario_first",
            "mechanism_decomp", "industry_value_chain",
            "freeform_essay",
        }
        assert set(ids) == expected

    def test_all_archetypes_implement_protocol(self) -> None:
        for aid in list_archetypes():
            arch = get_archetype(aid)
            assert isinstance(arch, ReportArchetype), f"{aid} not Protocol"
            assert arch.archetype_id == aid
            assert arch.name
            # Legacy six_act_theater → report.html. freeform_essay → archetypes/freeform_essay.html.
            # 그 외는 모두 report_block.html.
            assert arch.template_path() in (
                "report.html",
                "report_block.html",
                "archetypes/freeform_essay.html",
            )

    def test_six_act_theater_suitable_intents_narrowed(self) -> None:
        sat = get_archetype("six_act_theater")
        # AC-3: suitable_intents 정확히 ["who_benefits", "what_happened"]
        assert sat.suitable_intents == ["who_benefits", "what_happened"]


# ----------------------------------------------------------------------
# Section plan smoke for new archetypes
# ----------------------------------------------------------------------


class TestNewArchetypeSectionPlans:
    @pytest.mark.parametrize("aid", [
        "decision_brief", "timeline_first", "scenario_first",
        "mechanism_decomp", "industry_value_chain",
    ])
    def test_section_plan_non_empty(self, aid: str) -> None:
        arch = get_archetype(aid)
        s = _make_strategy("what_happened", "general")
        plan = arch.section_plan(s)
        assert len(plan) >= 4
        for sec in plan:
            assert sec.block_types, f"{aid}.{sec.section_id} block_types empty"


# ----------------------------------------------------------------------
# Selection matrix (AC-4, AC-5)
# ----------------------------------------------------------------------


class TestSelectionMatrix:
    """10-case regression matrix per spec.

    Cases 1~6: 회귀 (5/6 이상 통과 — AC-4)
    Cases 7~10: 의도 전용 신규 (4/4 통과 — AC-5)
    """

    @pytest.mark.parametrize("label, intent, event_type, expected", [
        # Regression — 6 cases
        ("환율 어떻게 됨", "where_spreads", "currency", "financial_transmission"),
        ("GPT-5 출시", "what_happened", "tech", "tech_decomposition"),
        ("미중 무역 분쟁", "what_happened", "diplomacy", "six_act_theater"),
        ("호르무즈 해협 위기", "what_next", "war", "geopolitical_strategic"),
        ("OO 공장 화재", "why_happened", "accident", "accident_forensic"),
        ("한국 부동산 규제", "who_benefits", "policy", "policy_implementation"),
        # Intent-only new — 4 cases
        ("결정 내려야", "what_to_do", "general", "decision_brief"),
        ("현재 상황만 정리", "what_happened", "general", "timeline_first"),
        ("앞으로 어떻게", "what_next", "general", "scenario_first"),
        ("왜 이렇게 됐는가", "why_happened", "general", "mechanism_decomp"),
    ])
    def test_case_routes_to_expected(
        self, label: str, intent: str, event_type: str, expected: str,
    ) -> None:
        s = _make_strategy(intent, event_type)
        got = select_archetype(s).archetype_id
        assert got == expected, (
            f"{label!r}: got={got}, expected={expected}"
        )


# ----------------------------------------------------------------------
# Tech 사건 의도별 분기 (사용자 우려 #2 해결 검증)
# ----------------------------------------------------------------------


class TestTechIntentDifferentiation:
    """사용자 우려 #2: tech 사건의 의도별 차등 매칭."""

    def test_tech_what_next_routes_to_scenario_first(self) -> None:
        s = _make_strategy("what_next", "tech")
        assert select_archetype(s).archetype_id == "scenario_first"

    def test_tech_what_to_do_routes_to_decision_brief(self) -> None:
        s = _make_strategy("what_to_do", "tech")
        assert select_archetype(s).archetype_id == "decision_brief"

    def test_tech_why_happened_routes_to_decomposition(self) -> None:
        s = _make_strategy("why_happened", "tech")
        assert select_archetype(s).archetype_id == "tech_decomposition"


# ----------------------------------------------------------------------
# Fallback warning (AC-6)
# ----------------------------------------------------------------------


class TestFallbackWarning:
    def test_fallback_emits_warning_on_uncategorizable(self, caplog) -> None:
        """완전 미분류 (general + 의도 매핑 없는 일반 의도) → 4순위 fallback + warning."""
        # who_benefits + general → 어떤 1·2·3순위에도 안 잡힘 (general 은 geopolitical 도 아니고
        # who_benefits 는 의도 전용 매핑 없음) → 4순위 fallback.
        # 단 select_archetype 의 2순위 보충 은 "intent in intent_only_map" 이라 who_benefits 는
        # 보충도 통과 못 함 → 최종 fallback.
        import logging
        with caplog.at_level(logging.WARNING):
            s = _make_strategy("who_benefits", "general")
            arch = select_archetype(s)
        assert arch.archetype_id == "six_act_theater"
        assert any(
            "falling back" in r.message.lower() or "no specific archetype" in r.message.lower()
            for r in caplog.records
        )

    def test_unknown_archetype_id_get_archetype_warns(self, caplog) -> None:
        import logging
        with caplog.at_level(logging.WARNING):
            arch = get_archetype("does_not_exist")
        assert arch.archetype_id == "six_act_theater"
        assert any("Unknown archetype_id" in r.message for r in caplog.records)
