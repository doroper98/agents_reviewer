"""V6 Phase V6-0 — Fact discipline fixture 로드/스키마 회귀.

REFACTOR_V6_PLAN.md §3 (Phase V6-0) + §4 (테스트 플랜 T-1 스켈레톤).

본 테스트는 V6 의 사실 거버넌스 fixture (fact_discipline_scenarios.yaml) 가
구조적으로 건강한지 검증한다. 실제 결정적 가드 (UnsourcedNumberGuard 등) 는
Phase V6-1 에서 src/factcheck/deterministic_guards.py 에 구현되며, 그때 본
파일에 검출률 테스트 (T-1) 가 추가된다.

지금 단계의 목적: error_class 5종 동결 + 시나리오 스키마 강제 + NVIDIA 회귀
케이스 영구 보존. fixture 가 깨지거나 error_class 가 임의 확장되면 fail.
"""

from __future__ import annotations

from pathlib import Path

import yaml

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "fact_discipline_scenarios.yaml"
)

# REFACTOR_V6_PLAN.md §3 Phase V6-0 에서 동결한 5종. 추가는 Plan 갱신 + 본 set
# 갱신 *동시에* 만 (AP-V6 신규 케이스 등록 절차).
# 1차 동결 5종 (REFACTOR_V6_PLAN.md §3 Phase V6-0 — NVIDIA 2026-06-01 표본).
FROZEN_ERROR_CLASSES = {
    "unsourced_number",
    "scope_misattribution",
    "novelty_conflation",
    "timepoint_overclaim",
    "list_truncation",
}

# 2차 확장 6종 (2026-06-03 일일 브리핑 표본, 사용자 게이트 승격 — AP-V6-9).
# REFACTOR_V6_PLAN.md §0.2-b. 신규 class 는 Plan §0.2-b + 본 set 갱신 *동시에* 만.
EXPANDED_ERROR_CLASSES = {
    "market_data_mismatch",
    "stale_sourcing",
    "event_conflation",
    "attribution_as_fact",
    "causal_overreach",
    "metric_label_ambiguity",
}

# 임의 확장 차단용 전체 enum (가드 대상 = 알려진 class 전체).
ALL_ERROR_CLASSES = FROZEN_ERROR_CLASSES | EXPANDED_ERROR_CLASSES

_REQUIRED_KEYS = {
    "id",
    "error_class",
    "evidence",
    "bad_prose",
    "good_prose",
    "expected_flag",
    "guard",
}
_REQUIRED_EVIDENCE_KEYS = {"fact", "source_date", "scope_note", "source_url"}


def _load() -> list[dict]:
    with FIXTURE_PATH.open(encoding="utf-8") as fp:
        data = yaml.safe_load(fp)
    return list(data.get("scenarios", []))


def test_fixture_loads_and_nonempty() -> None:
    scenarios = _load()
    assert len(scenarios) >= 5, "최소 5종 (NVIDIA 회귀) 시나리오가 있어야 한다"


def test_every_scenario_has_required_schema() -> None:
    for sc in _load():
        missing = _REQUIRED_KEYS - set(sc)
        assert not missing, f"{sc.get('id')} 에 누락된 키: {missing}"
        ev_missing = _REQUIRED_EVIDENCE_KEYS - set(sc["evidence"])
        assert not ev_missing, f"{sc['id']} evidence 누락: {ev_missing}"


def test_error_class_within_known_enum() -> None:
    for sc in _load():
        assert (
            sc["error_class"] in ALL_ERROR_CLASSES
        ), f"{sc['id']} 의 error_class '{sc['error_class']}' 가 알려진 enum 밖 (게이트 승격 필요)"


def test_all_known_error_classes_covered() -> None:
    present = {sc["error_class"] for sc in _load()}
    assert FROZEN_ERROR_CLASSES <= present, (
        "1차 동결 5종이 모두 fixture 에 1건 이상 있어야 한다. "
        f"누락: {FROZEN_ERROR_CLASSES - present}"
    )
    assert present == ALL_ERROR_CLASSES, (
        "알려진 error_class 가 모두 fixture 에 1건 이상 있어야 한다. "
        f"누락: {ALL_ERROR_CLASSES - present}"
    )


def test_scenario_ids_unique() -> None:
    ids = [sc["id"] for sc in _load()]
    assert len(ids) == len(set(ids)), "시나리오 id 중복"


def test_bad_and_good_prose_differ() -> None:
    for sc in _load():
        assert (
            sc["bad_prose"].strip() != sc["good_prose"].strip()
        ), f"{sc['id']} 의 bad/good prose 가 동일 — 교정 케이스가 아님"
