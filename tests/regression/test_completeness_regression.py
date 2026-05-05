"""V5 Phase 0B — Test 5/5: Report Completeness Regression.

Plan §3.4 (마) — total chars by mode, section target vs actual, closing
존재 여부, unresolved placeholder count, JSON truncation 검출. GAP-9
(보고서 절단) 의 회귀 사례를 자동으로 잡는다.

본 테스트의 핵심은 ``helpers.detect_truncation`` 의 5종 시그널 — Plan §6.4
의 결정적 절단 검출이 이미 helpers 에 박혀 있어 본 모듈은 *Golden Prompt
별 적용 + threshold 검증* 만 한다.

Phase 0B 시점:
- sample 미녹화면 SKIP.
- v4.5.x 의 알려진 절단 사례 (deep 모드 32K 한도) 가 발생하면 즉시 fail.
- 본격 회귀 검증은 사용자가 record_baseline.py 로 v4.5.7 sample 채운 후.

CLI runner: ``scripts/run_regression.py --tests completeness``
"""

from __future__ import annotations

import re
from typing import Any

from tests.regression._pytest_compat import pytest

from tests.regression.helpers import (
    MODE_TARGET_CHARS_LOWER,
    RegressionResult,
    detect_truncation,
    load_golden_prompts,
    load_sample_composed_report,
    section_count,
    total_prose_chars,
)


# ─── Placeholder 패턴 (composer 가 emit 하면 안 되는 표식) ────────────────

UNRESOLVED_PLACEHOLDERS = [
    re.compile(r"TODO[:\s]"),
    re.compile(r"\[FILL[\s_-]+IN\]"),
    re.compile(r"\{\{[^}]+\}\}"),       # Jinja2 미치환 — 렌더 회귀
    re.compile(r"<UNRESOLVED>"),
    re.compile(r"\[\[ex:[a-zA-Z]"),     # V5 Phase 4 의 [[ex:N]] 미치환 — N 자리에 문자
]


# ─── 코어 검증 ──────────────────────────────────────────────────────────


def count_unresolved_placeholders(composed: dict[str, Any]) -> int:
    """모든 prose / closing / deck / headline 에서 placeholder 패턴 카운트."""
    fields = [
        composed.get("headline") or "",
        composed.get("deck") or "",
        composed.get("closing") or "",
    ]
    for s in composed.get("sections") or []:
        s = s or {}
        fields.extend([
            s.get("heading") or "",
            s.get("kicker") or "",
            s.get("lede") or "",
            s.get("prose") or "",
        ])
    text = "\n".join(fields)
    count = 0
    for pat in UNRESOLVED_PLACEHOLDERS:
        count += len(pat.findall(text))
    return count


def run_one(prompt_entry: dict[str, Any]) -> RegressionResult:
    pid = prompt_entry["id"]
    expected = prompt_entry["expected"]
    issues: list[str] = []
    metrics: dict[str, Any] = {}

    sample = load_sample_composed_report(pid)
    if sample is None:
        return RegressionResult(
            test_name="completeness_regression",
            prompt_id=pid,
            passed=True,
            issues=[],
            metrics={"sample_missing": True},
        )

    mode = expected["mode"]

    # 1. 절단 검출 (Plan §6.4 의 5종 시그널 일괄 적용)
    trunc = detect_truncation(sample, mode)
    metrics["truncated"] = trunc["truncated"]
    metrics["truncation_issues"] = trunc["issues"]
    if trunc["truncated"]:
        issues.append(f"truncation_detected: {trunc['reason']}")

    # 2. 총 자수 vs mode 별 하한
    chars = total_prose_chars(sample)
    metrics["total_prose_chars"] = chars
    metrics["mode_lower_bound"] = MODE_TARGET_CHARS_LOWER.get(mode, 0)
    # detect_truncation 이 이미 underweight 잡지만, expected.min_total_chars 는
    # *prompt 별로 더 엄격한* 임계 (지정학·금융 deep 은 6000 자로 박혀 있음).
    if chars < expected["min_total_chars"]:
        issues.append(
            f"total_chars_below_prompt_minimum: {chars} < "
            f"{expected['min_total_chars']} (prompt-specific threshold)"
        )

    # 3. closing 필드
    if not (sample.get("closing") or "").strip():
        # detect_truncation 이 이미 잡지만, sample 에 명시적으로.
        metrics["closing_present"] = False
    else:
        metrics["closing_present"] = True

    # 4. 섹션 수 범위 (Golden Prompt 와 동일하지만 Completeness 관점 — 빈 섹션 거절)
    sc = section_count(sample)
    metrics["section_count"] = sc
    lo, hi = expected["section_count_range"]
    if not (lo <= sc <= hi):
        issues.append(f"section_count_out_of_range: {sc} not in [{lo},{hi}]")
    # 빈 prose 섹션 카운트
    empty_sections = sum(
        1 for s in (sample.get("sections") or [])
        if not ((s or {}).get("prose") or "").strip()
    )
    metrics["empty_section_count"] = empty_sections
    if empty_sections > 0:
        issues.append(f"empty_section_present: {empty_sections}건")

    # 5. unresolved placeholder
    pcount = count_unresolved_placeholders(sample)
    metrics["unresolved_placeholder_count"] = pcount
    if pcount > 0:
        issues.append(f"unresolved_placeholder_present: {pcount}건")

    return RegressionResult(
        test_name="completeness_regression",
        prompt_id=pid,
        passed=not issues,
        issues=issues,
        metrics=metrics,
    )


def run_all() -> list[RegressionResult]:
    return [run_one(p) for p in load_golden_prompts()]


# ─── pytest 통합 ────────────────────────────────────────────────────────


def test_mode_target_chars_lower_matches_plan() -> None:
    """Plan §6.4 의 MODE_TARGET_CHARS_LOWER 와 helpers 의 SSOT 일치."""
    assert MODE_TARGET_CHARS_LOWER == {
        "fast": 1500,
        "standard": 3500,
        "deep": 6000,
    }, "Plan §6.3 의 mode 별 분량 가이드 변경 시 본 테스트 + helpers 함께 갱신"


@pytest.mark.parametrize("entry", load_golden_prompts(), ids=lambda e: e["id"])
def test_completeness_regression(entry: dict[str, Any]) -> None:
    if load_sample_composed_report(entry["id"]) is None:
        pytest.skip(f"{entry['id']}: sample 미녹화")
    result = run_one(entry)
    assert result.passed, (
        f"{entry['id']}: completeness regression failed — "
        + "; ".join(result.issues)
        + f" (metrics: {result.metrics})"
    )


def test_detect_truncation_json_parse_failed() -> None:
    """Plan §6.4 시그널 1 — composed is None."""
    r = detect_truncation(None, "deep", raw_response="...partial json")
    assert r["truncated"]
    assert r["reason"] == "json_parse_failed"
    assert r["raw_tail"] == "...partial json"


def test_detect_truncation_last_section_unfinished() -> None:
    """Plan §6.4 시그널 2 — 마지막 prose 가 문장부호 없이 끝남."""
    sample = {
        "sections": [
            {"prose": "첫 단락은 마침표로 끝난다."},
            {"prose": "둘째는 도중에 끊긴다는"},  # 문장부호 X
        ],
        "closing": "결론.",
        "watch_signals": [{"signal": "x"}],
        "contradictions": [{"side_a": "a", "side_b": "b"}],
    }
    # 자수도 충분하게 채워 underweight 회피
    sample["sections"][0]["prose"] = "첫 단락은 마침표로 끝난다." * 200
    sample["sections"][1]["prose"] = "둘째는 도중에 끊긴다는" * 200
    r = detect_truncation(sample, "deep")
    assert r["truncated"]
    assert "last_section_unfinished" in r["issues"]


def test_detect_truncation_closing_missing() -> None:
    """Plan §6.4 시그널 3 — closing 비어 있음."""
    sample = {
        "sections": [{"prose": "마침표로 끝남." * 500}],
        "closing": "",  # 비어있음
        "watch_signals": [{"signal": "x"}],
        "contradictions": [{"side_a": "a", "side_b": "b"}],
    }
    r = detect_truncation(sample, "deep")
    assert r["truncated"]
    assert "closing_missing" in r["issues"]


def test_detect_truncation_deep_mode_missing_signals() -> None:
    """Plan §6.4 시그널 4 — deep 에서 watch_signals/contradictions 비어있음."""
    sample = {
        "sections": [{"prose": "내용." * 1000}],
        "closing": "결론.",
        "watch_signals": [],
        "contradictions": [],
    }
    r = detect_truncation(sample, "deep")
    assert r["truncated"]
    assert "watch_signals_missing_in_deep" in r["issues"]
    assert "contradictions_missing_in_deep" in r["issues"]


def test_detect_truncation_underweight() -> None:
    """Plan §6.4 시그널 5 — 총 분량이 mode lower bound 의 70% 미만."""
    sample = {
        "sections": [{"prose": "짧은 본문."}],
        "closing": "끝.",
        "watch_signals": [{"signal": "x"}],
        "contradictions": [{"side_a": "a", "side_b": "b"}],
    }
    r = detect_truncation(sample, "deep")
    assert r["truncated"]
    assert any("underweight_" in i for i in r["issues"])


def test_detect_truncation_clean_pass() -> None:
    """완전한 보고서는 truncated=false."""
    prose = "이 문장은 마침표로 끝난다." * 400  # ~6400+ chars
    sample = {
        "sections": [
            {"prose": prose},
            {"prose": prose},
        ],
        "closing": "결론입니다.",
        "watch_signals": [{"signal": "x", "direction": "confirms_base"}],
        "contradictions": [{"side_a": "a", "side_b": "b"}],
    }
    r = detect_truncation(sample, "deep")
    assert not r["truncated"], f"clean sample should pass, got issues: {r['issues']}"


def test_unresolved_placeholders_detected() -> None:
    sample = {
        "headline": "보고서 TODO: 헤드라인 채워야 함",
        "deck": "",
        "closing": "",
        "sections": [{"prose": "내용에 [FILL_IN] 가 있고 {{var}} 미치환"}],
    }
    count = count_unresolved_placeholders(sample)
    assert count >= 3, f"expected ≥3 placeholders, got {count}"


def test_unresolved_placeholders_none() -> None:
    sample = {
        "headline": "정상 헤드라인",
        "deck": "정상 부제",
        "closing": "정상 결론",
        "sections": [{"prose": "정상 본문 내용"}],
    }
    assert count_unresolved_placeholders(sample) == 0
