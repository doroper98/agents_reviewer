"""V5 Phase 2A — EvidenceDataset Contract regression test.

Plan §8.7 인수 기준:
    1. 모든 차트가 EvidenceDataset 을 *반드시* 입력으로 받아야.
    2. 모든 EvidenceDataset 이 ≥ 1개의 source_id 를 가져야.
    3. prose 에서 인용되지 않는 숫자가 차트에 들어 있으면 ChartCritic drop.
    4. TransformStep 이 raw → 차트 데이터의 변환을 100% 추적 가능.

본 모듈은 #1~#4 를 모두 결정적으로 검증. Phase 0C 의 EvidenceDataset 모델
강화 (DatasetField / TransformStep) + Phase 2A 의 EvidenceDatasetGuard
+ Plan §8.5 의 3개 금지 행위 (AP-V5-24 / 25 / 26).

[Phase 2A 시점의 가드]
- Pydantic min_length=1 (source_ids) — 1차 가드.
- EvidenceDatasetGuard.evaluate_chart() — 통합 검증.
- ensure_chart_data_cited_in_prose() — Phase 6 ChartCritic 의 사전 구현.
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.state.models import (
    DatasetField,
    EvidenceDataset,
    TransformStep,
)
from src.visual import (
    EvidenceDatasetGuard,
    EvidenceDatasetGuardError,
    ensure_chart_data_cited_in_prose,
    ensure_chart_has_source_ids,
    extract_chart_numbers,
    validate_evidence_dataset,
)


# ─── 인수 기준 #2 — source_ids ≥ 1 강제 ──────────────────────────────


def test_dataset_requires_source_ids_pydantic_level() -> None:
    """Pydantic min_length=1 가드가 1차로 작동."""
    with pytest.raises(Exception):
        EvidenceDataset(
            dataset_id="D-1",
            source_ids=[],
            rows=[{"x": 1}],
        )


def test_dataset_with_blank_source_ids_caught_by_guard() -> None:
    """공백 문자열 source_id 는 Pydantic 통과하지만 guard 가 잡음."""
    ds = EvidenceDataset(
        dataset_id="D-1",
        source_ids=["   "],
        rows=[{"x": 1}],
    )
    issues = validate_evidence_dataset(ds)
    assert any("AP-V5-25" in i for i in issues), (
        "공백 source_id 가 AP-V5-25 로 잡혀야"
    )


def test_dataset_with_empty_rows_fails() -> None:
    """rows 가 비어 있으면 CHART-AP-7 사전 가드 발화."""
    ds = EvidenceDataset(
        dataset_id="D-1",
        source_ids=["S-001"],
        rows=[],
    )
    issues = validate_evidence_dataset(ds)
    assert any("CHART-AP-7" in i for i in issues)


def test_dataset_with_nan_rows_fails() -> None:
    """NaN/inf 값 → CHART-AP-12 사전 가드."""
    ds = EvidenceDataset(
        dataset_id="D-1",
        source_ids=["S-001"],
        rows=[{"x": float("nan"), "y": 5.0}],
    )
    issues = validate_evidence_dataset(ds)
    assert any("CHART-AP-12" in i for i in issues)


# ─── 인수 기준 #4 — TransformStep 추적성 ──────────────────────────────


def test_transform_step_tracking() -> None:
    """transforms 의 input_fields 가 dataset.fields 안에 있는지 검증."""
    ds = EvidenceDataset(
        dataset_id="D-1",
        source_ids=["S-001"],
        rows=[{"date": "2026-05-01", "ratio": 0.32}],
        fields=[
            DatasetField(name="date", semantic_type="time"),
            DatasetField(name="ratio", semantic_type="ratio"),
        ],
        transforms=[
            TransformStep(
                operation="normalize",
                description="ratio 를 0~1 로 정규화",
                input_fields=["ratio"],
                output_fields=["ratio"],
            )
        ],
    )
    issues = validate_evidence_dataset(ds)
    # 이 경우는 input/output 모두 fields 에 있어 OK.
    transform_issues = [i for i in issues if "transform" in i]
    assert not transform_issues


def test_transform_step_broken_input_field() -> None:
    """transforms 의 input_field 가 fields 에 없으면 추적성 깨짐."""
    ds = EvidenceDataset(
        dataset_id="D-1",
        source_ids=["S-001"],
        rows=[{"date": "2026-05-01"}],
        fields=[
            DatasetField(name="date", semantic_type="time"),
        ],
        transforms=[
            TransformStep(
                operation="filter",
                description="존재하지 않는 ghost_field 참조",
                input_fields=["ghost_field"],   # fields 에 없음
                output_fields=["date"],
            )
        ],
    )
    issues = validate_evidence_dataset(ds)
    assert any("ghost_field" in i for i in issues)


def test_dataset_field_semantic_types() -> None:
    """DatasetField.semantic_type 의 7종 enum 검증."""
    expected = {"time", "category", "geo", "quantity", "ratio", "score", "text"}
    from typing import get_args
    actual = set(get_args(DatasetField.model_fields["semantic_type"].annotation))
    assert actual == expected, f"semantic_type enum drift: {actual} vs {expected}"


def test_suitable_forbidden_overlap_detected() -> None:
    """suitable_visuals 와 forbidden_visuals 가 겹치면 fail."""
    ds = EvidenceDataset(
        dataset_id="D-1",
        source_ids=["S-001"],
        rows=[{"x": 1}],
        suitable_visuals=["bar", "line"],
        forbidden_visuals=["line"],   # 충돌
    )
    issues = validate_evidence_dataset(ds)
    assert any("suitable_visuals" in i for i in issues)


# ─── AP-V5-26: source_id 없는 chart emit 금지 ────────────────────────


def test_chart_with_direct_source_ids_passes() -> None:
    chart = {
        "type": "bar",
        "title": "테스트",
        "data": [{"label": "A", "value": 10}],
        "source_ids": ["S-001"],
    }
    # 통과 — source_ids 가 직접 박혀 있음.
    ensure_chart_has_source_ids(chart)


def test_chart_with_dataset_ref_passes() -> None:
    ds = EvidenceDataset(
        dataset_id="D-1",
        source_ids=["S-001"],
        rows=[{"x": 1}],
    )
    chart = {
        "type": "bar",
        "title": "테스트",
        "data": [{"label": "A", "value": 10}],
        "dataset_id": "D-1",
    }
    ensure_chart_has_source_ids(chart, dataset_index={"D-1": ds})


def test_chart_without_source_id_fails_ap_v5_26() -> None:
    """AP-V5-26: source_id / dataset_ref 둘 다 없는 chart 는 fail."""
    chart = {
        "type": "bar",
        "title": "선례 오염 의심",
        "data": [{"label": "A", "value": 10}],
        # source_ids / dataset_id 둘 다 없음.
    }
    with pytest.raises(EvidenceDatasetGuardError) as exc:
        ensure_chart_has_source_ids(chart)
    assert "AP-V5-26" in str(exc) or "AP-V5-26" in str(exc.value if hasattr(exc, "value") else exc)


def test_chart_with_phantom_dataset_ref_fails() -> None:
    """존재하지 않는 dataset_id 참조 → fail."""
    chart = {
        "type": "bar",
        "title": "테스트",
        "data": [{"label": "A", "value": 10}],
        "dataset_id": "D-PHANTOM",
    }
    with pytest.raises(EvidenceDatasetGuardError):
        ensure_chart_has_source_ids(chart, dataset_index={})


# ─── AP-V5-24: prose 인용 가드 (Plan §8.6 question 8) ────────────────


def test_chart_numbers_extraction() -> None:
    """차트 data 의 숫자 추출."""
    chart = {
        "type": "bar",
        "data": [
            {"label": "A", "value": 35},
            {"label": "B", "value": 80},
            {"label": "C", "value": 18},
        ],
    }
    nums = extract_chart_numbers(chart)
    assert "35" in nums
    assert "80" in nums
    assert "18" in nums


def test_chart_numbers_skips_single_digit() -> None:
    """1자리 숫자는 false-positive 위험 — 추출 제외."""
    chart = {"data": [{"v": 5}, {"v": 7}]}
    nums = extract_chart_numbers(chart)
    assert "5" not in nums
    assert "7" not in nums


def test_chart_data_cited_in_prose_passes_when_quoted() -> None:
    chart = {
        "type": "bar",
        "data": [{"label": "한국", "value": 35}, {"label": "일본", "value": 80}],
    }
    prose = "한국의 의존도는 35%, 일본은 80% 수준."
    ok, reason = ensure_chart_data_cited_in_prose(chart, prose)
    assert ok, reason


def test_chart_data_cited_in_prose_fails_when_orphan() -> None:
    chart = {
        "type": "bar",
        "data": [{"label": "A", "value": 35}, {"label": "B", "value": 80}],
    }
    prose = "이 사건은 매우 중요하며 영향이 크다."  # 차트 숫자 인용 0건
    ok, reason = ensure_chart_data_cited_in_prose(chart, prose)
    assert not ok
    assert "AP-V5-24" in reason


def test_chart_with_no_numeric_data_passes() -> None:
    """수치 0건인 차트 (network 등) 는 통과."""
    chart = {
        "type": "network",
        "data": {"nodes": [{"id": "a"}, {"id": "b"}], "links": [{"src": "a", "dst": "b"}]},
    }
    ok, reason = ensure_chart_data_cited_in_prose(chart, "")
    assert ok


# ─── EvidenceDatasetGuard 통합 ───────────────────────────────────────


def test_guard_evaluate_chart_passes_clean_case() -> None:
    ds = EvidenceDataset(
        dataset_id="D-1",
        source_ids=["S-001"],
        rows=[{"label": "A", "value": 35}],
    )
    guard = EvidenceDatasetGuard(datasets=[ds])
    chart = {
        "type": "bar",
        "title": "test",
        "data": [{"label": "A", "value": 35}],
        "dataset_id": "D-1",
    }
    prose = "값 35 는 결정적."
    result = guard.evaluate_chart(chart, prose)
    assert result["passed"]
    assert result["verdict"] == "keep"


def test_guard_evaluate_chart_drops_orphan_with_no_source() -> None:
    guard = EvidenceDatasetGuard()
    chart = {
        "type": "bar",
        "title": "선례 오염",
        "data": [{"label": "A", "value": 35}],
        # source_ids X, dataset_id X.
    }
    result = guard.evaluate_chart(chart, prose="값 35 인용함.")
    assert not result["passed"]
    assert result["verdict"] == "drop"
    assert any("AP-V5-26" in i for i in result["issues"])


def test_guard_assert_throws_on_violation() -> None:
    guard = EvidenceDatasetGuard()
    chart = {"type": "bar", "data": [{"v": 35}]}
    with pytest.raises(EvidenceDatasetGuardError):
        guard.assert_chart_valid(chart, prose="다른 내용")


def test_guard_add_dataset_validates() -> None:
    """add_dataset 이 validate_evidence_dataset 호출 — 깨진 dataset 거절."""
    guard = EvidenceDatasetGuard()
    bad = EvidenceDataset(
        dataset_id="D-bad",
        source_ids=["S-001"],
        rows=[],   # 비어있음 — CHART-AP-7
    )
    with pytest.raises(EvidenceDatasetGuardError):
        guard.add_dataset(bad)


# ─── 인수 기준 #1 — 모든 차트가 EvidenceDataset 입력 검증 ──────────────


def test_acceptance_1_all_charts_must_have_evidence_dataset() -> None:
    """Plan §8.7 #1 — 다양한 chart spec 시나리오를 가드가 일관되게 처리.

    실제 v4.5.7 의 ComposedSection.charts 는 source_id 없이 emit. Phase 2A
    부터는 emit 시 *어디에서나* 가드가 fail. 회귀 테스트가 본 가드를 *모든*
    차트 형태에 대해 우회 불가능하게 강제.
    """
    cases = [
        # (chart_dict, expected_passed)
        ({"type": "bar", "data": [{"v": 30}], "source_ids": ["S-1"]}, True),
        ({"type": "donut", "data": [{"v": 30}], "source_id": "S-1"}, True),
        ({"type": "line", "data": [{"v": 30}]}, False),  # 누락
        ({"type": "stacked", "data": [{"v": 30}], "source_ids": []}, False),  # 빈 list
        ({"type": "bubble", "data": [{"v": 30}], "source_ids": [""]}, False),  # 공백
    ]
    for chart, expected_pass in cases:
        if expected_pass:
            ensure_chart_has_source_ids(chart)
        else:
            with pytest.raises(EvidenceDatasetGuardError):
                ensure_chart_has_source_ids(chart)
