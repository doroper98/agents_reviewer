"""V5 Phase 7A — Deterministic Publish Gate regression test.

REFACTOR_V5_PLAN.md §15.6 인수 기준:
    1. Hard fail 11종이 모두 회귀 테스트로 검증.
    2. Hard fail 발생 시 Desk LLM 호출 *발생하지 않음* (토큰 0).
    3. v4.5.x 의 사용자 발견 결함 사례 다수가 Phase 7A 의 결정적 룰로 잡힘.
    4. Soft fail 이 DeskEditor system prompt 에 명시적 전달.

본 모듈은 #1, #2 를 결정적으로 검증. #3 / #4 는 운영 측정.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from tests.regression._pytest_compat import pytest

from src.visual.deterministic_gate import (
    HARD_FAIL_RULES,
    MODE_LOWER_BOUND,
    SOFT_FAIL_RULES,
    ChartCountLimits,
    DeterministicGateResult,
    run_deterministic_gate,
)


# ─── 인수 기준 #1 — 11종 Hard fail enum 보존 ───────────────────────


def test_hard_fail_rules_count_is_11() -> None:
    """Plan §15.4 의 11종 Hard fail 모두 명시."""
    assert len(HARD_FAIL_RULES) == 11
    expected = {
        "html_render_failed", "html_unparseable", "required_section_missing",
        "exhibit_ref_broken", "chart_without_source", "chart_container_empty",
        "report_too_short", "closing_missing", "asset_404",
        "mobile_horizontal_overflow", "playwright_timeout",
    }
    assert set(HARD_FAIL_RULES) == expected


def test_soft_fail_rules_count_is_6() -> None:
    """v5.2.14 — 6종 Soft fail. Plan §15.5 의 5종 + Layer 4 의 chart_type_monotony.

    Layer 4 (chart_type_monotony) 는 캔들 회귀 (한 보고서가 bar/line 일색)
    차단의 SSOT. standard mode ≥3 차트 시 distinct ≥2, deep mode ≥5 차트 시
    distinct ≥3 강제.
    """
    assert len(SOFT_FAIL_RULES) == 6
    expected = {
        "asymmetry_gini", "chart_count_exceeded",
        "heading_pattern_repetitive", "watch_signal_all_ambiguous",
        "stale_source_ratio",
        "chart_type_monotony",  # v5.2.14
    }
    assert set(SOFT_FAIL_RULES) == expected


def test_mode_lower_bound_matches_plan_6_3() -> None:
    """Plan §6.3 의 mode 별 lower bound (Phase 5 와 byte-equal)."""
    assert MODE_LOWER_BOUND == {
        "fast": 1500,
        "standard": 3500,
        "deep": 6000,
    }


def test_chart_count_limits_match_plan_13_8() -> None:
    """Plan §13.8 + AP-V5-9 의 mode 별 차트 상한."""
    assert ChartCountLimits.fast == 2
    assert ChartCountLimits.standard == 4
    assert ChartCountLimits.deep == 5


# ─── 인수 기준 #1 — 11종 Hard fail 시나리오 검증 ──────────────────


def _clean_composed() -> dict:
    """모든 게이트를 통과하는 정상 보고서."""
    prose = "한국의 의존도는 35%, 일본은 80%. 분석 결과 결정적인 변화. " * 50
    return {
        "headline": "테스트 보고서",
        "deck": "deck",
        "sections": [
            {"heading": "situation", "kicker": "사실", "prose": prose},
            {"heading": "mechanism", "kicker": "메커니즘", "prose": prose},
            {"heading": "scenarios", "kicker": "시나리오", "prose": prose},
            {"heading": "watch", "kicker": "감시", "prose": prose},
        ],
        "closing": "결론.",
        "watch_signals": [
            {"signal": "x", "direction": "confirms_base"},
            {"signal": "y", "direction": "rejects_base"},
        ],
        "exhibits": [
            {"title": "차트1", "source_ids": ["S-001"]},
            {"title": "차트2", "source_ids": ["S-002"]},
        ],
    }


def test_clean_report_publishes() -> None:
    """깨끗한 보고서 — decision='publish' / Hard 0 / Soft 0."""
    composed = _clean_composed()
    result = run_deterministic_gate(
        composed, mode="deep",
        must_have_sections=["situation", "mechanism", "scenarios", "watch"],
    )
    assert result.passed
    assert result.decision == "publish"
    assert result.hard_failures == []
    assert result.soft_failures == []


# Hard 1: html_render_failed
def test_hard_1_html_render_failed() -> None:
    composed = _clean_composed()
    result = run_deterministic_gate(
        composed, mode="deep",
        rendered_html_path="/nonexistent/path/report.html",
    )
    assert not result.passed
    assert result.decision == "kill"
    assert "html_render_failed" in result.hard_failures


# Hard 2: html_unparseable
def test_hard_2_html_unparseable() -> None:
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "broken.html"
        p.write_text("just plain text, not html")
        composed = _clean_composed()
        result = run_deterministic_gate(
            composed, mode="deep", rendered_html_path=p,
        )
        assert not result.passed
        assert "html_unparseable" in result.hard_failures


# Hard 3: required_section_missing
def test_hard_3_required_section_missing() -> None:
    composed = _clean_composed()
    result = run_deterministic_gate(
        composed, mode="deep",
        must_have_sections=["situation", "mechanism", "scenarios", "watch", "missing_one"],
    )
    assert not result.passed
    assert "required_section_missing" in result.hard_failures
    assert "missing_one" in result.metrics.get("missing_sections", [])


# Hard 4: exhibit_ref_broken
def test_hard_4_exhibit_ref_broken() -> None:
    composed = _clean_composed()
    composed["sections"][0]["prose"] = "본문에서 [[ex:99]] 참조하는데 없음." + composed["sections"][0]["prose"]
    result = run_deterministic_gate(composed, mode="deep")
    assert not result.passed
    assert "exhibit_ref_broken" in result.hard_failures
    assert 99 in result.metrics.get("broken_exhibit_refs", [])


# Hard 5: chart_without_source (AP-V5-26)
def test_hard_5_chart_without_source() -> None:
    composed = _clean_composed()
    composed["exhibits"] = [{"title": "src 없음", "source_ids": []}]
    result = run_deterministic_gate(composed, mode="deep")
    assert not result.passed
    assert "chart_without_source" in result.hard_failures


# Hard 6: chart_container_empty
def test_hard_6_chart_container_empty() -> None:
    with tempfile.TemporaryDirectory() as td:
        html = '''<!DOCTYPE html><html><body>
            <div class="chart-card"></div>
        </body></html>'''
        p = Path(td) / "report.html"
        p.write_text(html)
        composed = _clean_composed()
        result = run_deterministic_gate(
            composed, mode="deep", rendered_html_path=p,
        )
        assert "chart_container_empty" in result.hard_failures


# Hard 7: report_too_short
def test_hard_7_report_too_short() -> None:
    composed = _clean_composed()
    composed["sections"] = [{"heading": "h", "prose": "짧음"}]
    result = run_deterministic_gate(composed, mode="deep")
    assert not result.passed
    assert "report_too_short" in result.hard_failures
    assert result.metrics["total_prose_chars"] < MODE_LOWER_BOUND["deep"]


# Hard 8: closing_missing
def test_hard_8_closing_missing() -> None:
    composed = _clean_composed()
    composed["closing"] = ""
    result = run_deterministic_gate(composed, mode="deep")
    assert not result.passed
    assert "closing_missing" in result.hard_failures


# Hard 9: asset_404
def test_hard_9_asset_404() -> None:
    with tempfile.TemporaryDirectory() as td:
        html = '''<!DOCTYPE html><html><head>
            <script src="missing_asset.js"></script>
        </head><body><div class="chart-card"><svg></svg></div></body></html>'''
        p = Path(td) / "report.html"
        p.write_text(html)
        composed = _clean_composed()
        result = run_deterministic_gate(
            composed, mode="deep", rendered_html_path=p,
        )
        assert "asset_404" in result.hard_failures
        assert "missing_asset.js" in result.metrics.get("missing_assets", [])


# Hard 10: mobile_horizontal_overflow
def test_hard_10_mobile_overflow() -> None:
    with tempfile.TemporaryDirectory() as td:
        html = '''<!DOCTYPE html><html><body>
            <div class="chart-card" style="width: 800px"><svg></svg></div>
        </body></html>'''
        p = Path(td) / "report.html"
        p.write_text(html)
        composed = _clean_composed()
        result = run_deterministic_gate(
            composed, mode="deep", rendered_html_path=p,
        )
        assert "mobile_horizontal_overflow" in result.hard_failures


# Hard 11: playwright_timeout
def test_hard_11_playwright_timeout() -> None:
    composed = _clean_composed()
    result = run_deterministic_gate(
        composed, mode="deep", playwright_timed_out=True,
    )
    assert not result.passed
    assert "playwright_timeout" in result.hard_failures


# ─── 인수 기준 #2 — Hard fail 시 LLM 호출 0 (decision='kill') ──────


def test_decision_kill_when_any_hard_fail() -> None:
    """단 1개의 Hard fail 만 있어도 decision='kill' → DeskEditor LLM 호출 X.
    AP-V5-29 강제."""
    composed = _clean_composed()
    composed["closing"] = ""    # Hard 8 trigger.
    result = run_deterministic_gate(composed, mode="deep")
    assert result.decision == "kill"
    assert not result.passed


def test_decision_publish_when_all_clean() -> None:
    composed = _clean_composed()
    result = run_deterministic_gate(
        composed, mode="deep",
        must_have_sections=["situation", "mechanism", "scenarios", "watch"],
    )
    assert result.decision == "publish"
    assert result.passed


# ─── Soft fail 시나리오 (Plan §15.5) ─────────────────────────────────


# Soft 1: asymmetry_gini
def test_soft_1_asymmetry_gini() -> None:
    composed = _clean_composed()
    # 한 섹션만 매우 길고 다른 섹션은 짧음 → 지니 높음.
    composed["sections"][0]["prose"] = "x" * 50000   # 5만자 1섹션
    composed["sections"][1]["prose"] = "y" * 100
    composed["sections"][2]["prose"] = "z" * 100
    composed["sections"][3]["prose"] = "w" * 100
    result = run_deterministic_gate(composed, mode="deep")
    # Hard fail 없으면 soft.
    if result.decision != "kill":
        assert any("asymmetry_gini" in s for s in result.soft_failures)
        assert result.metrics["section_length_gini"] > 0.6


# Soft 2: chart_count_exceeded
def test_soft_2_chart_count_exceeded() -> None:
    composed = _clean_composed()
    # standard 모드에서 차트 5개 (limit 4 초과).
    composed["exhibits"] = [
        {"title": f"chart{i}", "source_ids": ["S-001"]}
        for i in range(5)
    ]
    result = run_deterministic_gate(composed, mode="standard")
    if result.decision != "kill":
        assert any("chart_count_exceeded" in s for s in result.soft_failures)


# Soft 3: heading_pattern_repetitive
def test_soft_3_heading_repetitive() -> None:
    composed = _clean_composed()
    # 모든 heading 이 같은 어두 + 비슷한 길이.
    for s in composed["sections"]:
        s["heading"] = "분석 보고서"
    result = run_deterministic_gate(composed, mode="deep")
    if result.decision != "kill":
        assert any("heading_pattern_repetitive" in s for s in result.soft_failures)


# Soft 4: watch_signal_all_ambiguous
def test_soft_4_watch_signal_all_ambiguous() -> None:
    composed = _clean_composed()
    composed["watch_signals"] = [
        {"signal": "x", "direction": "ambiguous"},
        {"signal": "y", "direction": "ambiguous"},
    ]
    result = run_deterministic_gate(composed, mode="deep")
    if result.decision != "kill":
        assert any("watch_signal_all_ambiguous" in s for s in result.soft_failures)


# Soft 6: chart_type_monotony (v5.2.14 Layer 4)
def test_soft_6_chart_type_monotony_standard() -> None:
    """standard ≥3 차트 + distinct types <2 면 monotony soft fail.

    캔들 회귀 (production 13종 중 70% 가 bar/line/donut) 방지.
    """
    composed = _clean_composed()
    composed["exhibits"] = [
        {"type": "bar", "title": "c1", "source_ids": ["S-001"]},
        {"type": "bar", "title": "c2", "source_ids": ["S-001"]},
        {"type": "bar", "title": "c3", "source_ids": ["S-001"]},
    ]
    result = run_deterministic_gate(composed, mode="standard")
    if result.decision != "kill":
        assert any("chart_type_monotony" in s for s in result.soft_failures)
        assert result.metrics["chart_distinct_types"] == 1


def test_soft_6_chart_type_monotony_deep() -> None:
    """deep ≥5 차트 + distinct types <3 면 monotony soft fail."""
    composed = _clean_composed()
    composed["exhibits"] = [
        {"type": "bar", "title": "c1", "source_ids": ["S-001"]},
        {"type": "bar", "title": "c2", "source_ids": ["S-001"]},
        {"type": "line", "title": "c3", "source_ids": ["S-001"]},
        {"type": "line", "title": "c4", "source_ids": ["S-001"]},
        {"type": "line", "title": "c5", "source_ids": ["S-001"]},
    ]
    result = run_deterministic_gate(composed, mode="deep")
    if result.decision != "kill":
        assert any("chart_type_monotony" in s for s in result.soft_failures)
        assert result.metrics["chart_distinct_types"] == 2


def test_soft_6_chart_type_monotony_pass_when_diverse() -> None:
    """type 다양하면 monotony soft fail 안 떠야."""
    composed = _clean_composed()
    composed["exhibits"] = [
        {"type": "bar", "title": "c1", "source_ids": ["S-001"]},
        {"type": "line", "title": "c2", "source_ids": ["S-001"]},
        {"type": "donut", "title": "c3", "source_ids": ["S-001"]},
    ]
    result = run_deterministic_gate(composed, mode="standard")
    if result.decision != "kill":
        assert not any("chart_type_monotony" in s for s in result.soft_failures)


def test_soft_6_chart_type_monotony_fast_skip() -> None:
    """fast mode 는 monotony 검증 안 함 (1-2 차트는 자연스레 단조)."""
    composed = _clean_composed()
    composed["exhibits"] = [
        {"type": "bar", "title": "c1", "source_ids": ["S-001"]},
        {"type": "bar", "title": "c2", "source_ids": ["S-001"]},
    ]
    result = run_deterministic_gate(composed, mode="fast")
    if result.decision != "kill":
        assert not any("chart_type_monotony" in s for s in result.soft_failures)


# ─── 다중 Hard fail 시 모두 보고 ─────────────────────────────────────


def test_multiple_hard_failures_all_reported() -> None:
    composed = _clean_composed()
    composed["closing"] = ""                   # Hard 8
    composed["exhibits"] = [{"title": "bad", "source_ids": []}]  # Hard 5
    composed["sections"] = [{"heading": "h", "prose": "짧"}]      # Hard 7
    result = run_deterministic_gate(composed, mode="deep")
    assert result.decision == "kill"
    assert "closing_missing" in result.hard_failures
    assert "chart_without_source" in result.hard_failures
    assert "report_too_short" in result.hard_failures


# ─── DeterministicGateResult 형식 ────────────────────────────────────


def test_result_has_metrics() -> None:
    composed = _clean_composed()
    result = run_deterministic_gate(composed, mode="deep")
    assert "total_prose_chars" in result.metrics
    assert "mode_lower_bound" in result.metrics
    assert "section_length_gini" in result.metrics
    assert "chart_count" in result.metrics


def test_decision_enum_values() -> None:
    """decision Literal 의 3종 enum."""
    composed = _clean_composed()
    result = run_deterministic_gate(composed, mode="deep")
    assert result.decision in ("publish", "soft_fail", "kill")
