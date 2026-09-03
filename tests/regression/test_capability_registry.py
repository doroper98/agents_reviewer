"""V5 Phase 2B — Visualization Capability Registry regression test.

Plan §9.5 인수 기준:
    1. VISUAL_CAPABILITY_REGISTRY.yaml 이 모든 차트 type 을 명시적으로 분류.
    2. VisualPlanner 가 emit 하는 모든 차트가 Registry 에 등재된 type.
    3. experimental 차트가 등재 없이 emit 되면 즉시 fail.
    4. 새 차트 type 추가 시 Registry 갱신을 *필수 단계* 로 강제 (PR 체크리스트).

본 모듈은 #1, #3 을 결정적으로 검증. #2 는 VisualPlanner 활성 시점에 통합
검증. #4 는 PR 체크리스트 정책.
"""

from __future__ import annotations

from tests.regression._pytest_compat import pytest

from src.visual.capability_registry import (
    REGISTRY_PATH,
    CapabilityRegistryError,
    assert_chart_in_registry,
    check_required_fields,
    get_capability,
    is_chart_type_allowed,
    list_all_types,
    list_experimental_types,
    list_guarded_types,
    list_safe_types,
    load_registry,
)


# ─── 인수 기준 #1 — Registry 모든 type 분류 ──────────────────────────


def test_registry_yaml_exists() -> None:
    assert REGISTRY_PATH.exists(), f"Registry yaml 미존재: {REGISTRY_PATH}"


def test_registry_loads_without_error() -> None:
    reg = load_registry()
    assert isinstance(reg, dict)
    assert "visual_capabilities" in reg


def test_registry_distribution_matches_plan_9_3() -> None:
    """v8.7.0 정본 분포 — safe 11 / guarded 24 / experimental 1 (총 36).

    v8.7.0 변경 (CHART_REDESIGN_V8_6_PLAN §9 — Phase 5): gauge(단일 KPI 반원 링) +
    spectrum(양극 축 성향) + funnel(단계 감소) 을 guarded 로 신설.
    v8.6.3 변경 (CHART_REDESIGN_V8_6_PLAN §5.3/§5.4): histogram(구간 도수) +
    calendar_heat(일별 강도 달력) 을 guarded 로 신설.
    v8.6.2 변경 (§5.1/§5.2): treemap 을 experimental →
    guarded 로 승격(렌더러 실장, default_policy 제거)하고 tree 를 신설.

    v5.2.14 변경: Plan §9.3 의 원본 (safe 11 / guarded 3 / experimental 2 / 총 16)
    에서 FT/Economist 스타일 신규 7종을 guarded 로 추가 → guarded 10 / 총 23.
    v7.0.0 변경 (REFACTOR_V7_PLAN.md §1.3, 사용자 게이트 승인): bump / bullet /
    connected_scatter 3종을 guarded 로 추가 → guarded 13 / 총 26.
    v7.5.0 변경 (사용자 요청 — 시각화 유형 확장): combo / diverging_bar /
    pyramid / dot_matrix 4종 (이중 축 결합 + 사회 이슈 어휘) 을 guarded 로
    추가 → guarded 17 / 총 30.
    v8.0.0 변경 (르포 트랙): stakeholder_map 1종 (행위자 관계도) 을 guarded 로 추가.
    v7.9.17 변경 (사용자 요청): network(구 관계도) 폐기 (CHART-AP-36) → guarded 17 / 총 30.
    신규 type 의 chart_critic 통과율이 충분히 측정되면 safe 승격 검토.
    """
    safe = list_safe_types()
    guarded = list_guarded_types()
    experimental = list_experimental_types()
    total = list_all_types()

    assert len(safe) == 11, f"safe types: 11 expected, got {len(safe)}: {safe}"
    assert len(guarded) == 24, f"guarded types: 24 expected, got {len(guarded)}: {guarded}"
    assert len(experimental) == 1, f"experimental types: 1 expected, got {len(experimental)}"
    assert len(total) == 36, f"total: 36 expected, got {len(total)}"


def test_registry_safe_types_match_plan_9_3() -> None:
    """Plan §9.3 의 정본 — safe 11종 (bar/line/area/stacked_bar/heatmap/bubble/donut/forecast/dual_line/gantt/decision_matrix)."""
    expected_safe = {
        "bar", "line", "area", "stacked_bar", "heatmap", "bubble",
        "donut", "forecast", "dual_line", "gantt", "decision_matrix",
    }
    actual_safe = set(list_safe_types())
    assert actual_safe == expected_safe, (
        f"safe types drift: missing={expected_safe - actual_safe}, "
        f"extra={actual_safe - expected_safe}"
    )


def test_registry_guarded_types_match_plan_9_3() -> None:
    """v8.7.0 정본 — guarded 24종 (v8.6.2~3 의 4종 + v8.7.0 gauge/spectrum/funnel)."""
    expected_guarded = {
        "choropleth", "sankey",
        # v5.2.14 — FT/Economist 스타일 신규 7종
        "scatter", "stacked_area", "lollipop", "slope",
        "small_multiples", "waterfall", "range_bar",
        # v7.0.0 — Track A 신규 3종 (REFACTOR_V7_PLAN.md §1.3)
        "bump", "bullet", "connected_scatter",
        # v7.5.0 — 이중 축 결합 + 사회 이슈 어휘 4종
        "combo", "diverging_bar", "pyramid", "dot_matrix",
        # v8.0.0 — 르포 행위자 관계도
        "stakeholder_map",
        # v8.6.2 — 위계 2종 (2층 구성 / 소속)
        "treemap", "tree",
        # v8.6.3 — 분포·달력 2종
        "histogram", "calendar_heat",
        # v8.7.0 — 2차 흡수 3종 (단일 KPI / 양극 성향 / 단계 감소)
        "gauge", "spectrum", "funnel",
    }
    assert set(list_guarded_types()) == expected_guarded


def test_registry_experimental_types_match_plan_9_3() -> None:
    """v8.6.2 정본 — experimental 1종 (chord). treemap 은 guarded 로 승격."""
    expected_experimental = {"chord"}
    assert set(list_experimental_types()) == expected_experimental


def test_registry_distribution_section_consistent() -> None:
    """yaml 의 distribution 섹션이 실제 카운트와 일치."""
    reg = load_registry()
    declared = reg.get("distribution", {})
    assert declared.get("safe") == 11
    assert declared.get("guarded") == 24
    assert declared.get("experimental") == 1
    assert reg.get("total") == 36


def test_each_capability_has_required_fields() -> None:
    """모든 entry 가 renderer / status / required_fields 보유."""
    reg = load_registry()
    caps = reg["visual_capabilities"]
    for chart_type, cap in caps.items():
        assert "renderer" in cap, f"{chart_type}: renderer missing"
        assert "status" in cap, f"{chart_type}: status missing"
        assert "required_fields" in cap, f"{chart_type}: required_fields missing"
        assert cap["status"] in ("safe", "guarded", "experimental"), (
            f"{chart_type}: invalid status {cap['status']!r}"
        )


def test_experimental_types_have_default_policy_forbidden() -> None:
    """Plan §9.4 — experimental 의 default_policy 는 forbidden."""
    for chart_type in list_experimental_types():
        cap = get_capability(chart_type)
        assert cap is not None
        assert cap.get("default_policy") == "forbidden", (
            f"experimental {chart_type}: default_policy must be 'forbidden'"
        )


# ─── 인수 기준 #3 — experimental forbidden 강제 ─────────────────────


def test_safe_type_always_allowed() -> None:
    allowed, _ = is_chart_type_allowed("bar")
    assert allowed


def test_guarded_type_allowed_with_warning() -> None:
    allowed, reason = is_chart_type_allowed("sankey")
    assert allowed
    assert "guarded" in reason.lower() or "Gate C" in reason


def test_experimental_type_forbidden_by_default() -> None:
    """AP-V5-27 — experimental 차트는 must_have 없으면 거절."""
    allowed, reason = is_chart_type_allowed("chord")
    assert not allowed
    assert "AP-V5-27" in reason or "experimental" in reason.lower()


def test_experimental_type_allowed_with_must_have() -> None:
    """ResearchDirector 가 must_have 에 명시 등재한 경우만 허용."""
    allowed, reason = is_chart_type_allowed("chord", must_have_types=["chord"])
    assert allowed
    assert "must_have" in reason


def test_unregistered_type_forbidden() -> None:
    """AP-V5-27 — Registry 미등재 type 은 즉시 거절."""
    allowed, reason = is_chart_type_allowed("waterfall_pie_chord_3d")
    assert not allowed
    assert "AP-V5-27" in reason or "미등재" in reason


# ─── required_fields 검증 ────────────────────────────────────────────


def test_check_required_fields_passes_with_all_fields() -> None:
    ok, _ = check_required_fields("bubble", ["x", "y", "size", "extra"])
    assert ok


def test_check_required_fields_fails_with_missing() -> None:
    ok, reason = check_required_fields("bubble", ["x", "y"])  # size 누락
    assert not ok
    assert "size" in reason


def test_check_required_fields_unregistered_type_fails() -> None:
    ok, reason = check_required_fields("phantom_chart", ["x"])
    assert not ok
    assert "unregistered" in reason


def test_decision_matrix_has_phase_8_fields() -> None:
    """Plan §6.3 + Phase 8 — decision_matrix 는 option/criterion/score 강제."""
    cap = get_capability("decision_matrix")
    assert cap is not None
    assert set(cap["required_fields"]) == {"option", "criterion", "score"}


def test_gantt_has_v4_5_4_time_fields() -> None:
    """v4.5.4 의 시간축 자동 정책 (CHART-AP-13) — gantt 는 task/start/end."""
    cap = get_capability("gantt")
    assert cap is not None
    assert set(cap["required_fields"]) == {"task", "start", "end"}


def test_forecast_has_confidence_interval_fields() -> None:
    """forecast 는 ci_low/ci_high 까지 — Vega-Lite area band 필수."""
    cap = get_capability("forecast")
    assert cap is not None
    assert "ci_low" in cap["required_fields"]
    assert "ci_high" in cap["required_fields"]


# ─── assert_chart_in_registry 통합 ───────────────────────────────────


def test_assert_chart_in_registry_passes_safe() -> None:
    chart = {"type": "bar", "data": [{"category": "A", "value": 10}]}
    assert_chart_in_registry(chart)  # raises 없음


def test_assert_chart_in_registry_uses_mark_when_no_type() -> None:
    """Vega-Lite spec 형식 (mark 만 있는) 에서도 type 추출."""
    spec = {"mark": "line", "data": {"values": []}}
    assert_chart_in_registry(spec)  # line 은 safe


def test_assert_chart_in_registry_rejects_unregistered() -> None:
    chart = {"type": "totally_made_up_type", "data": []}
    with pytest.raises(CapabilityRegistryError) as exc:
        assert_chart_in_registry(chart)
    assert "AP-V5-27" in str(exc.value) or "미등재" in str(exc.value)


def test_assert_chart_in_registry_rejects_experimental_without_must_have() -> None:
    chart = {"type": "chord", "data": [{"source": "a", "target": "b", "value": 1}]}
    with pytest.raises(CapabilityRegistryError):
        assert_chart_in_registry(chart)  # must_have 미명시 → fail


def test_assert_chart_in_registry_passes_experimental_with_must_have() -> None:
    chart = {"type": "treemap", "data": [{"hierarchy": "x", "value": 1}]}
    assert_chart_in_registry(chart, must_have_types=["treemap"])  # OK


def test_assert_chart_in_registry_rejects_no_type() -> None:
    """type / mark 둘 다 없으면 검증 불가 — fail."""
    chart = {"data": [{"x": 1}]}
    with pytest.raises(CapabilityRegistryError):
        assert_chart_in_registry(chart)


# ─── Plan §9.5 인수 기준 #4 — PR 체크리스트 강제 ────────────────────


def test_renderer_field_uses_known_values() -> None:
    """Plan §9.3 의 renderer enum: vega_lite / d3_custom / vega_lite_or_d3_geo /
    vega_lite_or_d3_custom."""
    expected_renderers = {
        "vega_lite", "d3_custom",
        "vega_lite_or_d3_geo", "vega_lite_or_d3_custom",
    }
    reg = load_registry()
    for chart_type, cap in reg["visual_capabilities"].items():
        renderer = cap.get("renderer")
        assert renderer in expected_renderers, (
            f"{chart_type}: unknown renderer {renderer!r} — Plan §9.3 의 4종 enum"
        )


def test_added_in_field_present_for_all() -> None:
    """모든 entry 에 added_in 필드 — 신규 추가 시 어느 Phase 인지 추적."""
    reg = load_registry()
    for chart_type, cap in reg["visual_capabilities"].items():
        assert "added_in" in cap, (
            f"{chart_type}: added_in 필드 누락 (Phase 추가 추적용)"
        )
