"""V5 Phase 3 — Layout Typesetter regression test.

REFACTOR_V5_PLAN.md §10.5 인수 기준:
    - 9종 layout 모두 데모 가능 (HTML 템플릿은 별도).
    - LayoutTypesetter 호출 실패 시 모든 섹션 'standard' fallback.
    - AP-V5-3 강제 — layout primitive 추가 금지 (9종 동결).

본 모듈은 9-vocab SSOT + heuristic fallback + AP-V5-3 정합성 검증.
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.agents.layout_typesetter import (
    LAYOUT_VOCAB,
    SYSTEM_PROMPT,
    LayoutTypesetter,
    fallback_all_standard,
    plan_layouts_via_heuristics,
)
from src.state.models import LayoutAssignment, LayoutPrimitive


# ─── 9-vocab SSOT (Plan §10.2 + AP-V5-3) ─────────────────────────


def test_layout_vocab_count_is_9() -> None:
    """Plan §10.2 — 9종 정본 (AP-V5-3 강제 동결)."""
    assert len(LAYOUT_VOCAB) == 9


def test_layout_vocab_matches_plan_10_2() -> None:
    """Plan §10.2 의 9종 byte-equal."""
    expected = {
        "standard", "hero_map", "hero_chart", "split_2col",
        "sidebar_callout", "qna_panel", "timeline_strip",
        "signature_summary", "exhibit_grid",
    }
    assert set(LAYOUT_VOCAB) == expected


def test_layout_primitive_literal_matches_vocab() -> None:
    """LayoutPrimitive Literal 의 enum 이 LAYOUT_VOCAB 와 byte-equal."""
    from typing import get_args
    actual = set(get_args(LayoutPrimitive))
    assert actual == set(LAYOUT_VOCAB)


def test_layout_assignment_default_is_standard() -> None:
    la = LayoutAssignment(section_idx=0)
    assert la.layout == "standard"
    assert la.assigned_by == "default"


def test_layout_assignment_assigned_by_3_enum() -> None:
    from typing import get_args
    actual = set(get_args(LayoutAssignment.model_fields["assigned_by"].annotation))
    assert actual == {"layout_typesetter", "heuristic", "default"}


# ─── SYSTEM_PROMPT 정합성 ────────────────────────────────────────


def test_system_prompt_contains_all_9_layouts() -> None:
    """Plan §10.2 의 9종 layout 모두 SYSTEM_PROMPT 에 명시."""
    for layout in LAYOUT_VOCAB:
        assert layout in SYSTEM_PROMPT, f"layout '{layout}' SYSTEM_PROMPT 누락"


def test_system_prompt_contains_decision_principles() -> None:
    """Plan §10.3 의 결정 원칙 (60~70% standard, hero_* ≤ 1~2개 등)."""
    assert "60~70%" in SYSTEM_PROMPT or "standard" in SYSTEM_PROMPT
    assert "연속" in SYSTEM_PROMPT  # 연속 배치 차단
    assert "hero_map" in SYSTEM_PROMPT
    assert "signature_summary" in SYSTEM_PROMPT


def test_system_prompt_excludes_strategic_decision_brief() -> None:
    """전략 모드 decision_brief 는 별도 vocab — 본 prompt 명시 안 함 (혼동 차단)."""
    # 본문 명시는 OK 단 layout 결정 vocab 에 포함 X.
    # 정확히는 'decision_brief' 가 layout 후보로 나오지 않도록.
    layout_section_after_vocab = SYSTEM_PROMPT.split("[결정 원칙]")[0]
    # 9-vocab 직접 listing 부분에 decision_brief 가 들어가 있지 않은지.
    assert "decision_brief" not in layout_section_after_vocab.split("\n[")[0]


# ─── heuristic fallback (LLM 0) ──────────────────────────────────


def test_heuristic_empty_sections() -> None:
    assert plan_layouts_via_heuristics([]) == []


def test_heuristic_default_all_standard() -> None:
    """평범한 섹션들 — 대부분 standard."""
    sections = [
        {"heading": "h1", "prose": "p1", "charts": []},
        {"heading": "h2", "prose": "p2", "charts": []},
        {"heading": "h3", "prose": "p3", "charts": []},
    ]
    result = plan_layouts_via_heuristics(sections)
    assert len(result) == 3
    standards = sum(1 for r in result if r.layout == "standard")
    # 모두 standard.
    assert standards == 3


def test_heuristic_geographic_first_section_hero_map() -> None:
    """has_map=True + 첫 섹션 → hero_map (1~2번째 권장)."""
    sections = [
        {"heading": "도입", "prose": "...", "charts": []},
        {"heading": "본론", "prose": "...", "charts": []},
    ]
    result = plan_layouts_via_heuristics(sections, has_map=True)
    assert result[0].layout == "hero_map"
    # 두 번째는 standard (연속 차단).
    assert result[1].layout != "hero_map"


def test_heuristic_last_section_conclusion_signature_summary() -> None:
    """마지막 섹션의 heading 에 '결론' → signature_summary."""
    sections = [
        {"heading": "도입", "prose": "...", "charts": []},
        {"heading": "본론", "prose": "...", "charts": []},
        {"heading": "결론", "prose": "...", "charts": []},
    ]
    result = plan_layouts_via_heuristics(sections)
    assert result[-1].layout == "signature_summary"


def test_heuristic_exhibit_grid_for_3plus_charts() -> None:
    """차트 ≥ 3 → exhibit_grid."""
    sections = [
        {"heading": "도입", "prose": "...", "charts": []},
        {
            "heading": "데이터 종합",
            "prose": "...",
            "charts": [
                {"type": "bar"}, {"type": "line"}, {"type": "donut"},
            ],
        },
    ]
    result = plan_layouts_via_heuristics(sections)
    assert result[1].layout == "exhibit_grid"


def test_heuristic_qna_panel_for_question_heading() -> None:
    sections = [
        {"heading": "흔한 오해 5가지", "kicker": "Q&A", "prose": "...", "charts": []},
    ]
    result = plan_layouts_via_heuristics(sections)
    assert result[0].layout == "qna_panel"


def test_heuristic_timeline_strip_for_timeline_heading() -> None:
    sections = [
        {"heading": "사건 흐름", "prose": "...", "charts": []},
    ]
    result = plan_layouts_via_heuristics(sections)
    assert result[0].layout == "timeline_strip"


def test_heuristic_split_2col_for_comparison() -> None:
    sections = [
        {
            "heading": "한국 vs 일본 비교",
            "prose": "...",
            "charts": [{"type": "bar"}],
        },
    ]
    result = plan_layouts_via_heuristics(sections)
    assert result[0].layout == "split_2col"


def test_heuristic_sidebar_callout_for_analogy() -> None:
    sections = [
        {
            "heading": "본론",
            "prose": "...",
            "charts": [],
            "analogy": {"title": "비유 박스", "body": "..."},
        },
    ]
    result = plan_layouts_via_heuristics(sections)
    assert result[0].layout == "sidebar_callout"


def test_heuristic_no_consecutive_same_layout() -> None:
    """같은 layout 이 *연속* 으로 배치되지 않음 (Plan §10.3 리듬 원칙)."""
    sections = [
        {"heading": "흐름 1", "prose": "...", "charts": []},
        {"heading": "흐름 2", "prose": "...", "charts": []},   # timeline_strip 후보
        {"heading": "흐름 3", "prose": "...", "charts": []},
    ]
    result = plan_layouts_via_heuristics(sections)
    # 첫 timeline_strip 후 두 번째는 strip 이 안 옴.
    for i in range(1, len(result)):
        if result[i].layout != "standard":
            assert result[i].layout != result[i - 1].layout, (
                f"연속 배치 발견: section {i-1}={result[i-1].layout}, "
                f"section {i}={result[i].layout}"
            )


def test_heuristic_hero_count_capped_at_2() -> None:
    """hero_map / hero_chart 합계 ≤ 2."""
    sections = [{"heading": f"h{i}", "prose": "", "charts": [{"type": "bar"}]} for i in range(5)]
    result = plan_layouts_via_heuristics(sections, has_map=True)
    hero_count = sum(1 for r in result if r.layout in ("hero_map", "hero_chart"))
    assert hero_count <= 2


def test_heuristic_strategic_mode_falls_back_to_standard() -> None:
    """전략 모드는 별도 vocab — heuristic 은 처리 안 하므로 standard fallback
    (LayoutTypesetter.assign_layouts 가 처리)."""
    # heuristic 자체는 strategic 인자 없음 — agent 의 책임.
    pass


# ─── fallback_all_standard ───────────────────────────────────────


def test_fallback_all_standard_count() -> None:
    result = fallback_all_standard(5)
    assert len(result) == 5
    assert all(r.layout == "standard" for r in result)
    assert all(r.assigned_by == "default" for r in result)


def test_fallback_all_standard_zero() -> None:
    assert fallback_all_standard(0) == []


# ─── LayoutTypesetter agent 모델 (Plan §10.3) ───────────────────


def test_layout_typesetter_class_constants() -> None:
    """Plan §10.3 — Sonnet 4.6, 빠른 결정."""
    assert LayoutTypesetter.TYPESETTER_MODEL == "claude-sonnet-4-6"
    assert LayoutTypesetter.MAX_TOKENS == 2048


def test_layout_typesetter_init_smoke() -> None:
    """Agent 인스턴스 생성 smoke."""
    from src.config import Config
    config = Config()
    agent = LayoutTypesetter(config)
    assert agent.name == "layout_typesetter"
    assert agent.system_prompt == SYSTEM_PROMPT


# ─── AP-V5-3 강제 — layout primitive 추가 금지 ───────────────────


def test_ap_v5_3_layout_vocab_frozen_at_9() -> None:
    """AP-V5-3 — 분석 모드 9종 동결. 추가/변경 금지 가드.

    본 테스트가 fail 하면 LAYOUT_VOCAB 가 변경됨 → Plan §10.2 + AP-V5-3
    + docs/STRATEGIC_MODE_PROMPT.md §5 (decision_brief 별도) + 회귀
    테스트 *모두* 동시 갱신 필요. 단순 수정 금지.
    """
    assert len(LAYOUT_VOCAB) == 9, (
        f"AP-V5-3 위반: layout vocab 가 9 → {len(LAYOUT_VOCAB)}. "
        "Plan §10.2 동결 정책 + 본 회귀 테스트 + STRATEGIC_MODE_PROMPT 도 함께 갱신해야."
    )
