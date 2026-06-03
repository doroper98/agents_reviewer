"""V6 Phase V6-1 — FactVerdict / CritiqueClaim 계약 회귀 (T-V1).

REFACTOR_V6_PLAN.md §4.1 T-V1. Codex 외부 critic 의 구조화 verdict 계약을
검증한다. per-claim 필수필드 (location/error_class/quote/evidence_conflict/
fix_instruction/severity) 누락 시 *거부* + 근거(evidence_conflict) 미인용 지적
거부 (AP-V6-8). FactVerdict 의 degrade(skip)·status 정합도 함께 고정한다.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models import CritiqueClaim, FactVerdict


def _valid_claim_kwargs() -> dict:
    return {
        "location": "headline",
        "error_class": "unsourced_number",
        "quote": "27년 만의 PC 칩",
        "evidence_conflict": "공식 표현은 '30년'. '27년 만'은 출처에 없음.",
        "fix_instruction": "'27년 만' 을 빼고 '30년 기술' 로 교정.",
        "severity": "high",
    }


# --------------------------------------------------------------------------
# CritiqueClaim — per-claim 필수필드 강제 (T-V1)
# --------------------------------------------------------------------------


def test_valid_claim_constructs() -> None:
    claim = CritiqueClaim(**_valid_claim_kwargs())
    assert claim.severity == "high"
    assert claim.source_urls == []  # 선택 필드 기본값


@pytest.mark.parametrize(
    "missing",
    ["location", "error_class", "quote", "evidence_conflict", "fix_instruction", "severity"],
)
def test_missing_required_field_rejected(missing: str) -> None:
    kwargs = _valid_claim_kwargs()
    del kwargs[missing]
    with pytest.raises(ValidationError):
        CritiqueClaim(**kwargs)


@pytest.mark.parametrize(
    "blank", ["location", "error_class", "quote", "evidence_conflict", "fix_instruction"],
)
def test_empty_string_required_field_rejected(blank: str) -> None:
    """min_length=1 — 빈 문자열은 누락과 동일하게 거부 (AP-V6-8: 근거 없는 지적)."""
    kwargs = _valid_claim_kwargs()
    kwargs[blank] = ""
    with pytest.raises(ValidationError):
        CritiqueClaim(**kwargs)


def test_severity_must_be_enum() -> None:
    kwargs = _valid_claim_kwargs()
    kwargs["severity"] = "critical"  # enum 밖
    with pytest.raises(ValidationError):
        CritiqueClaim(**kwargs)


def test_source_urls_optional_but_evidence_conflict_grounds_claim() -> None:
    # AP-V6-8 — source_urls 가 비어도 evidence_conflict 가 근거를 대면 유효.
    claim = CritiqueClaim(**_valid_claim_kwargs())
    assert claim.evidence_conflict
    assert not claim.source_urls


# --------------------------------------------------------------------------
# FactVerdict — status 정합 + degrade
# --------------------------------------------------------------------------


def test_clean_verdict_when_no_claims() -> None:
    v = FactVerdict()
    assert v.verdict_status == "clean"
    assert v.violation_count == 0
    assert not v.is_actionable


def test_claims_force_violations_status() -> None:
    # codex 가 status 를 'clean' 으로 줘도 claims 있으면 violations 로 정규화.
    v = FactVerdict(verdict_status="clean", claims=[CritiqueClaim(**_valid_claim_kwargs())])
    assert v.verdict_status == "violations"
    assert v.is_actionable


def test_skip_classmethod_marks_skipped() -> None:
    v = FactVerdict.skip("rate_limited", latency_ms=1234)
    assert v.skipped is True
    assert v.verdict_status == "skipped"
    assert v.skip_reason == "rate_limited"
    assert v.latency_ms == 1234
    # degrade 는 행동 대상이 아니다 — 호출측이 단일패스로 발행 (AP-V6-12).
    assert not v.is_actionable


def test_skipped_overrides_status_even_with_claims() -> None:
    # 거짓 신뢰 방지 — skipped 면 무조건 status=skipped (바이라인 정합, AP-V6-10).
    v = FactVerdict(skipped=True, claims=[CritiqueClaim(**_valid_claim_kwargs())])
    assert v.verdict_status == "skipped"
    assert not v.is_actionable
