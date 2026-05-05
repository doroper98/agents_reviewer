"""V5 Phase 2B — Visualization Capability Registry loader + guards.

REFACTOR_V5_PLAN.md §9 의 SSOT 인 ``docs/VISUAL_CAPABILITY_REGISTRY.yaml``
을 로드해 차트 type 의 capability 를 검증한다.

[정책 — Plan §9.4 의 3-tier]
    safe         : VisualPlanner 자유 emit. ChartCritic 통과 필요.
    guarded      : ChartCritic + Visual Sanity (Gate C) 통과 필수.
    experimental : 기본값 forbidden. ResearchDirector must_have 시만.

[AP-V5-27 — Plan §23]
"Capability Registry 미등재 차트 emit 금지. 새 차트 type 추가 시 Registry
갱신을 PR 체크리스트로 강제."

[Public API]
    from src.visual.capability_registry import (
        load_registry,
        get_capability,
        is_chart_type_allowed,
        check_required_fields,
        list_safe_types,
        list_guarded_types,
        list_experimental_types,
        REGISTRY_PATH,
        CapabilityRegistryError,
    )
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# Plan §9.5 인수 기준 #1 의 yaml 위치 SSOT.
REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "VISUAL_CAPABILITY_REGISTRY.yaml"
)


class CapabilityRegistryError(ValueError):
    """Plan §23 AP-V5-27 위반 — 등재 안 된 type / 정책 위반."""


# ─── 로더 (캐시) ───────────────────────────────────────────────────────


_REGISTRY_CACHE: dict[str, Any] | None = None


def load_registry(force_reload: bool = False) -> dict[str, Any]:
    """yaml 파일을 로드해 dict 반환. 한 번 로드 후 캐시.

    Args:
        force_reload: True 면 캐시 무시하고 다시 읽음.
    """
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None and not force_reload:
        return _REGISTRY_CACHE

    if not REGISTRY_PATH.exists():
        raise CapabilityRegistryError(
            f"Capability Registry yaml 미존재: {REGISTRY_PATH}"
        )

    with REGISTRY_PATH.open(encoding="utf-8") as fp:
        data = yaml.safe_load(fp)

    if not isinstance(data, dict) or "visual_capabilities" not in data:
        raise CapabilityRegistryError(
            f"Capability Registry yaml 형식 오류: top-level 'visual_capabilities' 누락"
        )

    _REGISTRY_CACHE = data
    return data


def _capabilities() -> dict[str, dict[str, Any]]:
    """visual_capabilities 섹션만 반환."""
    reg = load_registry()
    caps = reg.get("visual_capabilities") or {}
    return caps if isinstance(caps, dict) else {}


# ─── 조회 / 검증 ──────────────────────────────────────────────────────


def get_capability(chart_type: str) -> dict[str, Any] | None:
    """chart_type 에 해당하는 Registry entry 반환. 미등재 시 None."""
    return _capabilities().get(chart_type)


def is_chart_type_allowed(
    chart_type: str,
    *,
    must_have_types: list[str] | None = None,
) -> tuple[bool, str]:
    """차트 type 이 *현재 Registry 정책* 에서 허용되는지 판정.

    Plan §9.4 3-tier 정책 그대로:
        safe         : 항상 허용.
        guarded      : 허용 (단 Phase 6 Gate C 통과 필수 — 본 함수는 형식 가드만).
        experimental : ``must_have_types`` 안에 *명시 등재* 된 경우만 허용.
        미등재       : 즉시 거절 (AP-V5-27).

    Args:
        chart_type: VisualPlanner 가 emit 한 type 이름.
        must_have_types: ResearchDirector (Phase 1A) 의
            ``visual_constraints.must_have`` 또는 사용자 명시 요청 type 목록.

    Returns:
        (allowed, reason) — allowed=False 면 reason 에 거절 사유.
    """
    must_have = set(must_have_types or [])
    cap = get_capability(chart_type)
    if cap is None:
        return False, (
            f"AP-V5-27: chart type {chart_type!r} 가 Registry 미등재 — "
            f"emit 금지. docs/VISUAL_CAPABILITY_REGISTRY.yaml 에 추가 필요."
        )

    status = cap.get("status")
    if status == "safe":
        return True, "safe"
    if status == "guarded":
        return True, "guarded — Phase 6 Gate C 통과 필수"
    if status == "experimental":
        if chart_type in must_have:
            return True, "experimental — must_have 에 명시 등재"
        default_policy = cap.get("default_policy", "forbidden")
        if default_policy == "forbidden":
            return False, (
                f"AP-V5-27: chart type {chart_type!r} 는 experimental 이며 "
                f"default_policy=forbidden — must_have 에 명시 등재 필요."
            )
        return True, f"experimental — default_policy={default_policy}"

    return False, f"unknown status: {status!r} for type {chart_type!r}"


def check_required_fields(
    chart_type: str,
    available_field_names: list[str],
) -> tuple[bool, str]:
    """차트 type 이 요구하는 필드가 데이터에 모두 있는지.

    Args:
        chart_type: Registry 에 등재된 type.
        available_field_names: EvidenceDataset.fields 의 name 목록 또는 chart
            data 의 키 목록.

    Returns:
        (ok, reason) — ok=False 면 reason 에 missing 필드 명시.
    """
    cap = get_capability(chart_type)
    if cap is None:
        return False, f"unregistered type: {chart_type!r}"

    required = set(cap.get("required_fields") or [])
    available = set(available_field_names or [])
    missing = required - available
    if missing:
        return False, (
            f"required_fields 누락: {sorted(missing)} "
            f"(type={chart_type}, available={sorted(available)})"
        )
    return True, "ok"


# ─── 분포 헬퍼 ─────────────────────────────────────────────────────────


def list_safe_types() -> list[str]:
    return sorted(
        t for t, cap in _capabilities().items()
        if cap.get("status") == "safe"
    )


def list_guarded_types() -> list[str]:
    return sorted(
        t for t, cap in _capabilities().items()
        if cap.get("status") == "guarded"
    )


def list_experimental_types() -> list[str]:
    return sorted(
        t for t, cap in _capabilities().items()
        if cap.get("status") == "experimental"
    )


def list_all_types() -> list[str]:
    return sorted(_capabilities().keys())


# ─── VisualPlanner / chart spec 통합 가드 ─────────────────────────────


def assert_chart_in_registry(
    chart: dict[str, Any],
    *,
    must_have_types: list[str] | None = None,
) -> None:
    """exhibit dict 또는 chart spec 에서 type 을 추출해 Registry 정합성 검증.

    Plan §9.5 인수 기준 #2 — VisualPlanner 가 emit 하는 *모든* 차트가
    Registry 에 등재된 type 이어야.

    Raises:
        CapabilityRegistryError: 미등재 또는 정책 위반.
    """
    # 차트 type 추출 — exhibit 형식 or chart spec 형식 모두 지원.
    chart_type = (
        chart.get("type")
        or (chart.get("mark") if isinstance(chart.get("mark"), str)
            else (chart.get("mark") or {}).get("type"))
        or ""
    )

    if not chart_type or not isinstance(chart_type, str):
        raise CapabilityRegistryError(
            "chart 의 type 또는 mark 필드 누락 — Registry 검증 불가"
        )

    allowed, reason = is_chart_type_allowed(
        chart_type, must_have_types=must_have_types
    )
    if not allowed:
        raise CapabilityRegistryError(reason)
