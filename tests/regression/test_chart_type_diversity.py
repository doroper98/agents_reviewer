"""Chart type scenario fixture sanity (v5.2.14, Layer 5 of 5).

캔들 회귀 (v5.2.0 추가했으나 거의 emit X) 교훈으로 신설. 본 모듈은
``tests/regression/fixtures/chart_type_scenarios.yaml`` 의 정합성과,
production 의 ``KNOWN_CHART_TYPES`` 와의 1:1 매핑을 결정적으로 검증한다.

본 모듈이 잡는 회귀:
    1. KNOWN_CHART_TYPES 가 늘었는데 fixture 갱신 안 됨 → 새 type 가 starvation
       alarm 의 분모에서 누락
    2. fixture 의 expected_chart_type 이 KNOWN_CHART_TYPES 와 불일치
    3. fixture 의 id 와 expected_chart_type 이 일치하지 않음
    4. status: pending 항목이 production 도입 후에도 active 로 안 바뀜
       (Phase 도입 PR 체크리스트 강제)

Phase 4 (신규 7종 production 도입) 진입 시 본 모듈은 pending 7종을 active 로
승격시키는 fixture 갱신을 강제한다.
"""

from __future__ import annotations

from pathlib import Path

from tests.regression._pytest_compat import pytest

import yaml

from src.visual.usage_log import KNOWN_CHART_TYPES


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "chart_type_scenarios.yaml"
)


@pytest.fixture(scope="module")
def fixture() -> dict:
    raw = FIXTURE_PATH.read_text(encoding="utf-8")
    return yaml.safe_load(raw)


def test_fixture_loads(fixture: dict) -> None:
    assert "scenarios" in fixture
    assert isinstance(fixture["scenarios"], list)
    assert len(fixture["scenarios"]) >= 13, (
        "fixture 가 production 13종을 최소 커버해야 함"
    )


def test_id_equals_expected_type(fixture: dict) -> None:
    """각 scenario 의 id 가 expected_chart_type 과 동일해야 (자명성 보장)."""
    for sc in fixture["scenarios"]:
        assert sc["id"] == sc["expected_chart_type"], (
            f"id '{sc['id']}' != expected_chart_type "
            f"'{sc['expected_chart_type']}' — fixture 정합성 위반"
        )


def test_all_known_types_have_scenarios(fixture: dict) -> None:
    """production 의 KNOWN_CHART_TYPES 의 모든 type 에 시나리오가 존재해야.

    캔들 회귀 방지의 핵심 — Layer 1 의 starvation alarm 이 의도된 분모를
    가지도록 보장.
    """
    fixture_ids = {sc["id"] for sc in fixture["scenarios"]}
    missing = set(KNOWN_CHART_TYPES) - fixture_ids
    assert not missing, (
        f"KNOWN_CHART_TYPES 의 {missing} 가 fixture 에 누락. "
        f"src/visual/usage_log.py 또는 본 fixture 둘 중 하나가 drift."
    )


def test_active_scenarios_match_production(fixture: dict) -> None:
    """status: active 인 scenario 의 id 가 production 의 KNOWN_CHART_TYPES 와 동일."""
    active_ids = {
        sc["id"] for sc in fixture["scenarios"]
        if sc.get("status") == "active"
    }
    assert active_ids == set(KNOWN_CHART_TYPES), (
        f"active fixture ids {active_ids} != "
        f"KNOWN_CHART_TYPES {set(KNOWN_CHART_TYPES)}. "
        f"신규 type production 도입 PR 에서 fixture status 를 pending→active "
        f"로 함께 승격시켜야 함."
    )


def test_pending_scenarios_have_distinct_ids(fixture: dict) -> None:
    """status: pending 항목들도 KNOWN_CHART_TYPES 와 겹치지 않아야 (아직 미도입)."""
    pending_ids = {
        sc["id"] for sc in fixture["scenarios"]
        if sc.get("status") == "pending"
    }
    overlap = pending_ids & set(KNOWN_CHART_TYPES)
    assert not overlap, (
        f"pending 으로 표시된 {overlap} 가 이미 KNOWN_CHART_TYPES 에 있음. "
        f"production 도입된 type 은 status 를 active 로 바꿔야."
    )


def test_required_fields_present(fixture: dict) -> None:
    """각 scenario 가 필수 필드를 모두 가져야 — 인간 가독성 SSOT 보장."""
    required = {"id", "status", "data_shape", "scenario", "sample_prompt", "expected_chart_type"}
    for sc in fixture["scenarios"]:
        missing = required - set(sc.keys())
        assert not missing, (
            f"scenario id={sc.get('id')!r} 가 필수 필드 누락: {missing}"
        )


def test_metadata_counts_match(fixture: dict) -> None:
    """metadata 의 active_count / pending_count 가 실제 항목과 일치해야."""
    meta = fixture.get("metadata", {})
    if not meta:
        pytest.skip("metadata 섹션 없음 — optional")
    scenarios = fixture["scenarios"]
    actual_active = sum(1 for s in scenarios if s.get("status") == "active")
    actual_pending = sum(1 for s in scenarios if s.get("status") == "pending")
    assert meta.get("active_count") == actual_active, (
        f"metadata.active_count={meta.get('active_count')} != "
        f"실제 active 항목 수 {actual_active}"
    )
    assert meta.get("pending_count") == actual_pending, (
        f"metadata.pending_count={meta.get('pending_count')} != "
        f"실제 pending 항목 수 {actual_pending}"
    )
    assert meta.get("total_scenarios") == len(scenarios), (
        f"metadata.total_scenarios={meta.get('total_scenarios')} != "
        f"실제 항목 수 {len(scenarios)}"
    )
