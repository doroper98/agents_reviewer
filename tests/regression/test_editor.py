"""V5 Phase 1 — Editor Pass regression test.

REFACTOR_V5_PLAN.md §5.6 인수 기준:
    1. 2-call → 3-call (Context → Compose → Edit) — opt-in 시점에 활성.
    2. Editor 호출 실패 시 graceful fallback (DraftReport 그대로).
    3. 기존 사건 5건 재실행, watch_signals / contradictions 개수 동일 유지.

본 모듈은 #2 (graceful fallback) + #3 (보존 검증) + 7-rubric 정합성 검증.
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.agents.editor import (
    SECTION_SCORE_RUBRICS,
    SYSTEM_PROMPT,
    EditedReport,
    Editor,
    EditorCritique,
    SectionRevision,
    SectionScore,
    _draft_to_edited,
    assert_signal_count_preserved,
    detect_cliches,
)


# ─── 7-rubric SSOT 정합성 (Plan §5.4) ────────────────────────────


def test_section_score_rubrics_count_is_7() -> None:
    assert len(SECTION_SCORE_RUBRICS) == 7
    expected = {
        "padding", "punch", "contradiction", "binding",
        "asymmetry", "originality", "vocabulary",
    }
    assert set(SECTION_SCORE_RUBRICS) == expected


def test_section_score_model_has_all_7_fields() -> None:
    """SectionScore 모델이 7-rubric 모두 보유."""
    fields = set(SectionScore.model_fields.keys())
    expected_required = {
        "padding", "punch", "contradiction", "binding",
        "asymmetry", "originality", "vocabulary",
    }
    assert expected_required <= fields


# ─── SYSTEM_PROMPT 정합성 ────────────────────────────────────────


def test_system_prompt_contains_all_7_rubrics() -> None:
    """Plan §5.4 의 7-rubric 모두 SYSTEM_PROMPT 에 명시."""
    expected_ko = [
        "군더더기", "결론의 칼날", "모순 봉합",
        "차트-본문 결합도", "분량 비대칭", "신선함",
        "외래어 / 전문용어 풀이",
    ]
    for kw in expected_ko:
        assert kw in SYSTEM_PROMPT, f"7-rubric '{kw}' SYSTEM_PROMPT 누락"


def test_system_prompt_preservation_rules() -> None:
    """Plan §5.6 — 보존 규칙 (contradictions / watch_signals 개수 / 사실)."""
    assert "contradictions" in SYSTEM_PROMPT
    assert "watch_signals" in SYSTEM_PROMPT
    assert "Anti-pattern #5" in SYSTEM_PROMPT


def test_system_prompt_includes_anti_pattern_5() -> None:
    """모순 봉합 (Anti-pattern #5) 명시 — Plan §5.4 Q3."""
    assert "봉합" in SYSTEM_PROMPT


def test_system_prompt_response_schema() -> None:
    """JSON 응답 스키마 — critique / revisions / final."""
    assert "critique" in SYSTEM_PROMPT
    assert "revisions" in SYSTEM_PROMPT
    assert "final" in SYSTEM_PROMPT


# ─── 보존 검증 — Plan §5.6 인수 기준 #3 ──────────────────────────


def _draft_with_signals_and_contradictions() -> dict:
    return {
        "headline": "테스트",
        "deck": "deck",
        "sections": [{"heading": "h", "prose": "x" * 1000}],
        "closing": "결론.",
        "watch_signals": [
            {"signal": "x", "direction": "confirms_base"},
            {"signal": "y", "direction": "rejects_base"},
            {"signal": "z", "direction": "ambiguous"},
        ],
        "contradictions": [
            {"side_a": "a", "side_b": "b"},
            {"side_a": "c", "side_b": "d"},
        ],
    }


def test_preservation_passes_when_count_same() -> None:
    draft = _draft_with_signals_and_contradictions()
    edited = dict(draft)   # 동일 개수.
    ok, _ = assert_signal_count_preserved(draft, edited)
    assert ok


def test_preservation_passes_when_edited_adds_signals() -> None:
    """편집이 신호를 *추가* 하는 건 OK (drop 만 거절)."""
    draft = _draft_with_signals_and_contradictions()
    edited = dict(draft)
    edited["watch_signals"] = list(draft["watch_signals"]) + [{"signal": "extra"}]
    ok, _ = assert_signal_count_preserved(draft, edited)
    assert ok


def test_preservation_fails_when_watch_signals_dropped() -> None:
    """Editor 가 watch_signals 를 drop 하면 fail (Plan §5.6)."""
    draft = _draft_with_signals_and_contradictions()
    edited = dict(draft)
    edited["watch_signals"] = draft["watch_signals"][:1]   # 3 → 1
    ok, reason = assert_signal_count_preserved(draft, edited)
    assert not ok
    assert "watch_signals" in reason


def test_preservation_fails_when_contradictions_dropped() -> None:
    """Editor 가 contradictions 봉합으로 drop → Anti-pattern #5 회귀."""
    draft = _draft_with_signals_and_contradictions()
    edited = dict(draft)
    edited["contradictions"] = []
    ok, reason = assert_signal_count_preserved(draft, edited)
    assert not ok
    assert "Anti-pattern #5" in reason


# ─── 진부어 차단 (Plan §5.4 Q1) ──────────────────────────────────


def test_detect_cliches_finds_padding_phrases() -> None:
    text = "주목할 만한 점은 사용자 의존도가 높다는 것이다."
    cliches = detect_cliches(text)
    assert "주목할 만한 점은" in cliches


def test_detect_cliches_finds_multiple() -> None:
    text = "결론적으로 주목할 만한 점은 매우 중요하다는 점이다."
    cliches = detect_cliches(text)
    assert len(cliches) >= 2


def test_detect_cliches_clean_text() -> None:
    text = "한국 35%, 일본 80% 의 의존도. 호르무즈 봉쇄 시 즉시 충격."
    assert detect_cliches(text) == []


def test_detect_cliches_empty() -> None:
    assert detect_cliches("") == []
    assert detect_cliches(None) == []   # type: ignore[arg-type]


# ─── EditedReport 모델 ───────────────────────────────────────────


def test_edited_report_default_fields() -> None:
    er = EditedReport()
    assert er.headline == ""
    assert er.editor_pass_applied is False
    assert er.confidence_score == 0.5


def test_edited_report_preserves_composed_fields() -> None:
    """ComposedReport 와 *동일 구조* 보존."""
    expected_compatible_fields = {
        "headline", "deck", "sections", "closing",
        "watch_signals", "contradictions",
        "confidence_summary", "confidence_score", "embedded_map",
    }
    fields = set(EditedReport.model_fields.keys())
    assert expected_compatible_fields <= fields


def test_edited_report_editor_pass_applied_marker() -> None:
    """editor_pass_applied 가 True 면 실제 Editor 가 처리, False 면 fallback."""
    fields = EditedReport.model_fields
    assert "editor_pass_applied" in fields
    assert "editor_critique" in fields


# ─── _draft_to_edited fallback ───────────────────────────────────


def test_draft_to_edited_fallback_marks_not_applied() -> None:
    draft = _draft_with_signals_and_contradictions()
    er = _draft_to_edited(draft, applied=False)
    assert er.editor_pass_applied is False
    assert er.headline == "테스트"
    assert len(er.watch_signals) == 3
    assert len(er.contradictions) == 2


def test_draft_to_edited_applied_true() -> None:
    draft = _draft_with_signals_and_contradictions()
    er = _draft_to_edited(draft, applied=True)
    assert er.editor_pass_applied is True


# ─── EditorCritique / SectionScore 모델 ──────────────────────────


def test_section_score_range_validated() -> None:
    """7-rubric 점수가 0~10 범위."""
    SectionScore(section_idx=0, padding=10, punch=0)   # 경계 OK
    with pytest.raises(Exception):
        SectionScore(section_idx=0, padding=11)
    with pytest.raises(Exception):
        SectionScore(section_idx=0, padding=-1)


def test_section_revision_action_3_enum() -> None:
    from typing import get_args
    actions = set(get_args(SectionRevision.model_fields["action"].annotation))
    assert actions == {"rewrite", "cut", "keep"}


def test_editor_critique_default_empty() -> None:
    ec = EditorCritique()
    assert ec.critique == []
    assert ec.revisions == []
    assert ec.final == {}


# ─── Editor agent 모델·예산 (Plan §5.3) ─────────────────────────


def test_editor_class_constants_match_plan_5_3() -> None:
    """Plan §5.3 — composer 동일 모델(v8.5.0 부터 claude-opus-5), MAX_TOKENS=16000."""
    assert Editor.EDITOR_MODEL == "claude-opus-5"
    assert Editor.MAX_TOKENS == 16000


def test_editor_init_smoke() -> None:
    """Editor 인스턴스 생성 smoke (LLM 호출 X)."""
    from src.config import Config
    config = Config()
    editor = Editor(config)
    assert editor.name == "editor"
    assert editor.model_name == "claude-opus-5"
    assert editor.system_prompt == SYSTEM_PROMPT
