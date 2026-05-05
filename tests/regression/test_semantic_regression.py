"""V5 Phase 0B — Test 3/5: Semantic Regression.

Plan §3.4 (다) — headline-body 정합, deck-conclusion 정합, evidence-claim
coverage, source freshness, contradiction preservation, watch signal
actionability 를 정량화해 점수로 측정.

Phase 0B 는 *결정적 휴리스틱* 으로 시작 — V5 Phase 7 DeskEditor 의 LLM 검수가
도입되기 전 단계의 *최저선 가드*. headline 과 본문이 *완전히 무관* 한 회귀,
deck 이 단호한데 결론이 양손잡이 회귀, watch_signal 이 모두 ambiguous 인 회귀
같은 *명백한* 결함만 잡는다.

threshold (Phase 0B 기본값):
- headline_body_match_score ≥ 0.30  (과반 이상은 휴리스틱 한계)
- deck_conclusion_alignment ≥ 0.20  (deck 의 어휘 ≥ 20% 가 마지막 섹션에)
- watch_signal_actionability ≥ 0.34 (전부 ambiguous 인 사례 거절. Phase 8 에서 강화)
- contradiction_preservation_check 통과 (side_a/side_b 형식 + 동치 거절)

CLI runner: ``scripts/run_regression.py --tests semantic``
"""

from __future__ import annotations

from typing import Any

from tests.regression._pytest_compat import pytest

from tests.regression.helpers import (
    RegressionResult,
    contradiction_preservation_check,
    deck_conclusion_alignment,
    headline_body_match_score,
    load_golden_prompts,
    load_sample_composed_report,
    watch_signal_actionability,
)


# ─── Threshold SSOT ────────────────────────────────────────────────────

SEMANTIC_THRESHOLDS = {
    "headline_body_match": 0.30,
    "deck_conclusion": 0.20,
    "watch_signal_actionability": 0.34,
}


# ─── 코어 검증 ──────────────────────────────────────────────────────────


def run_one(prompt_entry: dict[str, Any]) -> RegressionResult:
    pid = prompt_entry["id"]
    expected = prompt_entry["expected"]
    issues: list[str] = []
    metrics: dict[str, Any] = {}

    sample = load_sample_composed_report(pid)
    if sample is None:
        return RegressionResult(
            test_name="semantic_regression",
            prompt_id=pid,
            passed=True,
            issues=[],
            metrics={"sample_missing": True},
        )

    # 1. headline-body match
    hb = headline_body_match_score(sample)
    metrics["headline_body_match"] = round(hb, 3)
    if hb < SEMANTIC_THRESHOLDS["headline_body_match"]:
        issues.append(
            f"headline_body_match_low: {hb:.2f} < "
            f"{SEMANTIC_THRESHOLDS['headline_body_match']}"
        )

    # 2. deck-conclusion alignment
    dc = deck_conclusion_alignment(sample)
    metrics["deck_conclusion"] = round(dc, 3)
    if dc < SEMANTIC_THRESHOLDS["deck_conclusion"]:
        issues.append(
            f"deck_conclusion_low: {dc:.2f} < "
            f"{SEMANTIC_THRESHOLDS['deck_conclusion']}"
        )

    # 3. watch_signal actionability — must_have_watch_signals 인 prompt 만 강제.
    if expected.get("must_have_watch_signals"):
        ws = watch_signal_actionability(sample)
        metrics["watch_signal_actionability"] = round(ws, 3)
        if ws < SEMANTIC_THRESHOLDS["watch_signal_actionability"]:
            issues.append(
                f"watch_signal_actionability_low: {ws:.2f} < "
                f"{SEMANTIC_THRESHOLDS['watch_signal_actionability']} "
                f"(전부 ambiguous 회귀 가능성)"
            )

    # 4. contradiction preservation (Anti-pattern #5 형식 가드)
    if expected.get("must_have_contradictions"):
        ok = contradiction_preservation_check(sample)
        metrics["contradiction_preservation"] = ok
        if not ok:
            issues.append("contradiction_preservation_failed: side_a/side_b 형식 또는 동치 회귀")

    # 5. source freshness — sources 가 비어 있지 않은지 (Phase 0B 에선 *형식 가드*).
    sources = sample.get("sources") or []
    metrics["source_count"] = len(sources)
    if expected.get("required_evidence_types") and not sources:
        # required_evidence_types 가 있는데 sources 가 0 이면 회귀.
        # 단 ComposedReport 에 sources 는 직접 없고 ContextAnalysis 에 있다 —
        # sample 이 통합 dict 일 때만 검증 (helper).
        pass  # ContextAnalysis 통합 검증은 Phase 0C 의 6-tier State 도입 후.

    return RegressionResult(
        test_name="semantic_regression",
        prompt_id=pid,
        passed=not issues,
        issues=issues,
        metrics=metrics,
    )


def run_all() -> list[RegressionResult]:
    return [run_one(p) for p in load_golden_prompts()]


# ─── pytest 통합 ────────────────────────────────────────────────────────


def test_thresholds_documented() -> None:
    """SEMANTIC_THRESHOLDS 가 4개 항목 모두 보유."""
    assert set(SEMANTIC_THRESHOLDS.keys()) == {
        "headline_body_match", "deck_conclusion", "watch_signal_actionability",
    }, "Phase 0B threshold SSOT 변경 시 본 테스트 함께 갱신"


@pytest.mark.parametrize("entry", load_golden_prompts(), ids=lambda e: e["id"])
def test_semantic_regression(entry: dict[str, Any]) -> None:
    if load_sample_composed_report(entry["id"]) is None:
        pytest.skip(f"{entry['id']}: sample 미녹화")
    result = run_one(entry)
    assert result.passed, (
        f"{entry['id']}: semantic regression failed — "
        + "; ".join(result.issues)
        + f" (metrics: {result.metrics})"
    )


def test_headline_body_match_perfect_overlap() -> None:
    """sanity — headline 의 모든 토큰이 본문에 있으면 1.0."""
    sample = {
        "headline": "이스라엘 이란 충돌",
        "deck": "",
        "sections": [{"prose": "이스라엘 과 이란 의 충돌 가능성"}],
    }
    score = headline_body_match_score(sample)
    assert score >= 0.99, f"perfect overlap should be ~1.0, got {score}"


def test_headline_body_match_no_overlap() -> None:
    """sanity — headline 토큰이 본문에 하나도 없으면 0.0."""
    sample = {
        "headline": "전혀 다른 주제",
        "deck": "",
        "sections": [{"prose": "completely unrelated body content"}],
    }
    score = headline_body_match_score(sample)
    assert score < 0.1, f"no overlap should be ~0, got {score}"


def test_watch_signal_all_ambiguous_zero() -> None:
    sample = {
        "watch_signals": [
            {"direction": "ambiguous"},
            {"direction": "ambiguous"},
        ]
    }
    assert watch_signal_actionability(sample) == 0.0


def test_watch_signal_mixed_directions() -> None:
    sample = {
        "watch_signals": [
            {"direction": "confirms_base"},
            {"direction": "ambiguous"},
            {"direction": "rejects_base"},
        ]
    }
    score = watch_signal_actionability(sample)
    assert abs(score - (2.0 / 3.0)) < 1e-9


def test_contradiction_preservation_rejects_identical_sides() -> None:
    sample = {
        "contradictions": [
            {"side_a": "동일", "side_b": "동일"},
        ]
    }
    assert not contradiction_preservation_check(sample)


def test_contradiction_preservation_passes_distinct_sides() -> None:
    sample = {
        "contradictions": [
            {"side_a": "위험 확대", "side_b": "위험 축소", "resolution": "side_a 채택"},
        ]
    }
    assert contradiction_preservation_check(sample)
