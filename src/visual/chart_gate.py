"""V5 Phase 6 — Chart Correctness Gate (Plan §13).

4중 게이트의 *통합 진입점* + Plan §13.5 의 Fallback Ladder.

[게이트 흐름 — Plan §13.1]
    VisualPlanner emit
       ↓
    [Gate A] Schema Validation         (validate_vega_spec + schemas.guard)
       ↓ pass / fail → Gate D
    [Gate B] Chart-Topic Fit Critic    (chart_critic.critique — LLM)
       ↓ keep / replace / drop
    [Gate C] Render-time Visual Sanity (sanity_check.visual_sanity_check_svg)
       ↓ pass / fail → Gate D
    [Gate D] Fallback Ladder           (어느 게이트든 fail 시)
       ↓
    보고서에 노출

[Plan §13.5 Fallback Ladder — 3단계]
    1단계: 같은 데이터 → fact_grid 변환 (라벨 격자, 시각화 X).
    2단계: fact_grid 도 부적합 → 본문에 1문장 자연어 요약 추가.
    3단계: 차트 자체 제거.

[Plan §13.7 인수 기준 — 14개 antipattern 회귀 테스트]
회귀 테스트가 *깨진 입력* 을 만들어 4중 게이트가 잡는지 검증.

Public API:
    from src.visual.chart_gate import (
        ChartGateResult,
        run_chart_gate,
        FallbackLadder,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from src.visual.capability_registry import (
    CapabilityRegistryError,
    assert_chart_in_registry,
)
from src.visual.evidence_dataset import (
    EvidenceDatasetGuard,
    EvidenceDatasetGuardError,
)
from src.visual.sanity_check import (
    DEFAULT_THRESHOLDS,
    SanityCheckThresholds,
    SanityResult,
    visual_sanity_check_svg,
)
from src.visual.schemas import validate_chart_data
from src.visual.vega_adapter import VegaSpecError, validate_vega_spec

logger = logging.getLogger(__name__)


# ─── 결과 자료구조 ────────────────────────────────────────────────────


@dataclass
class ChartGateResult:
    """4중 게이트 통과 결과 + Fallback 정보."""

    chart_id: str
    passed: bool
    final_verdict: Literal["keep", "replace", "drop", "fallback_fact_grid", "fallback_text", "fallback_drop"]
    gate_results: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    fallback_payload: Any = None     # fact_grid dict 또는 자연어 텍스트


# ─── Plan §13.5 Fallback Ladder ──────────────────────────────────────


class FallbackLadder:
    """Plan §13.5 의 3단계 격하 fallback.

    [정책]
    1단계: chart data → fact_grid (label/value 격자 — 시각화 X, editorial 톤).
    2단계: 1단계도 부적합 (데이터 너무 많아 격자 부적합) → 본문에 1문장
           자연어 요약 추가 (compose 가 처리, 본 모듈은 텍스트만 emit).
    3단계: 2단계도 부적합 (Critic 이 drop) → 차트 자체 제거.

    *깨진 차트 / 부적합 차트가 보고서에 노출되는 일은 0건* — Plan §13.5.
    """

    MAX_FACT_GRID_ROWS = 6

    @staticmethod
    def to_fact_grid(chart_spec: dict[str, Any]) -> dict[str, Any] | None:
        """1단계 — chart data → fact_grid 변환. 데이터 ≤ 6행일 때만 적합."""
        data = chart_spec.get("data")
        if isinstance(data, dict):
            data = data.get("values") or data.get("rows")

        if not isinstance(data, list) or len(data) == 0:
            return None
        if len(data) > FallbackLadder.MAX_FACT_GRID_ROWS:
            return None

        tiles: list[dict[str, Any]] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            label = (
                row.get("label") or row.get("category") or row.get("name") or row.get("x")
                or row.get("when") or ""
            )
            value = (
                row.get("value") or row.get("y") or row.get("size") or row.get("score") or ""
            )
            if label == "" and value == "":
                continue
            tiles.append({
                "label": str(label)[:40],
                "value": str(value)[:20],
                "sublabel": str(row.get("note") or row.get("group") or "")[:30],
            })

        if not tiles:
            return None

        return {
            "kind": "fact_grid",
            "title": _spec_title(chart_spec),
            "tiles": tiles,
        }

    @staticmethod
    def to_text_summary(chart_spec: dict[str, Any]) -> str | None:
        """2단계 — 자연어 1문장. data 의 max/min 또는 첫 N개 항목 요약."""
        data = chart_spec.get("data")
        if isinstance(data, dict):
            data = data.get("values") or data.get("rows")

        if not isinstance(data, list) or len(data) == 0:
            return None

        title = _spec_title(chart_spec)
        # 단순 — 첫 3 항목 + 총 개수 요약.
        head: list[str] = []
        for row in data[:3]:
            if not isinstance(row, dict):
                continue
            label = row.get("label") or row.get("category") or row.get("name") or ""
            value = row.get("value") or row.get("y") or row.get("size") or ""
            if label or value:
                head.append(f"{label} {value}".strip())

        if not head:
            return None

        prefix = f"({title}) " if title else ""
        more = f" 외 {len(data) - 3}건" if len(data) > 3 else ""
        return f"{prefix}{', '.join(head)}{more}."


def _spec_title(chart_spec: dict[str, Any]) -> str:
    """chart spec 또는 dict 의 title 추출."""
    title = chart_spec.get("title")
    if isinstance(title, dict):
        return (title.get("text") or "").strip()
    if isinstance(title, str):
        return title.strip()
    return ""


# ─── 4중 게이트 통합 — run_chart_gate ─────────────────────────────────


def run_chart_gate(
    chart: dict[str, Any],
    *,
    section_prose: str = "",
    report_thesis: str = "",
    rendered_svg: str | None = None,
    viewbox: tuple[float, float, float, float] = (0, 0, 560, 280),
    must_have_types: list[str] | None = None,
    datasets: list[Any] | None = None,
    critic_verdict: Any = None,             # ChartVerdict from Gate B (선택)
    sanity_thresholds: SanityCheckThresholds | None = None,
    chart_id: str = "",
) -> ChartGateResult:
    """4중 게이트 일괄 실행 + Fallback Ladder.

    Args:
        chart: 검증할 chart dict 또는 Vega-Lite spec.
        section_prose: Gate B (Critic) 의 prose 인접도 검증용.
        report_thesis: Gate B 의 thesis 비교용.
        rendered_svg: Gate C 입력 — Vega-Lite 또는 d3 가 렌더한 SVG.
            None 이면 Gate C 스킵 (서버 측 렌더 X 환경).
        viewbox: Gate C 의 viewBox (width/height 포함).
        must_have_types: ResearchDirector visual_constraints.must_have —
            experimental 차트 우회용.
        datasets: Phase 2A EvidenceDataset 목록 (source_id 가드).
        critic_verdict: Gate B 의 결과 (LLM 호출 결과 미리 받아 전달).
            None 이면 Gate B 는 *결정적 휴리스틱* 으로 평가.
        sanity_thresholds: Gate C threshold 사용자화.

    Returns:
        ChartGateResult — passed / final_verdict / gate_results / issues /
        fallback_payload.
    """
    chart_id = chart_id or _spec_title(chart) or "<untitled>"
    issues: list[str] = []
    gate_results: dict[str, Any] = {}

    # ─── Gate A — Schema Validation ───────────────────────────────────
    gate_a_passed = True
    gate_a_reason = ""
    try:
        # Vega-Lite spec 형식 검증.
        if "$schema" in chart or "mark" in chart or "encoding" in chart:
            validate_vega_spec(chart)
        # Capability Registry 미등재 거절.
        assert_chart_in_registry(chart, must_have_types=must_have_types)
        # 타입별 Pydantic 가드.
        chart_type = (chart.get("type") or chart.get("mark") or "").lower()
        if isinstance(chart.get("mark"), dict):
            chart_type = (chart["mark"].get("type") or "").lower()
        if chart_type:
            data = chart.get("data")
            if isinstance(data, dict):
                data = data.get("values", data)
            ok, reason = validate_chart_data(chart_type, data)
            if not ok:
                gate_a_passed = False
                gate_a_reason = reason
                issues.append(f"Gate A: {reason}")
    except (VegaSpecError, CapabilityRegistryError) as e:
        gate_a_passed = False
        gate_a_reason = str(e)
        issues.append(f"Gate A: {e}")
    gate_results["gate_a"] = {"passed": gate_a_passed, "reason": gate_a_reason}

    if not gate_a_passed:
        return _apply_fallback_ladder(chart, chart_id, issues, gate_results)

    # ─── Gate B — Chart-Topic Fit Critic ──────────────────────────────
    # critic_verdict 이 주어지지 않으면 결정적 휴리스틱으로 평가.
    gate_b_passed = True
    gate_b_reason = ""
    if critic_verdict is None:
        from src.agents.chart_critic import critique_via_heuristics, is_score_keep
        verdict = critique_via_heuristics(chart, section_prose, report_thesis)
        if not is_score_keep(verdict.score, verdict.verdict):
            gate_b_passed = False
            gate_b_reason = (
                f"Critic verdict={verdict.verdict}, score={verdict.score}, "
                f"reason={verdict.reason}"
            )
        gate_results["gate_b"] = {
            "passed": gate_b_passed,
            "verdict": verdict.verdict,
            "score": verdict.score,
            "reason": verdict.reason,
            "source": "heuristic",
        }
    else:
        from src.agents.chart_critic import is_score_keep
        verdict = critic_verdict
        score = getattr(verdict, "score", 1)
        v_label = getattr(verdict, "verdict", "drop")
        reason = getattr(verdict, "reason", "")
        if not is_score_keep(score, v_label):
            gate_b_passed = False
            gate_b_reason = f"Critic LLM verdict={v_label}, score={score}, reason={reason}"
        gate_results["gate_b"] = {
            "passed": gate_b_passed,
            "verdict": v_label,
            "score": score,
            "reason": reason,
            "source": "llm",
        }

    if not gate_b_passed:
        issues.append(f"Gate B: {gate_b_reason}")
        return _apply_fallback_ladder(chart, chart_id, issues, gate_results)

    # ─── Gate B-extra — EvidenceDataset Guard (Phase 2A 결합) ─────────
    if datasets:
        try:
            guard = EvidenceDatasetGuard(datasets=datasets)
            verdict_ds = guard.evaluate_chart(
                chart, prose=section_prose, require_prose_citation=True
            )
            gate_results["gate_b_dataset"] = verdict_ds
            if not verdict_ds["passed"]:
                issues.extend([f"Gate B-dataset: {i}" for i in verdict_ds["issues"]])
                return _apply_fallback_ladder(chart, chart_id, issues, gate_results)
        except EvidenceDatasetGuardError as e:
            gate_results["gate_b_dataset"] = {"passed": False, "issues": [str(e)]}
            issues.append(f"Gate B-dataset: {e}")
            return _apply_fallback_ladder(chart, chart_id, issues, gate_results)

    # ─── Gate C — Visual Sanity (SVG 렌더 후) ─────────────────────────
    gate_c_passed = True
    if rendered_svg:
        sanity = visual_sanity_check_svg(
            rendered_svg, viewbox, thresholds=sanity_thresholds or DEFAULT_THRESHOLDS
        )
        gate_results["gate_c"] = {
            "passed": sanity.passed,
            "issues": sanity.issues,
            "metrics": sanity.metrics,
        }
        if not sanity.passed:
            gate_c_passed = False
            issues.extend([f"Gate C: {i}" for i in sanity.issues])

    if not gate_c_passed:
        return _apply_fallback_ladder(chart, chart_id, issues, gate_results)

    # 모든 게이트 통과.
    return ChartGateResult(
        chart_id=chart_id,
        passed=True,
        final_verdict="keep",
        gate_results=gate_results,
        issues=[],
    )


def _apply_fallback_ladder(
    chart: dict[str, Any],
    chart_id: str,
    issues: list[str],
    gate_results: dict[str, Any],
) -> ChartGateResult:
    """Plan §13.5 의 3단계 격하."""
    # 1단계 — fact_grid.
    fact_grid = FallbackLadder.to_fact_grid(chart)
    if fact_grid is not None:
        return ChartGateResult(
            chart_id=chart_id,
            passed=False,
            final_verdict="fallback_fact_grid",
            gate_results=gate_results,
            issues=issues,
            fallback_payload=fact_grid,
        )

    # 2단계 — 자연어 1문장.
    text_summary = FallbackLadder.to_text_summary(chart)
    if text_summary is not None:
        return ChartGateResult(
            chart_id=chart_id,
            passed=False,
            final_verdict="fallback_text",
            gate_results=gate_results,
            issues=issues,
            fallback_payload=text_summary,
        )

    # 3단계 — drop.
    return ChartGateResult(
        chart_id=chart_id,
        passed=False,
        final_verdict="fallback_drop",
        gate_results=gate_results,
        issues=issues,
    )
