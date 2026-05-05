"""V5 Phase 5 — Word Budget per Section + 절단 검출 + 적응형 max_tokens.

REFACTOR_V5_PLAN.md §12 — 두 작업 통합:
    (가) 분량 균질화 회귀 차단 — 섹션 단위 *어절·문자 수* budget.
    (나) 출력 절단 회귀 차단 — 자동 검출 + 연속 호출.

[Plan §6.3 / §12.3 mode 별 분량 가이드]
    fast      : 1500~2500 자, 3~4 섹션, 균등 (400~700/섹션)
    standard  : 3500~5500 자, 4~6 섹션, 비대칭 (peak 1200~1800)
    deep      : 6000~9000 자, 5~7 섹션, 강한 비대칭 (peak 2000~2500)

[Plan §12.4 절단 검출 5종 시그널]
이미 tests/regression/helpers.py 에 detect_truncation 박혀 있음 — 본
모듈은 *runtime production 경로* 의 SSOT 로 격상 (helpers 는 회귀 테스트
경계값 검증용으로 보존).

[Plan §12.5 연속 호출 — 1회 cap]
- 절단 검출 시 부분 출력을 다시 composer 입력으로 — 이어 작성.
- 1회 후에도 절단 잔존 시 publish-with-warning (AP-V5-22).
- Stitching 정책 — 원본의 마지막 미완성 잘라내고 연속 출력 붙임.

[Plan §12.6 적응형 max_tokens]
- ContextAnalyst 가 사건 복잡도 점수 산출.
- composer max_tokens 가 점수에 따라 base ~ max 사이 보간.

[Public API]
    from src.visual.word_budget import (
        TruncationStatus,
        WordBudget,
        MODE_TARGET_CHARS_LOWER,
        MODE_BUDGET_BANDS,
        COMPOSER_MAX_TOKENS_V5,
        detect_truncation,
        adaptive_max_tokens,
        compute_word_budgets,
        gini_coefficient,
        section_length_distribution,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ─── Plan §6.3 / §12.3 SSOT — mode 별 분량 ──────────────────────


# Plan §6.4 truncation lower bound (이미 tests/regression/helpers.py 에도).
MODE_TARGET_CHARS_LOWER: dict[str, int] = {
    "fast": 1500,
    "standard": 3500,
    "deep": 6000,
}

# Plan §12.3 mode 별 분량 분포 가이드.
MODE_BUDGET_BANDS: dict[str, dict[str, Any]] = {
    "fast": {
        "total_min": 1500, "total_max": 2500,
        "section_count_min": 3, "section_count_max": 4,
        "section_target_min": 400, "section_target_max": 700,
        "peak_target": 700,    # peak 섹션도 균등 가까이
        "asymmetry": "even",
    },
    "standard": {
        "total_min": 3500, "total_max": 5500,
        "section_count_min": 4, "section_count_max": 6,
        "section_target_min": 500, "section_target_max": 1200,
        "peak_target": 1500,    # peak 섹션 강조
        "asymmetry": "moderate",
    },
    "deep": {
        "total_min": 6000, "total_max": 9000,
        "section_count_min": 5, "section_count_max": 7,
        "section_target_min": 600, "section_target_max": 1500,
        "peak_target": 2200,    # peak 섹션 강한 강조
        "asymmetry": "strong",
    },
}


# Plan §12.6 — composer 의 mode 별 적응형 max_tokens.
COMPOSER_MAX_TOKENS_V5: dict[str, dict[str, int]] = {
    "fast":     {"base": 16000, "max": 24000},
    "standard": {"base": 28000, "max": 40000},
    "deep":     {"base": 48000, "max": 64000},   # v4.5.7 의 일률 32K 한계 해소
}


# ─── 자료구조 ──────────────────────────────────────────────────


@dataclass
class TruncationStatus:
    truncated: bool
    reason: str = ""
    issues: list[str] = field(default_factory=list)
    raw_tail: str | None = None


@dataclass
class WordBudget:
    """섹션별 분량 budget. Editor 가 이 budget 을 강제."""

    section_idx: int
    target_chars: int
    is_peak: bool = False
    role: Literal["main", "support", "watch"] = "support"


# ─── Plan §12.4 절단 검출 ─────────────────────────────────────


def detect_truncation(
    composed: dict[str, Any] | None,
    mode: str,
    raw_response: str = "",
) -> TruncationStatus:
    """Plan §12.4 의 5종 시그널 통합. tests/regression/helpers.py 와
    *byte-equal* 정책. 본 모듈이 production SSOT.

    Args:
        composed: ComposedReport dict 또는 None (JSON 파싱 실패).
        mode: fast / standard / deep.
        raw_response: 절단된 raw LLM 응답 (tail 보존용).

    Returns:
        TruncationStatus.
    """
    issues: list[str] = []

    # 1. JSON 파싱 실패.
    if composed is None:
        return TruncationStatus(
            truncated=True,
            reason="json_parse_failed",
            issues=["json_parse_failed"],
            raw_tail=(raw_response[-500:] if raw_response else None),
        )

    sections = composed.get("sections") or []

    # 2. 마지막 섹션 prose 가 문장부호 없이 끝남.
    if sections:
        last_prose = (((sections[-1] or {}).get("prose") or "")).rstrip()
        if last_prose and last_prose[-1] not in ".!?。·":
            issues.append("last_section_unfinished")

    # 3. closing 비어있음.
    if not (composed.get("closing") or "").strip():
        issues.append("closing_missing")

    # 4. deep 모드에서 watch_signals / contradictions 비어있음.
    if mode == "deep":
        if not composed.get("watch_signals"):
            issues.append("watch_signals_missing_in_deep")
        if not composed.get("contradictions"):
            issues.append("contradictions_missing_in_deep")

    # 5. 총 분량 < mode lower bound × 0.7.
    target = MODE_TARGET_CHARS_LOWER.get(mode, 3500)
    actual = sum(len(((s or {}).get("prose") or "")) for s in sections)
    if actual < target * 0.7:
        issues.append(f"underweight_{actual}_vs_{int(target * 0.7)}")

    return TruncationStatus(
        truncated=bool(issues),
        reason="; ".join(issues),
        issues=issues,
    )


# ─── Plan §12.6 적응형 max_tokens ─────────────────────────────


def adaptive_max_tokens(mode: str, complexity_score: float) -> int:
    """ContextAnalyst 의 복잡도 점수 → composer max_tokens.

    Plan §12.6 — base ~ max 사이 보간 (정규화 0~1).

    Args:
        mode: fast / standard / deep.
        complexity_score: 사건 복잡도 (출처 수 × 행위자 수 × 타임라인 등의
            가중합. ContextAnalyst 가 별도 산출).

    Returns:
        max_tokens 정수값 (base 이상 max 이하).
    """
    config = COMPOSER_MAX_TOKENS_V5.get(mode, COMPOSER_MAX_TOKENS_V5["standard"])
    norm = max(0.0, min(complexity_score / 50.0, 1.0))
    return int(config["base"] + (config["max"] - config["base"]) * norm)


def complexity_score_from_context(context: Any) -> float:
    """Plan §12.6 의 복잡도 점수 — 출처 / 타임라인 / 핵심 수치 가중합.

    `len(sources) * 2 + len(timeline) * 1.5 + len(key_figures)`.
    """
    sources = getattr(context, "sources", None) or []
    timeline = getattr(context, "timeline", None) or []
    key_figures = getattr(context, "key_figures", None) or []
    if isinstance(context, dict):
        sources = context.get("sources") or []
        timeline = context.get("timeline") or []
        key_figures = context.get("key_figures") or []
    return float(len(sources) * 2 + len(timeline) * 1.5 + len(key_figures))


# ─── Plan §12.3 — 섹션별 word budget 부여 ─────────────────────


def compute_word_budgets(
    section_count: int,
    mode: str,
    *,
    peak_section_idx: int | None = None,
) -> list[WordBudget]:
    """Plan §12.3 의 mode 별 분량 budget 부여.

    Args:
        section_count: 보고서 섹션 수.
        mode: fast / standard / deep.
        peak_section_idx: peak 섹션 위치 (ResearchDirector AnalysisBrief
            의 report_shape.peak_section). None 이면 절반 위치 디폴트.

    Returns:
        list[WordBudget].
    """
    if section_count <= 0:
        return []

    band = MODE_BUDGET_BANDS.get(mode, MODE_BUDGET_BANDS["standard"])
    peak = peak_section_idx if peak_section_idx is not None else section_count // 2
    peak = max(0, min(peak, section_count - 1))

    out: list[WordBudget] = []
    for i in range(section_count):
        if i == peak:
            target = band["peak_target"]
            role: Literal["main", "support", "watch"] = "main"
        elif i == section_count - 1:
            # 마지막 섹션 = watch / 결론. 짧게.
            target = band["section_target_min"]
            role = "watch"
        else:
            target = (band["section_target_min"] + band["section_target_max"]) // 2
            role = "support"

        out.append(WordBudget(
            section_idx=i,
            target_chars=target,
            is_peak=(i == peak),
            role=role,
        ))
    return out


# ─── 분량 비대칭 측정 (Plan §12.7 인수 기준) ──────────────────


def gini_coefficient(values: list[float]) -> float:
    """섹션 분량의 지니 계수 (0=균등, 1=극단 집중).

    Plan §12.7 인수 기준 #1 — V5 의 deep 보고서 분량 지니 계수가 v4.5.7
    baseline 보다 0.10 이상 증가해야 (peak 섹션 강조 신호).
    """
    if not values or all(v == 0 for v in values):
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cum = 0.0
    for i, v in enumerate(sorted_vals, start=1):
        cum += i * v
    total = sum(sorted_vals)
    if total <= 0:
        return 0.0
    return (2.0 * cum) / (n * total) - (n + 1) / n


def section_length_distribution(composed: dict[str, Any]) -> dict[str, Any]:
    """섹션 분량 분포 통계 — Phase 7A soft fail 의 보강."""
    sections = composed.get("sections") or []
    chars = [len(((s or {}).get("prose") or "")) for s in sections]
    chars_pos = [c for c in chars if c > 0]
    return {
        "section_count": len(sections),
        "char_counts": chars,
        "total_chars": sum(chars),
        "min_chars": min(chars_pos) if chars_pos else 0,
        "max_chars": max(chars_pos) if chars_pos else 0,
        "gini": round(gini_coefficient([float(c) for c in chars_pos]), 3),
    }


# ─── Stitching — 연속 호출 결합 (Plan §12.5) ────────────────


def stitch_continuation(
    partial: dict[str, Any],
    continuation: dict[str, Any] | None,
) -> dict[str, Any]:
    """원본 절단된 보고서 + 연속 호출 결과를 결합.

    Plan §12.5 — "원본의 마지막 미완성 부분을 잘라내고, 연속 호출의 출력을
    그 자리에 붙인다. 두 출력의 경계가 어색하면 Editor 가 다음 단계에서
    다듬는다."

    Args:
        partial: 절단된 ComposedReport.
        continuation: 연속 호출 결과. None 이면 partial 그대로 반환.

    Returns:
        stitched ComposedReport dict.
    """
    if continuation is None:
        return dict(partial)

    out = dict(partial)
    sections_p = partial.get("sections") or []
    sections_c = continuation.get("sections") or []

    # 1. 마지막 섹션이 미완성인지.
    if sections_p and sections_c:
        last_p = sections_p[-1]
        # 연속 호출의 첫 섹션이 *원본 마지막 섹션의 이어 작성* 인 경우 결합.
        # 단순 정책 — heading 일치하면 prose 결합.
        first_c = sections_c[0] if sections_c else {}
        if (
            isinstance(last_p, dict) and isinstance(first_c, dict)
            and (last_p.get("heading") or "") == (first_c.get("heading") or "")
        ):
            # 마지막 섹션 prose 의 미완성 끝 잘라내고 continuation 의 prose 이어 붙임.
            new_last = dict(last_p)
            last_prose = ((last_p.get("prose") or "")).rstrip()
            # 마지막 단락의 미완성 문장 자르기 — 마지막 마침표 이후 잘라냄.
            cut_idx = max(
                last_prose.rfind("."),
                last_prose.rfind("!"),
                last_prose.rfind("?"),
            )
            if cut_idx > 0:
                last_prose = last_prose[:cut_idx + 1]
            new_last["prose"] = (last_prose + " " + (first_c.get("prose") or "")).strip()
            sections_p = list(sections_p[:-1]) + [new_last] + list(sections_c[1:])
        else:
            # 새 섹션으로 추가.
            sections_p = list(sections_p) + list(sections_c)

    out["sections"] = sections_p

    # closing / watch_signals / contradictions — continuation 우선 (있을 시).
    for key in ("closing", "watch_signals", "contradictions",
                "confidence_summary", "confidence_score"):
        if continuation.get(key):
            out[key] = continuation[key]

    return out
