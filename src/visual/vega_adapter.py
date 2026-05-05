"""V5 Phase 2 — Vega-Lite spec → SVG renderer.

REFACTOR_V5_PLAN.md §7 (Phase 2) 의 핵심:
    "차트 enum 폐기 — Vega-Lite Adapter"
    "src/visual_builder.py 의 _render_donut, _render_bar, _render_gantt 등 11개
    함수 전부 폐기. 단일 어댑터로 통일."

본 모듈은 Plan §7.4 의 ``render_vega_lite()`` SSOT.

[활성화 정책 — Phase 2 시점]
- v4.5.7 호출 경로 byte-equal 보존을 위해 *opt-in flag* 로 통합.
- ``Config.enable_visual_planner`` (env: ``V5_VISUAL_PLANNER=1``) 가
  켜진 환경에서만 VisualPlanner 가 호출되어 Vega-Lite spec emit.
- 꺼진 환경에선 v4.5.7 의 charts.js (브라우저 d3) 가 그대로 작동.
- src/visual_builder.py 는 *현재 commit 시점엔 보존* — Plan §7.4 의
  "11개 함수 폐기" 는 Phase 2 의 실제 호출 경로 활성 (Tier 3 진입 후 또는
  사용자 명시 활성) 시점에 진행.

[의존성 — vl-convert-python (optional)]
실제 SVG 렌더링은 ``vl-convert-python`` (Vega-Lite JSON → SVG 변환) 또는
``vega-cli`` (npm) 가 필요. 미설치 시 SVG 대신 *spec dict 그대로* 반환 —
브라우저에서 vega-embed 로 렌더 가능 (현재 v4.5.7 의 d3 와 동일한 모델).

[Plan §7.7 자동 해결 antipattern (8개)]
- AP-1 (group/category 시각 분리)     → encoding.color 자동
- AP-2 (반복 라벨 시각 일관성)         → scale 안정성
- AP-3 (음수/0/극단값)                → 도메인 자동 + Phase 6 가드
- AP-4 (aspect-ratio vs viewBox)      → explicit width/height
- AP-9 (지도 zoom/center)             → projection 자동 bounds
- AP-11 (차트 카드 배경 하드코딩)       → theme config 강제
- AP-12 (bubble 스케일 고정)          → extent 자동 + Phase 6 가드
- AP-13 (gantt 시간축 누락)           → axis 자동 생성

[Plan §7.7 Phase 6 추가 가드 필요 (3개)]
- AP-5 / 6 / 10 (라벨 / annotation 충돌) — Vega-Lite 부분 자동 + Phase 6 Gate C.

[Plan §7.7 LLM Critic 단독 (2개)]
- AP-8 (chart type 사건 부적합) / AP-14 (무관 지리 annotation) — Phase 6 Gate B.

Public API:
    from src.visual import (
        render_vega_lite,
        is_vl_convert_available,
        validate_vega_spec,
        VegaSpecError,
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from src.visual.v5_theme import ThemeName, apply_theme_to_spec

logger = logging.getLogger(__name__)


class VegaSpecError(ValueError):
    """Vega-Lite spec 의 구조 / 의미 결함. Phase 6 Gate A 가 차단할 항목의 1차 가드."""


# ─── 의존성 검사 ───────────────────────────────────────────────────────


def is_vl_convert_available() -> bool:
    """vl-convert-python 설치 여부. 없으면 SVG 렌더 X — spec dict 그대로 반환."""
    try:
        import vl_convert  # noqa: F401
        return True
    except ImportError:
        return False


def is_vega_cli_available() -> bool:
    """vega-cli (npm) 설치 여부. fallback 경로."""
    import shutil
    return shutil.which("vl2svg") is not None


# ─── 코어 어댑터 — Plan §7.4 ─────────────────────────────────────────


def render_vega_lite(
    spec: dict[str, Any],
    theme: ThemeName = "editorial",
    *,
    output: Literal["svg", "spec_only"] = "svg",
    width: int | None = None,
    height: int | None = None,
) -> str | dict[str, Any]:
    """Vega-Lite JSON spec → SVG 또는 themed spec.

    Plan §7.4 의 단일 어댑터. v4.5.7 의 11개 type-specific renderer 를
    이 함수 1개로 대체.

    Args:
        spec: Vega-Lite spec dict. composer 또는 VisualPlanner 가 emit.
        theme: V5 design token 적용. "editorial" (default) / "burgundy".
        output:
            - "svg" — vl-convert-python 사용해 SVG 문자열 반환.
              미설치 시 자동으로 "spec_only" fallback.
            - "spec_only" — themed spec dict 그대로 반환 (브라우저 vega-embed
              가 렌더). 가벼운 경로.
        width / height: spec 의 width/height 를 *강제 덮어씀* (CHART-AP-4 가드).
            None 이면 spec 의 값 또는 Vega-Lite default 사용.

    Returns:
        - output="svg" + vl-convert 가용: SVG 문자열.
        - output="svg" + vl-convert 미설치: themed spec dict (with warning log).
        - output="spec_only": themed spec dict.

    Raises:
        VegaSpecError: spec 의 형식이 깨짐.
    """
    # 1. 형식 검증.
    validate_vega_spec(spec)

    # 2. V5 theme 강제 적용 (AP-V5-2 가드 — composer 가 색 결정 못 하게).
    themed = apply_theme_to_spec(spec, theme=theme, overwrite_existing_config=True)

    # 3. width / height 강제 (CHART-AP-4 가드 — aspect-ratio 충돌 차단).
    if width is not None:
        themed["width"] = int(width)
    if height is not None:
        themed["height"] = int(height)

    # 4. spec_only 면 dict 그대로 반환.
    if output == "spec_only":
        return themed

    # 5. SVG 렌더 — vl-convert-python 우선, 없으면 spec 반환 (브라우저에서 렌더).
    if is_vl_convert_available():
        try:
            import vl_convert as vlc  # type: ignore  # pragma: no cover
            svg = vlc.vegalite_to_svg(json.dumps(themed))
            return svg
        except Exception as e:  # pragma: no cover
            logger.warning(
                "[vega_adapter] vl_convert SVG render failed: %s — falling back to spec",
                e,
            )
            return themed

    if is_vega_cli_available():  # pragma: no cover  — npm 환경에서만 검증
        import subprocess
        try:
            proc = subprocess.run(
                ["vl2svg"],
                input=json.dumps(themed),
                capture_output=True,
                text=True,
                timeout=15,
                check=True,
            )
            return proc.stdout
        except Exception as e:
            logger.warning(
                "[vega_adapter] vl2svg CLI render failed: %s — falling back to spec",
                e,
            )
            return themed

    # 의존성 없음 — themed spec dict 반환 (브라우저 vega-embed 가 렌더).
    logger.info(
        "[vega_adapter] vl-convert / vega-cli 미설치 — themed spec dict 반환 "
        "(브라우저 vega-embed 가 렌더하는 경로)"
    )
    return themed


# ─── Spec 형식 검증 — Phase 6 Gate A 의 사전 구현 ──────────────────────


_TOP_LEVEL_REQUIRED = {"$schema", "data"}
_VEGA_LITE_SCHEMA_PREFIX = "https://vega.github.io/schema/vega-lite/"


def validate_vega_spec(spec: dict[str, Any]) -> None:
    """Vega-Lite spec 의 *기본* 형식 검증. Plan §7.2 (다) 의 사전 구현.

    Phase 6 Gate A (Schema Validation) 가 본격 활성될 때 본 함수가 1차 가드로
    호출됨. 본 함수는 *결정적* (LLM 0).

    Raises:
        VegaSpecError: spec 형식 결함.
    """
    if not isinstance(spec, dict):
        raise VegaSpecError(f"spec must be dict, got {type(spec).__name__}")

    # $schema 필드 — 없어도 vl-convert 가 처리하지만 명시 권장.
    schema = spec.get("$schema", "")
    if schema and not schema.startswith(_VEGA_LITE_SCHEMA_PREFIX):
        raise VegaSpecError(
            f"$schema 가 Vega-Lite 스키마가 아님: {schema!r}"
        )

    # data 필드 — values, url, name, sequence 중 하나는 있어야.
    data = spec.get("data")
    if data is None:
        raise VegaSpecError("spec.data 필드 누락 — 데이터 없는 차트 emit (CHART-AP-7)")

    if isinstance(data, dict):
        if not any(k in data for k in ("values", "url", "name", "sequence")):
            raise VegaSpecError(
                "spec.data 에 values/url/name/sequence 중 하나 필요 (CHART-AP-7)"
            )
        # data.values 가 빈 배열이면 차트 자체 의미 X (AP-7).
        values = data.get("values")
        if values is not None and isinstance(values, list) and len(values) == 0:
            raise VegaSpecError("spec.data.values 가 빈 배열 — CHART-AP-7")

    # mark 또는 layer / facet / concat / repeat 중 하나는 있어야 (Vega-Lite 필수).
    has_mark_or_view = any(
        k in spec
        for k in ("mark", "layer", "concat", "hconcat", "vconcat", "facet", "repeat")
    )
    if not has_mark_or_view:
        raise VegaSpecError(
            "spec 에 mark / layer / facet / concat / repeat 중 하나 필요"
        )


# ─── 호환 — v4.5.7 의 ComposedSection.charts dict → Vega-Lite spec ──────


_TYPE_TO_VEGA_MARK = {
    "bar":     "bar",
    "donut":   "arc",
    "line":    "line",
    "stacked": "bar",
    "bubble":  "circle",
    "heatmap": "rect",
    # gantt / network 는 단순 1:1 매핑 안 됨 — 별도 spec 빌더 필요.
    "gantt":   "bar",
    "network": "rect",   # Vega-Lite 에는 force-directed network 가 직접 없음.
}


def chart_dict_to_vega_spec(chart: dict[str, Any]) -> dict[str, Any]:
    """v4.5.7 의 ``ComposedSection.charts`` dict 형식을 *최소* Vega-Lite spec 으로 변환.

    Plan §7.7 의 자동 해결 antipattern 8종 중 *호환 변환* 부분. 단순 변환이라
    원본의 모든 의미를 보존하지 않을 수 있음 — VisualPlanner 가 Vega-Lite spec
    을 *직접* emit 하는 게 본 plan 의 의도. 본 함수는 *마이그레이션 보조* 도구.

    Args:
        chart: {"type": str, "title": str, "data": list|dict, "note"?: str}.

    Returns:
        Vega-Lite spec dict — apply_theme_to_spec 적용 가능.

    Raises:
        VegaSpecError: type 이 매핑 안 됨 또는 data 비어있음.
    """
    chart_type = (chart.get("type") or "").lower()
    if chart_type not in _TYPE_TO_VEGA_MARK:
        raise VegaSpecError(
            f"chart_dict_to_vega_spec: type {chart_type!r} 미지원. "
            f"VisualPlanner 가 Vega-Lite spec 을 직접 emit 하도록 권장."
        )

    data = chart.get("data")
    if not data:
        raise VegaSpecError("chart_dict_to_vega_spec: data 비어있음")

    mark = _TYPE_TO_VEGA_MARK[chart_type]

    # 가장 단순한 spec — 사용자가 Vega-Lite spec 으로 점진 마이그레이션할 수 있도록.
    spec: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": chart.get("title", ""),
        "data": {"values": data if isinstance(data, list) else [data]},
        "mark": mark,
        "width": 560,
        "height": 280,
    }

    # type 별 encoding 힌트 — 완전한 spec 은 아니지만 vl-convert 가 처리 가능.
    if chart_type == "bar":
        spec["encoding"] = {
            "x": {"field": "label", "type": "nominal"},
            "y": {"field": "value", "type": "quantitative"},
        }
    elif chart_type == "donut":
        spec["mark"] = {"type": "arc", "innerRadius": 50}
        spec["encoding"] = {
            "theta": {"field": "value", "type": "quantitative"},
            "color": {"field": "label", "type": "nominal"},
        }
    elif chart_type == "line":
        spec["encoding"] = {
            "x": {"field": "x", "type": "temporal"},
            "y": {"field": "y", "type": "quantitative"},
        }
    elif chart_type == "bubble":
        spec["encoding"] = {
            "x": {"field": "x", "type": "quantitative"},
            "y": {"field": "y", "type": "quantitative"},
            "size": {"field": "size", "type": "quantitative"},
        }
    elif chart_type == "heatmap":
        spec["encoding"] = {
            "x": {"field": "x", "type": "nominal"},
            "y": {"field": "y", "type": "nominal"},
            "color": {"field": "value", "type": "quantitative"},
        }

    return spec
