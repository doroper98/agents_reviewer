"""V5 Phase 2A — EvidenceDataset Contract Guard.

REFACTOR_V5_PLAN.md §8 — 차트와 지도가 *prose 의 부산물* 이 아니라 *구조화된
EvidenceDataset 에서 직접* 생성되도록 데이터 계약 도입.

Plan §8.5 의 3개 금지 행위 (AP-V5-24 / 25 / 26) 를 강제 검증:

    AP-V5-24 — prose 발 차트 데이터 생성 금지.
        composer / VisualPlanner 가 prose 에 박힌 숫자를 차트 데이터로
        *재구성* 하면 안 됨. 모든 차트 데이터는 EvidenceDataset 에서.

    AP-V5-25 — 출처 없는 synthetic value 금지.
        EvidenceDataset.source_ids 가 비어 있으면 EvidenceDatasetGuard fail.
        Pydantic min_length=1 가드가 이미 1차 가드 — 본 모듈은 *runtime*
        검증 + 친화적 에러 메시지.

    AP-V5-26 — source_id 없는 chart emit 금지.
        Phase 6 Gate A schema validation 이 1차 차단. 본 모듈은 chart spec
        의 dataset_ref / dataset_id / source_ids 누락을 사전 가드.

[Public API]
    from src.visual.evidence_dataset import (
        EvidenceDatasetGuard,
        validate_evidence_dataset,
        ensure_chart_has_source_ids,
        ensure_chart_data_cited_in_prose,
        EvidenceDatasetGuardError,
    )

[ChartCritic 의 question 8 사전 구현 — Plan §8.6]
``ensure_chart_data_cited_in_prose`` 가 차트 안의 *수치값* 을 prose 에서
인용하는지 확인. 인용 0 건이면 fail (drop 권고). Phase 6 ChartCritic 이
LLM 으로 본격 검수하기 전의 결정적 1차 가드.
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Iterable

from src.state.models import EvidenceDataset

logger = logging.getLogger(__name__)


class EvidenceDatasetGuardError(ValueError):
    """Plan §8.5 의 3개 금지 행위 위반. 차트 drop 신호."""


# ─── EvidenceDataset 자체의 검증 (Pydantic 가드 보강) ────────────────────


def validate_evidence_dataset(dataset: EvidenceDataset) -> list[str]:
    """EvidenceDataset 의 *형식 + 의미* 검증. 위반 사항 list 반환 (빈 list = OK).

    Pydantic 의 ``min_length=1`` (source_ids) 와 ``extra="forbid"`` 는 이미 1차
    가드. 본 함수는 Plan §8.7 인수 기준 #2 / #4 의 추가 검증.
    """
    issues: list[str] = []

    # AP-V5-25 — source_ids 비어 있음.
    if not dataset.source_ids:
        issues.append(
            f"AP-V5-25: dataset {dataset.dataset_id!r} 에 source_ids 가 없음 "
            f"(EvidencePack.claims 의 source_id 와 매칭되어야)"
        )

    # 비어 있지 않은 source_id 만 카운트 (공백 문자열 거절).
    non_empty_sources = [s for s in dataset.source_ids if (s or "").strip()]
    if not non_empty_sources:
        issues.append(
            f"AP-V5-25: dataset {dataset.dataset_id!r} 의 source_ids 가 모두 공백"
        )

    # rows 가 비어 있으면 차트 자체 의미 X (CHART-AP-7 의 사전 가드).
    if not dataset.rows:
        issues.append(
            f"CHART-AP-7: dataset {dataset.dataset_id!r} 의 rows 가 비어 있음"
        )

    # rows 안의 숫자 필드에 NaN/inf 가 있으면 fail (CHART-AP-12 의 사전 가드).
    nan_count = 0
    for row in (dataset.rows or []):
        if not isinstance(row, dict):
            continue
        for v in row.values():
            if isinstance(v, float) and not math.isfinite(v):
                nan_count += 1
    if nan_count > 0:
        issues.append(
            f"CHART-AP-12: dataset {dataset.dataset_id!r} 의 rows 에 "
            f"NaN/inf 값 {nan_count}건"
        )

    # Plan §8.7 인수 기준 #4 — TransformStep 추적성. transforms 가 있으면
    # input_fields / output_fields 가 fields 안에 명시되어야.
    if dataset.fields and dataset.transforms:
        field_names = {f.name for f in dataset.fields}
        for ts in dataset.transforms:
            for f_in in ts.input_fields:
                if f_in not in field_names:
                    issues.append(
                        f"transform '{ts.operation}' 의 input_field "
                        f"{f_in!r} 가 dataset.fields 에 없음 — 추적성 깨짐"
                    )

    # suitable_visuals 와 forbidden_visuals 가 충돌하면 emit 자체가 모순.
    overlap = set(dataset.suitable_visuals) & set(dataset.forbidden_visuals)
    if overlap:
        issues.append(
            f"dataset {dataset.dataset_id!r}: suitable_visuals 와 "
            f"forbidden_visuals 가 동시 포함 — {sorted(overlap)}"
        )

    return issues


# ─── chart spec 의 source_id 가드 (AP-V5-26) ──────────────────────────


def ensure_chart_has_source_ids(
    chart: dict[str, Any],
    *,
    dataset_index: dict[str, EvidenceDataset] | None = None,
) -> None:
    """Plan §8.5 (다) — source_id 없는 chart 를 emit 하면 즉시 fail.

    chart 는 v4.5.7 의 ``ComposedSection.charts`` 의 dict (`{type, title,
    data, note?}`) 또는 V5 의 ExhibitPack.chart_specs 의 Vega-Lite spec.

    검증 규칙 (둘 중 하나라도 만족):
      - chart 자체가 ``"source_ids"`` 또는 ``"source_id"`` 필드 보유 (≥1 비공백).
      - chart 가 ``"dataset_id"`` 또는 ``"dataset_ref"`` 로 EvidenceDataset 참조,
        그리고 dataset_index 에 그 ID 가 등록되어 있고, 해당 dataset 의
        source_ids 가 ≥1 비공백.

    둘 다 실패하면 EvidenceDatasetGuardError.
    """
    if not isinstance(chart, dict):
        raise EvidenceDatasetGuardError(
            f"AP-V5-26: chart 가 dict 가 아님 — {type(chart).__name__}"
        )

    # Direct source_id(s) on chart.
    direct = (
        chart.get("source_ids")
        or ([chart.get("source_id")] if chart.get("source_id") else [])
    )
    direct = [s for s in (direct or []) if isinstance(s, str) and s.strip()]
    if direct:
        return  # OK — chart 에 직접 source_ids.

    # Reference to EvidenceDataset by id.
    dataset_ref = chart.get("dataset_id") or chart.get("dataset_ref")
    if dataset_ref and dataset_index is not None:
        ds = dataset_index.get(dataset_ref)
        if ds is None:
            raise EvidenceDatasetGuardError(
                f"AP-V5-26: chart 의 dataset_ref={dataset_ref!r} 가 "
                f"dataset_index 에 없음 — 가짜 참조"
            )
        non_empty = [s for s in (ds.source_ids or []) if (s or "").strip()]
        if not non_empty:
            raise EvidenceDatasetGuardError(
                f"AP-V5-25: 참조한 dataset {dataset_ref!r} 의 source_ids 가 비어있음"
            )
        return  # OK.

    # 둘 다 실패.
    raise EvidenceDatasetGuardError(
        f"AP-V5-26: chart {chart.get('title','<untitled>')!r} 가 "
        f"source_ids / source_id 필드도 없고 dataset_id 참조도 없음 — "
        f"Phase 2A 의 EvidenceDataset Contract 위반."
    )


# ─── prose 인용 가드 (Plan §8.6 ChartCritic 질문 8 의 사전 구현) ──────


_NUMBER_PATTERN = re.compile(
    r"-?\d+(?:[,_]\d{3})*(?:\.\d+)?"
)


def extract_chart_numbers(chart: dict[str, Any]) -> set[str]:
    """차트 dict 의 data 안에서 *수치값* 을 정규화해 set 으로 추출.

    chart["data"] 가 list[dict] 또는 dict 인 두 형태를 모두 지원. 각 값에서
    숫자 토큰을 뽑아 *원본 문자열* 그대로 set 에 담는다 — prose 안에서
    그대로 인용되었는지 substring 매칭으로 확인 가능.

    참고: composer 가 ``"3,500"`` / ``"3500"`` / ``"3.5K"`` 같이 *다양한
    형태로* 같은 숫자를 표기하는 회귀가 있다. 본 가드는 *문자열 그대로*
    매칭이라 표기 차이는 통과시킴 — 더 엄격한 normalize 는 LLM Critic 의
    영역 (Phase 6).
    """
    out: set[str] = set()

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
        elif isinstance(obj, (int, float)):
            if isinstance(obj, float) and not math.isfinite(obj):
                return
            out.add(str(obj))
        elif isinstance(obj, str):
            for m in _NUMBER_PATTERN.findall(obj):
                # 너무 짧은 (1자리) 숫자는 흔해 false-positive 위험 — 제외.
                if len(m.lstrip("-")) >= 2:
                    out.add(m)
    _walk(chart.get("data"))
    return out


def ensure_chart_data_cited_in_prose(
    chart: dict[str, Any],
    prose: str,
    *,
    min_citation_ratio: float = 0.20,
) -> tuple[bool, str]:
    """Plan §8.6 ChartCritic 의 질문 8 결정적 사전 구현.

    *이 차트의 데이터 중 일부* 가 인접 prose 에 등장하는지 검증. 특정 임계
    (`min_citation_ratio`, 기본 20%) 미만이면 *prose 와 분리된 데이터 회귀*
    로 판정 — drop 권고.

    Args:
        chart: ComposedSection.charts 의 1개 dict.
        prose: 차트가 박힐 인접 섹션의 prose.
        min_citation_ratio: 차트 data 안의 *고유 숫자* 중 prose 에 등장한 비율.

    Returns:
        (passed, reason) — passed=False 면 reason 에 fail 사유.
    """
    numbers = extract_chart_numbers(chart)
    if not numbers:
        # 수치가 없는 차트 (예: network 의 nodes/links) 는 본 가드를 통과.
        return True, "no_numeric_data"

    p = prose or ""
    cited = sum(1 for n in numbers if n in p)
    ratio = cited / len(numbers)
    if ratio < min_citation_ratio:
        return False, (
            f"AP-V5-24: 차트 data 의 수치 {len(numbers)}개 중 prose 인용 "
            f"{cited}건 ({ratio:.0%} < {min_citation_ratio:.0%}) — "
            f"prose 부산물로 보임"
        )
    return True, f"cited {cited}/{len(numbers)} ({ratio:.0%})"


# ─── EvidenceDatasetGuard — 통합 entry point ────────────────────────


class EvidenceDatasetGuard:
    """Phase 2A 의 통합 가드. VisualPlanner / ChartCritic 가 emit 한 차트의
    Plan §8.5 3개 금지 행위 (AP-V5-24/25/26) 를 1회 호출로 검증.

    [사용]
        guard = EvidenceDatasetGuard(datasets=[ds1, ds2])
        guard.assert_chart_valid(chart, prose="...")

    [통합 진입점 — VisualPlanner 가 drop 할지 결정]
        verdict = guard.evaluate_chart(chart, prose)
        if not verdict["passed"]:
            drop(chart)
    """

    def __init__(self, datasets: Iterable[EvidenceDataset] | None = None) -> None:
        self._dataset_index: dict[str, EvidenceDataset] = {}
        for ds in (datasets or []):
            self._dataset_index[ds.dataset_id] = ds

    @property
    def dataset_index(self) -> dict[str, EvidenceDataset]:
        return dict(self._dataset_index)

    def add_dataset(self, ds: EvidenceDataset) -> None:
        # validate 가 fail 하면 Pydantic 또는 자체 가드에서 잡혀 있어야.
        issues = validate_evidence_dataset(ds)
        if issues:
            raise EvidenceDatasetGuardError(
                f"EvidenceDataset {ds.dataset_id!r} validation failed: {issues}"
            )
        self._dataset_index[ds.dataset_id] = ds

    def evaluate_chart(
        self,
        chart: dict[str, Any],
        prose: str = "",
        *,
        require_prose_citation: bool = True,
    ) -> dict[str, Any]:
        """비-throw 진단 — passed/issues/metrics dict 반환.

        Phase 6 ChartCritic 이 LLM 검수 *전* 에 1차 결정적 가드로 사용.
        """
        issues: list[str] = []

        # AP-V5-26 — source_id 누락.
        try:
            ensure_chart_has_source_ids(chart, dataset_index=self._dataset_index)
        except EvidenceDatasetGuardError as e:
            issues.append(str(e))

        # AP-V5-24 — prose 인용.
        if require_prose_citation:
            ok, reason = ensure_chart_data_cited_in_prose(chart, prose)
            if not ok:
                issues.append(reason)

        return {
            "passed": not issues,
            "issues": issues,
            "verdict": "keep" if not issues else "drop",
            "chart_title": chart.get("title", "<untitled>"),
        }

    def assert_chart_valid(
        self,
        chart: dict[str, Any],
        prose: str = "",
        *,
        require_prose_citation: bool = True,
    ) -> None:
        """throwing variant — 위반 시 EvidenceDatasetGuardError."""
        result = self.evaluate_chart(
            chart, prose, require_prose_citation=require_prose_citation
        )
        if not result["passed"]:
            raise EvidenceDatasetGuardError(
                "; ".join(result["issues"])
            )
