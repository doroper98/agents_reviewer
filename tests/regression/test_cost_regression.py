"""V5 Phase 0B — Test 4/5: Cost Regression.

Plan §3.4 (라) — total input/output tokens, LLM call count, elapsed time,
retry count, hold/kill rate 를 매 실행마다 측정. v4.5.x 대비 토큰 폭주
(>2배) 시 fail.

Phase 0B 시점:
- ``RunTelemetry`` (src/telemetry.py) 에 LLM 호출별 토큰·시간 기록이 이미
  존재. 본 테스트는 그 telemetry JSON 을 입력으로 받아 *threshold 비교*.
- baseline_v4_5_7.json 에 record_baseline.py 가 v4.5.7 의 평균 cost 를
  박는다. 본 테스트는 V5 변경 후 동일 prompt 의 cost 가 baseline 의
  ≤ 2.0× 인지 검증.
- baseline 미녹화 시 SKIP — 다만 V5 의 인수 기준 (§22 의 #14) 이 본
  threshold 를 본격 활성화.

CLI runner: ``scripts/run_regression.py --tests cost``
"""

from __future__ import annotations

from typing import Any

from tests.regression._pytest_compat import pytest

from tests.regression.helpers import (
    BASELINE_PATH,
    RegressionResult,
    load_baseline,
    load_golden_prompts,
)


# ─── Threshold SSOT ────────────────────────────────────────────────────
#
# Plan §21 의 V5 비용 추정에 따라 *압축 후* 의 V5 비용은 v4.5.7 대비 +67~79%.
# 따라서 폭주 임계는 +100% (= 2.0×) 로 박는다 — Phase 0C 의 State Compaction
# 도입 후 Tier 1 의 인수 기준 (§22 #3) 이 *30% 이상 감소* 를 요구.

COST_THRESHOLDS = {
    "max_total_token_ratio": 2.0,    # V5 / v4.5.7 의 토큰 비율 상한.
    "max_llm_call_count": 12,        # Plan §1 의 신문사 모델 8 + DeskEditor + HOLD 재호출 등 최대치.
    "max_elapsed_seconds_factor": 3.0,  # 사용자 체감 — 3배 이상 느려지면 회귀.
}


# ─── 코어 검증 ──────────────────────────────────────────────────────────


def run_one(prompt_entry: dict[str, Any], telemetry: dict[str, Any] | None = None) -> RegressionResult:
    """단일 prompt 의 cost regression 검증.

    Args:
        prompt_entry: golden_prompts.yaml 의 한 entry.
        telemetry: ``RunTelemetry.export_dict()`` 또는 record_baseline 이
            남긴 cost 메트릭. None 이면 SKIP.
    """
    pid = prompt_entry["id"]
    issues: list[str] = []
    metrics: dict[str, Any] = {}

    if telemetry is None:
        metrics["status"] = "skipped_no_telemetry"
        return RegressionResult(
            test_name="cost_regression",
            prompt_id=pid,
            passed=True,
            issues=[],
            metrics=metrics,
        )

    baseline = load_baseline()
    base_results = baseline.get("results") or {}
    base_entry = base_results.get(pid)

    total_in = telemetry.get("total_input_tokens", 0)
    total_out = telemetry.get("total_output_tokens", 0)
    total_tokens = total_in + total_out
    metrics["total_input_tokens"] = total_in
    metrics["total_output_tokens"] = total_out
    metrics["total_tokens"] = total_tokens

    llm_calls = telemetry.get("llm_call_count", 0)
    metrics["llm_call_count"] = llm_calls
    elapsed = telemetry.get("total_elapsed_seconds", 0.0)
    metrics["total_elapsed_seconds"] = elapsed

    if llm_calls > COST_THRESHOLDS["max_llm_call_count"]:
        issues.append(
            f"llm_call_count_exceeded: {llm_calls} > "
            f"{COST_THRESHOLDS['max_llm_call_count']}"
        )

    # baseline 비교 — 미녹화면 통과 (informational only).
    if base_entry is not None:
        base_total = base_entry.get("total_tokens", 0)
        base_elapsed = base_entry.get("total_elapsed_seconds", 0.0)
        if base_total > 0:
            ratio = total_tokens / base_total
            metrics["token_ratio_vs_baseline"] = round(ratio, 2)
            if ratio > COST_THRESHOLDS["max_total_token_ratio"]:
                issues.append(
                    f"token_ratio_exceeded: {ratio:.2f}× > "
                    f"{COST_THRESHOLDS['max_total_token_ratio']}× "
                    f"(V5 변경 후 {total_tokens} vs baseline {base_total})"
                )
        if base_elapsed > 0 and elapsed > 0:
            efactor = elapsed / base_elapsed
            metrics["elapsed_ratio_vs_baseline"] = round(efactor, 2)
            if efactor > COST_THRESHOLDS["max_elapsed_seconds_factor"]:
                issues.append(
                    f"elapsed_factor_exceeded: {efactor:.2f}× > "
                    f"{COST_THRESHOLDS['max_elapsed_seconds_factor']}×"
                )

    return RegressionResult(
        test_name="cost_regression",
        prompt_id=pid,
        passed=not issues,
        issues=issues,
        metrics=metrics,
    )


def run_all(telemetry_by_id: dict[str, dict[str, Any]] | None = None) -> list[RegressionResult]:
    """모든 Golden Prompt 에 대해 run_one 실행.

    ``telemetry_by_id`` 가 None 이면 모두 SKIP.
    """
    telemetry_by_id = telemetry_by_id or {}
    return [
        run_one(entry, telemetry_by_id.get(entry["id"]))
        for entry in load_golden_prompts()
    ]


# ─── pytest 통합 ────────────────────────────────────────────────────────


def test_thresholds_match_plan() -> None:
    """COST_THRESHOLDS 가 Plan §21 의 추정과 정합."""
    # Plan §21 의 V5 deep 모드 추정 비용은 v4.5.7 대비 +67%. 2.0× 미만.
    assert COST_THRESHOLDS["max_total_token_ratio"] >= 1.67, (
        "Plan §21 의 deep 모드 +67% 추정을 허용해야 함"
    )
    assert COST_THRESHOLDS["max_total_token_ratio"] < 3.0, (
        "2배 초과는 폭주 — V5 의 어떤 단계도 그 이상 정당화 불가"
    )


def test_baseline_format_when_recorded() -> None:
    """baseline_v4_5_7.json 가 있을 때 형식 가드."""
    baseline = load_baseline()
    assert "recorded" in baseline, "baseline 에 recorded 플래그 필수"
    assert "version" in baseline, "baseline 에 version 필드 필수"
    if baseline.get("recorded"):
        assert "results" in baseline, "recorded baseline 은 results 필드 필수"
        for pid, entry in (baseline["results"] or {}).items():
            assert "total_tokens" in entry, f"{pid}: total_tokens 필드 필수"


def test_baseline_path_writable() -> None:
    """baseline 파일이 쓰기 가능한 위치인지 (디렉토리 존재 검증)."""
    assert BASELINE_PATH.parent.exists(), (
        f"baseline 디렉토리 {BASELINE_PATH.parent} 가 없음 — fixture 디렉토리 회귀"
    )


@pytest.mark.parametrize("entry", load_golden_prompts(), ids=lambda e: e["id"])
def test_cost_regression_skipped_without_telemetry(entry: dict[str, Any]) -> None:
    """Phase 0B 시점 — telemetry 없으면 SKIP, 형식만 가드."""
    result = run_one(entry, telemetry=None)
    assert result.passed
    assert result.metrics.get("status") == "skipped_no_telemetry"


def test_call_count_violation_detected() -> None:
    """llm_call_count > 12 시 fail 판정 회귀 가드."""
    sample_entry = {
        "id": "synthetic_cost_test",
        "prompt": "테스트",
        "expected": {},
    }
    bad_telemetry = {
        "total_input_tokens": 1000,
        "total_output_tokens": 500,
        "llm_call_count": 99,  # 임계 초과
        "total_elapsed_seconds": 30.0,
    }
    result = run_one(sample_entry, telemetry=bad_telemetry)
    assert not result.passed
    assert any("llm_call_count_exceeded" in i for i in result.issues)
