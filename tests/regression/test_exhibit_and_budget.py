"""V5 Phase 4 + Phase 5 — Exhibit 번호제 + Word Budget regression test.

Plan §11.5 인수 기준 (Phase 4):
    - 본문 cross-ref 사례 보고서당 평균 1~3회.
    - exhibit 번호 충돌 / 미존재 ref 회귀 테스트 통과.

Plan §12.7 인수 기준 (Phase 5):
    - 같은 deep 사건의 섹션 분량 지니 계수가 v4.5.7 baseline 보다 0.10 증가.
    - 절단 검출이 회귀 사례 100% 잡음.
    - 연속 호출 후 절단 잔존율 ≤ 5%.
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.state.models import Exhibit
from src.visual.exhibit_numbering import (
    EXHIBIT_REF_PATTERN,
    EXHIBIT_REF_RANGE_PATTERN,
    assign_exhibit_ids,
    collect_exhibit_refs,
    count_exhibit_refs,
    resolve_exhibit_refs,
    resolve_exhibit_refs_html,
    validate_exhibit_refs,
)
from src.visual.word_budget import (
    COMPOSER_MAX_TOKENS_V5,
    MODE_BUDGET_BANDS,
    MODE_TARGET_CHARS_LOWER,
    TruncationStatus,
    adaptive_max_tokens,
    complexity_score_from_context,
    compute_word_budgets,
    detect_truncation,
    gini_coefficient,
    section_length_distribution,
    stitch_continuation,
)


# ════════════════════════════════════════════════════════════════
# Phase 4 — Exhibit 번호제
# ════════════════════════════════════════════════════════════════


# ─── 자동 번호 부여 (AP-V5-6) ────────────────────────────────────


def test_assign_exhibit_ids_overwrites_composer_value() -> None:
    """AP-V5-6 — composer / Editor 가 박은 exhibit_id 는 *덮어쓰임*."""
    exhibits = [
        {"title": "차트1", "exhibit_id": "999", "spec": {}},
        {"title": "차트2", "exhibit_id": "phantom", "spec": {}},
    ]
    out = assign_exhibit_ids(exhibits)
    assert out[0].exhibit_id == "1"
    assert out[1].exhibit_id == "2"


def test_assign_exhibit_ids_sequential_from_1() -> None:
    exhibits = [{"title": f"c{i}", "spec": {}} for i in range(5)]
    out = assign_exhibit_ids(exhibits)
    assert [e.exhibit_id for e in out] == ["1", "2", "3", "4", "5"]


def test_assign_exhibit_ids_empty() -> None:
    assert assign_exhibit_ids([]) == []


# ─── Cross-ref 치환 (Plan §11.3) ────────────────────────────────


def test_resolve_exhibit_refs_single() -> None:
    text = "본문은 [[ex:4]] 에서 보듯 분명하다."
    result = resolve_exhibit_refs(text, total_exhibits=10)
    assert "Exhibit 4" in result
    assert "[[ex:4]]" not in result


def test_resolve_exhibit_refs_parenthesis() -> None:
    text = "이 결과 [[exr:7]] 와 일치한다."
    result = resolve_exhibit_refs(text, total_exhibits=10)
    assert "(Exhibit 7 참조)" in result


def test_resolve_exhibit_refs_range() -> None:
    text = "[[exs:2-3]] 비교."
    result = resolve_exhibit_refs(text, total_exhibits=10)
    assert "Exhibits 2~3" in result


def test_resolve_exhibit_refs_range_tilde() -> None:
    text = "[[exs:5~7]] 종합."
    result = resolve_exhibit_refs(text, total_exhibits=10)
    assert "Exhibits 5~7" in result


def test_resolve_exhibit_refs_phantom_dropped() -> None:
    """미존재 exhibit ref 는 빈 문자열로 치환 (Phase 7A 가 추가 fail 처리)."""
    text = "본문 [[ex:99]] 인용."
    result = resolve_exhibit_refs(text, total_exhibits=5)
    assert "Exhibit 99" not in result


def test_resolve_exhibit_refs_html_anchor() -> None:
    text = "본문은 [[ex:4]] 참조."
    result = resolve_exhibit_refs_html(text, total_exhibits=10)
    assert 'href="#exhibit-4"' in result
    assert "Exhibit 4" in result


def test_resolve_exhibit_refs_html_range() -> None:
    text = "[[exs:2-3]] 비교"
    result = resolve_exhibit_refs_html(text, total_exhibits=10)
    assert 'href="#exhibit-2"' in result
    assert 'href="#exhibit-3"' in result


def test_resolve_exhibit_refs_empty() -> None:
    assert resolve_exhibit_refs("") == ""
    assert resolve_exhibit_refs("not a ref") == "not a ref"


# ─── Validation (Plan §11.5 + Phase 7A 결합) ────────────────────


def test_validate_exhibit_refs_all_valid() -> None:
    composed = {
        "exhibits": [{"title": "c1"}, {"title": "c2"}, {"title": "c3"}],
        "sections": [
            {"prose": "본문 [[ex:1]] 인용."},
            {"prose": "추가 [[exr:2]] 와 [[exs:1-3]] 비교."},
        ],
    }
    valid, broken = validate_exhibit_refs(composed)
    assert valid
    assert broken == []


def test_validate_exhibit_refs_phantom() -> None:
    composed = {
        "exhibits": [{"title": "c1"}],
        "sections": [
            {"prose": "본문 [[ex:99]] 인용."},
        ],
    }
    valid, broken = validate_exhibit_refs(composed)
    assert not valid
    assert 99 in broken


def test_collect_exhibit_refs_mixed() -> None:
    text = "본문 [[ex:4]] + [[exr:7]] + [[exs:2-5]]."
    refs = collect_exhibit_refs(text)
    # ex:4 + exr:7 + exs:2-5 = {2,3,4,5,7}
    assert refs == {2, 3, 4, 5, 7}


def test_count_exhibit_refs_density() -> None:
    composed = {
        "exhibits": [{"title": f"c{i}"} for i in range(5)],
        "sections": [
            {"prose": "[[ex:1]] [[ex:2]] [[ex:3]]"},
            {"prose": "[[ex:1]] [[exr:4]]"},
        ],
    }
    stats = count_exhibit_refs(composed)
    # ref 5건 (1,2,3,1,4) 중 unique 4개
    assert stats["total_refs"] == 5
    assert stats["unique_exhibits_referenced"] == 4
    assert stats["n_exhibits"] == 5
    # density = 5 / 5 = 1.0 (Plan §11.5 의 1~3 권장 안)
    assert stats["ref_density"] == 1.0


# ─── 정규식 SSOT ─────────────────────────────────────────────────


def test_exhibit_ref_pattern_matches_ex_and_exr() -> None:
    assert EXHIBIT_REF_PATTERN.search("[[ex:1]]")
    assert EXHIBIT_REF_PATTERN.search("[[exr:1]]")
    assert not EXHIBIT_REF_PATTERN.search("[[exs:1-2]]")  # range 패턴 아님


def test_exhibit_ref_range_pattern_dash_or_tilde() -> None:
    assert EXHIBIT_REF_RANGE_PATTERN.search("[[exs:1-3]]")
    assert EXHIBIT_REF_RANGE_PATTERN.search("[[exs:5~7]]")


# ════════════════════════════════════════════════════════════════
# Phase 5 — Word Budget + 절단 검출
# ════════════════════════════════════════════════════════════════


# ─── SSOT Threshold ──────────────────────────────────────────────


def test_mode_target_chars_lower_byte_equal_with_helpers() -> None:
    """tests/regression/helpers.py 와 byte-equal — Plan §6.4 SSOT."""
    from tests.regression.helpers import MODE_TARGET_CHARS_LOWER as HELPERS_BOUND
    assert MODE_TARGET_CHARS_LOWER == HELPERS_BOUND


def test_mode_budget_bands_3_modes() -> None:
    """Plan §12.3 — 3 mode."""
    assert set(MODE_BUDGET_BANDS.keys()) == {"fast", "standard", "deep"}
    for mode in ("fast", "standard", "deep"):
        band = MODE_BUDGET_BANDS[mode]
        assert "total_min" in band
        assert "section_count_min" in band
        assert "peak_target" in band


def test_composer_max_tokens_v5_byte_equal_plan_12_6() -> None:
    """Plan §12.6 byte-equal — fast 16K~24K / std 28K~40K / deep 48K~64K."""
    assert COMPOSER_MAX_TOKENS_V5["fast"] == {"base": 16000, "max": 24000}
    assert COMPOSER_MAX_TOKENS_V5["standard"] == {"base": 28000, "max": 40000}
    assert COMPOSER_MAX_TOKENS_V5["deep"] == {"base": 48000, "max": 64000}


def test_deep_max_tokens_exceeds_v4_5_7_limit() -> None:
    """v4.5.7 의 deep 32K 한계 → V5 의 64K — Plan §12.6 의 핵심 개선."""
    assert COMPOSER_MAX_TOKENS_V5["deep"]["max"] == 64000
    assert COMPOSER_MAX_TOKENS_V5["deep"]["base"] >= 32000   # v4.5.7 단일 한도 이상


# ─── 절단 검출 (Plan §12.4) ──────────────────────────────────────


def test_detect_truncation_json_parse_failed() -> None:
    status = detect_truncation(None, "deep", raw_response="...partial")
    assert status.truncated
    assert status.reason == "json_parse_failed"
    assert status.raw_tail == "...partial"


def test_detect_truncation_last_section_unfinished() -> None:
    composed = {
        "sections": [{"prose": "첫 단락 끝남."}, {"prose": "중간에 끊긴다는"}],
        "closing": "결론.",
        "watch_signals": [{"x": 1}], "contradictions": [{"a": 1}],
    }
    composed["sections"][0]["prose"] = "x" * 5000
    composed["sections"][1]["prose"] = "y" * 5000   # 마침표 없음
    status = detect_truncation(composed, "deep")
    assert status.truncated
    assert "last_section_unfinished" in status.issues


def test_detect_truncation_clean_passes() -> None:
    composed = {
        "sections": [{"prose": "마침표로 끝." * 1000}],
        "closing": "결론.",
        "watch_signals": [{"x": 1, "direction": "confirms_base"}],
        "contradictions": [{"side_a": "a", "side_b": "b"}],
    }
    status = detect_truncation(composed, "deep")
    assert not status.truncated


def test_detect_truncation_underweight() -> None:
    composed = {
        "sections": [{"prose": "짧은 본문."}],
        "closing": "끝.",
        "watch_signals": [{}], "contradictions": [{}],
    }
    status = detect_truncation(composed, "deep")
    assert status.truncated
    assert any("underweight" in i for i in status.issues)


# ─── 적응형 max_tokens (Plan §12.6) ─────────────────────────────


def test_adaptive_max_tokens_low_complexity_returns_base() -> None:
    """복잡도 0 — base 토큰."""
    assert adaptive_max_tokens("deep", 0.0) == 48000


def test_adaptive_max_tokens_high_complexity_returns_max() -> None:
    """복잡도 ≥ 50 — max 토큰."""
    assert adaptive_max_tokens("deep", 50.0) == 64000
    assert adaptive_max_tokens("deep", 100.0) == 64000   # cap


def test_adaptive_max_tokens_interpolates() -> None:
    """복잡도 25 — base 와 max 사이 보간."""
    val = adaptive_max_tokens("deep", 25.0)
    assert 48000 < val < 64000


def test_complexity_score_from_context_dict() -> None:
    """Plan §12.6 가중합 — sources*2 + timeline*1.5 + key_figures."""
    context = {
        "sources": ["a", "b", "c"],          # 3 × 2 = 6
        "timeline": [{}, {}, {}, {}],         # 4 × 1.5 = 6
        "key_figures": [{}, {}],              # 2
    }
    score = complexity_score_from_context(context)
    assert score == 14.0


# ─── compute_word_budgets (Plan §12.3) ──────────────────────────


def test_compute_word_budgets_deep_5_sections() -> None:
    budgets = compute_word_budgets(5, "deep", peak_section_idx=2)
    assert len(budgets) == 5
    assert budgets[2].is_peak
    assert budgets[2].target_chars == 2200      # peak_target deep
    assert budgets[2].role == "main"
    # 마지막 섹션 = watch.
    assert budgets[-1].role == "watch"


def test_compute_word_budgets_fast_even_distribution() -> None:
    budgets = compute_word_budgets(3, "fast")
    # fast 는 균등.
    target_chars = [b.target_chars for b in budgets]
    # peak 는 700, 나머지는 평균.
    assert max(target_chars) == 700


def test_compute_word_budgets_zero() -> None:
    assert compute_word_budgets(0, "deep") == []


def test_compute_word_budgets_default_peak_at_middle() -> None:
    budgets = compute_word_budgets(5, "standard")
    # peak_section_idx None → 절반 = 2
    assert budgets[2].is_peak


# ─── 분량 비대칭 — gini (Plan §12.7 인수 기준) ─────────────────


def test_gini_coefficient_uniform_zero() -> None:
    assert gini_coefficient([100.0, 100.0, 100.0]) == pytest.approx(0.0, abs=0.01)


def test_gini_coefficient_concentrated_high() -> None:
    """1개 섹션에 모든 분량 집중 → gini ~0.7+."""
    g = gini_coefficient([1000.0, 50.0, 50.0, 50.0, 50.0])
    assert g > 0.5


def test_gini_coefficient_empty() -> None:
    assert gini_coefficient([]) == 0.0
    assert gini_coefficient([0.0, 0.0]) == 0.0


def test_section_length_distribution() -> None:
    composed = {
        "sections": [
            {"prose": "a" * 1000}, {"prose": "b" * 2000},
            {"prose": "c" * 500}, {"prose": "d" * 1500},
        ],
    }
    dist = section_length_distribution(composed)
    assert dist["section_count"] == 4
    assert dist["total_chars"] == 5000
    assert dist["min_chars"] == 500
    assert dist["max_chars"] == 2000


# ─── Stitching (Plan §12.5) ─────────────────────────────────────


def test_stitch_continuation_appends_new_sections() -> None:
    partial = {
        "sections": [
            {"heading": "도입", "prose": "끝."},
            {"heading": "본론", "prose": "중간에 끊"},
        ],
        "closing": "",
    }
    continuation = {
        "sections": [
            {"heading": "본론", "prose": "어진다는 부분의 이어 작성."},
            {"heading": "결론", "prose": "마지막 결론."},
        ],
        "closing": "최종 결론.",
    }
    out = stitch_continuation(partial, continuation)
    # 마지막 미완성 섹션이 결합됨.
    assert "이어 작성" in out["sections"][1]["prose"]
    # 새 섹션 추가됨.
    assert any(s.get("heading") == "결론" for s in out["sections"])
    # closing 갱신.
    assert out["closing"] == "최종 결론."


def test_stitch_continuation_none_returns_partial() -> None:
    partial = {"sections": [{"heading": "x", "prose": "y"}]}
    out = stitch_continuation(partial, None)
    assert out == partial


def test_stitch_continuation_preserves_watch_signals() -> None:
    partial = {
        "sections": [{"heading": "x", "prose": "y"}],
        "watch_signals": [{"signal": "p"}],
    }
    continuation = {
        "sections": [],
        "watch_signals": [{"signal": "q"}, {"signal": "r"}],
    }
    out = stitch_continuation(partial, continuation)
    # continuation 의 watch_signals 가 우선 (있을 시).
    assert len(out["watch_signals"]) == 2
