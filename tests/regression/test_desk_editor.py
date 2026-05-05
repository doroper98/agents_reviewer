"""V5 Phase 7 — Desk Editor regression test.

REFACTOR_V5_PLAN.md §16.10 인수 기준:
    1. DeskEditor 호출이 모든 lower phase *이후* 마지막에 추가.
    2. 자동 KILL_RULES (논리 5종 + 시각 3종) 모두 회귀 테스트.
    3. Playwright 캡쳐 파이프라인 동작 검증.
    4. 캡쳐 자체 실패 시 graceful degrade.
    5. KILL 발생 시 Cloudflare 배포 차단 + 텔레그램 알림.
    6. 첫 50건 운영 후 publish/hold/kill 분포 — 운영 측정.
    7. HOLD 재호출 1회 cap 작동 + 2차 HOLD 시 publish-with-warning.
    8. 시각 issue HOLD 후 재캡쳐 → Desk 재호출.
    9. YK 캡쳐 → 텔레그램 → AI 재작성 사이클 ≤ 5건/30일 — 운영 측정.

본 모듈은 #2 (KILL_RULES) + #4 (Playwright graceful) + #7 (HOLD dispatch)
+ visual rubric SSOT 정합성을 결정적으로 검증.
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.agents.desk_editor import (
    HOLD_DISPATCH,
    SYSTEM_PROMPT,
    DeskIssue,
    DeskVerdict,
    dispatch_hold_action,
    evaluate_auto_kill,
    run_logical_kill_rules,
    run_visual_kill_rules,
)
from src.visual.capture import (
    ScreenshotCapture,
    capture_proofs,
    is_playwright_available,
)


# ─── DeskVerdict / DeskIssue 모델 ─────────────────────────────────


def test_desk_verdict_decision_3_enum() -> None:
    """Plan §16.2 — decision 의 3종 enum (publish/hold/kill)."""
    from typing import get_args
    actual = set(get_args(DeskVerdict.model_fields["decision"].annotation))
    assert actual == {"publish", "hold", "kill"}


def test_desk_issue_severity_3_enum() -> None:
    from typing import get_args
    actual = set(get_args(DeskIssue.model_fields["severity"].annotation))
    assert actual == {"minor", "major", "blocker"}


def test_desk_issue_domain_2_enum() -> None:
    from typing import get_args
    actual = set(get_args(DeskIssue.model_fields["domain"].annotation))
    assert actual == {"logical", "visual"}


# ─── Plan §16.6 Logical KILL_RULES 5종 ───────────────────────────


def test_logical_kill_insufficient_sources() -> None:
    composed = {"sources": ["http://only-one.com"], "sections": [{"prose": "x" * 5000}]}
    triggered = run_logical_kill_rules(composed, mode="standard")
    assert "insufficient_sources" in triggered


def test_logical_kill_insufficient_prose() -> None:
    composed = {
        "sources": ["a", "b"],
        "sections": [{"prose": "very short"}],   # 짧음 (10자 < 1750)
    }
    triggered = run_logical_kill_rules(composed, mode="standard")
    assert "insufficient_prose" in triggered


def test_logical_kill_contradiction_overload() -> None:
    composed = {
        "sources": ["a", "b"],
        "sections": [{"prose": "x" * 5000}, {"prose": "y" * 5000}],
        "contradictions": [
            {"side_a": "a", "side_b": "b"},
            {"side_a": "c", "side_b": "d"},
        ],   # 2 > 2/2 = 1
    }
    triggered = run_logical_kill_rules(composed, mode="standard")
    assert "contradiction_overload" in triggered


def test_logical_kill_watch_signals_useless_empty() -> None:
    composed = {
        "sources": ["a", "b"], "sections": [{"prose": "x" * 5000}],
        "watch_signals": [],
    }
    triggered = run_logical_kill_rules(composed, mode="standard")
    assert "watch_signals_useless" in triggered


def test_logical_kill_watch_signals_all_ambiguous() -> None:
    composed = {
        "sources": ["a", "b"], "sections": [{"prose": "x" * 5000}],
        "watch_signals": [
            {"signal": "x", "direction": "ambiguous"},
            {"signal": "y", "direction": "ambiguous"},
        ],
    }
    triggered = run_logical_kill_rules(composed, mode="standard")
    assert "watch_signals_useless" in triggered


def test_logical_kill_clean_passes() -> None:
    """모든 게이트 통과 시 triggered 빈 list."""
    composed = {
        "sources": ["a", "b", "c"],
        "sections": [{"prose": "x" * 4000}, {"prose": "y" * 4000}],
        "contradictions": [{"side_a": "a", "side_b": "b"}],
        "watch_signals": [
            {"signal": "x", "direction": "confirms_base"},
            {"signal": "y", "direction": "rejects_base"},
        ],
    }
    triggered = run_logical_kill_rules(composed, mode="standard")
    assert triggered == []


# ─── Plan §16.6 Visual KILL_RULES 3종 ───────────────────────────


def test_visual_kill_majority_charts_broken() -> None:
    triggered = run_visual_kill_rules(
        {"mobile_responsive": 5, "color_consistency": 5},
        chart_total=4, chart_visual_fail_count=2,    # 50% fail
    )
    assert "majority_charts_visually_broken" in triggered


def test_visual_kill_mobile_layout_broken() -> None:
    triggered = run_visual_kill_rules(
        {"mobile_responsive": 1, "color_consistency": 5},
    )
    assert "mobile_layout_broken" in triggered


def test_visual_kill_theme_token_mismatch() -> None:
    triggered = run_visual_kill_rules(
        {"mobile_responsive": 5, "color_consistency": 1},
    )
    assert "theme_token_mismatch" in triggered


def test_visual_kill_clean_passes() -> None:
    triggered = run_visual_kill_rules(
        {"mobile_responsive": 5, "color_consistency": 5},
        chart_total=4, chart_visual_fail_count=0,
    )
    assert triggered == []


# ─── 자동 KILL 통합 (Plan §16.6 — 둘 이상) ───────────────────────


def test_auto_kill_triggers_when_two_rules_fire() -> None:
    """Plan §16.6 — *둘 이상* 충족 시 자동 KILL."""
    composed = {
        "sources": ["a"],   # insufficient_sources (Logical 1)
        "sections": [{"prose": "very short"}],   # insufficient_prose (Logical 2)
        "watch_signals": [],   # 추가 trigger
    }
    visual_scores = {"mobile_responsive": 5, "color_consistency": 5}
    should_kill, triggered = evaluate_auto_kill(composed, visual_scores)
    assert should_kill is True
    assert len(triggered) >= 2


def test_auto_kill_does_not_trigger_with_only_one_rule() -> None:
    """1종만 발화 시 KILL 아님 (DeskEditor LLM 판정 영역)."""
    composed = {
        "sources": ["a"],   # insufficient_sources (1종만)
        "sections": [{"prose": "x" * 5000}],
        "watch_signals": [{"signal": "x", "direction": "confirms_base"}],
        "contradictions": [],
    }
    visual_scores = {"mobile_responsive": 5, "color_consistency": 5}
    should_kill, triggered = evaluate_auto_kill(composed, visual_scores)
    # 단 1종 (insufficient_sources) 만 발화 → KILL 아님.
    assert should_kill is False
    assert len(triggered) == 1


def test_auto_kill_logical_visual_combination() -> None:
    """Logical 1 + Visual 1 = 2 → KILL."""
    composed = {
        "sources": ["a"],   # Logical 1
        "sections": [{"prose": "x" * 5000}],
        "watch_signals": [{"signal": "x", "direction": "confirms_base"}],
        "contradictions": [],
    }
    visual_scores = {"mobile_responsive": 1, "color_consistency": 5}   # Visual 1
    should_kill, triggered = evaluate_auto_kill(composed, visual_scores)
    assert should_kill is True
    assert "insufficient_sources" in triggered
    assert "mobile_layout_broken" in triggered


# ─── Plan §16.8 — HOLD_DISPATCH 매트릭스 ───────────────────────


def test_hold_dispatch_logical_actions() -> None:
    """Logical issue 의 HOLD 분기 — composer/editor/chart_critic."""
    assert dispatch_hold_action("rewrite_headline") == ("composer", "headline_only")
    assert dispatch_hold_action("rewrite_conclusion") == ("editor", "section_last")
    assert dispatch_hold_action("drop_chart_N") == ("chart_critic", "force_drop")


def test_hold_dispatch_visual_actions() -> None:
    """Visual issue 의 HOLD 분기 — renderer/chart_critic/layout/visual_planner."""
    assert dispatch_hold_action("rerender_chart") == ("renderer", "chart_only")
    assert dispatch_hold_action("adjust_map_zoom_center") == ("visual_planner", "map_only")
    assert dispatch_hold_action("major_layout_revision") == ("layout", "full_rerun")


def test_hold_dispatch_unknown_returns_none() -> None:
    assert dispatch_hold_action("totally_made_up_action") is None


def test_hold_dispatch_covers_all_actions() -> None:
    """HOLD_DISPATCH 가 17종 이상 action 커버 (Plan §16.8)."""
    # Logical 9 + Visual 8 = 17.
    assert len(HOLD_DISPATCH) >= 17


# ─── Plan §16.5 — Playwright capture (graceful skip) ─────────────


def test_capture_proofs_returns_empty_when_html_missing() -> None:
    """미존재 HTML 경로 → 빈 list (graceful)."""
    captures = capture_proofs("/nonexistent/path/report.html")
    assert captures == []


def test_capture_proofs_returns_empty_when_playwright_missing() -> None:
    """Playwright 미설치 환경 → 빈 list."""
    if is_playwright_available():
        pytest.skip("Playwright 설치됨 — fallback 경로 테스트 불가")
    # capture_proofs 가 어떤 경로든 빈 list.
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        f.write(b"<html></html>")
        path = f.name
    captures = capture_proofs(path)
    assert captures == []


def test_screenshot_capture_dataclass() -> None:
    """Plan §16.2 의 ScreenshotCapture 모델 형식."""
    cap = ScreenshotCapture(
        role="desktop_full",
        image_b64="base64encoded",
        label="test",
        width=1280,
        height=800,
    )
    assert cap.role == "desktop_full"
    assert cap.width == 1280


# ─── SYSTEM_PROMPT 정합성 — Plan §16.3 + §16.4 ──────────────────


def test_system_prompt_contains_logical_7_rubric() -> None:
    """Plan §16.3 의 7-rubric 항목 모두 명시."""
    expected_keywords = [
        "Headline-Body 정합", "Deck-Conclusion 정합",
        "섹션 흐름의 수렴성", "차트 횡적 중복",
        "Watch_signal 의 예측력", "출처-주장 비율", "Smell test",
    ]
    for kw in expected_keywords:
        assert kw in SYSTEM_PROMPT, f"SYSTEM_PROMPT 에 '{kw}' 누락"


def test_system_prompt_includes_visual_rubric() -> None:
    """SYSTEM_PROMPT 가 docs/DESK_VISUAL_RUBRIC.md 의 §1 (8-rubric) 포함."""
    expected = [
        "(시각-1)", "(시각-2)", "(시각-3)", "(시각-4)",
        "(시각-5)", "(시각-6)", "(시각-7)", "(시각-8)",
    ]
    for label in expected:
        assert label in SYSTEM_PROMPT, (
            f"SYSTEM_PROMPT 에 visual rubric '{label}' 누락 — "
            f"docs/DESK_VISUAL_RUBRIC.md 의 §1 8-rubric 정합성 깨짐"
        )


def test_system_prompt_publish_hold_kill_authority() -> None:
    """Plan §1.1 — publish/hold/KILL 권한 명시."""
    assert "publish" in SYSTEM_PROMPT.lower()
    assert "hold" in SYSTEM_PROMPT.lower()
    assert "KILL" in SYSTEM_PROMPT


def test_system_prompt_json_response_schema() -> None:
    """SYSTEM_PROMPT 의 JSON 응답 스키마 명시."""
    assert "logical_rubric_scores" in SYSTEM_PROMPT
    assert "visual_rubric_scores" in SYSTEM_PROMPT
    assert "auto_kill" in SYSTEM_PROMPT.lower() or "kill_reason" in SYSTEM_PROMPT


# ─── DESK_VISUAL_RUBRIC.md SSOT 형식 검증 ──────────────────────


def test_desk_visual_rubric_md_exists() -> None:
    """docs/DESK_VISUAL_RUBRIC.md 가 존재 + §1 8-rubric 포함."""
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent.parent / "docs" / "DESK_VISUAL_RUBRIC.md"
    assert p.exists(), "docs/DESK_VISUAL_RUBRIC.md 미존재"

    content = p.read_text(encoding="utf-8")
    # §1 8-rubric 항목.
    for i in range(1, 9):
        assert f"(시각-{i})" in content, f"§1 (시각-{i}) 누락"


def test_desk_visual_rubric_md_has_append_only_section() -> None:
    """§2 append-only 섹션 존재."""
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent.parent / "docs" / "DESK_VISUAL_RUBRIC.md"
    content = p.read_text(encoding="utf-8")
    assert "append-only" in content
    assert "AP-V5-16" in content
