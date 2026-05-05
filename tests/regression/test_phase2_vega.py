"""V5 Phase 2 — Visualization Decoupling regression test.

Plan §7.8 인수 기준:
    1. src/visual_builder.py 의 11개 type-specific 함수 폐기, render_vega_lite()
       단일 어댑터로 대체.   ← Phase 2 *코드 단계* 에선 어댑터 신설 / v4.5.7
       의 visual_builder 는 보존 (호출 경로 byte-equal). 폐기는 활성 시점.
    2. VisualPlanner 가 prose 를 읽고 *최소 1종 새 차트 type* (예: Sankey 또는
       Treemap) 을 emit 하는 demo. ← LLM 호출 가능 환경에서만 측정.
    3. Editor → VisualPlanner 호출 순서. ← orchestrator 통합 시점에 검증.
    4. 모든 차트가 V5 design token 으로 강제 적용됨. ← apply_theme_to_spec
       이 spec.config 를 *덮어쓴다* 검증.
    5. AP-1 ~ AP-13 중 라이브러리로 자동 해결되는 8개 항목이 회귀에서 0회.

본 모듈은 #4 + #5 를 결정적으로 검증. #2 / #3 은 통합 후 측정.
"""

from __future__ import annotations

import copy

from tests.regression._pytest_compat import pytest

from src.visual.v5_theme import (
    BURGUNDY_TOKENS,
    EDITORIAL_TOKENS,
    V5_FONTS,
    V5_THEME,
    apply_theme_to_spec,
    get_theme_config,
    get_token_set,
)
from src.visual.vega_adapter import (
    VegaSpecError,
    chart_dict_to_vega_spec,
    is_vl_convert_available,
    render_vega_lite,
    validate_vega_spec,
)


# ─── Plan §19 design token SSOT 정합성 ──────────────────────────────


def test_editorial_tokens_match_plan_19_2() -> None:
    """Plan §19.2 의 Editorial Cream 토큰이 byte-equal."""
    assert EDITORIAL_TOKENS["bg"] == "#F2EBDB"
    assert EDITORIAL_TOKENS["card"] == "#ECE3D0"
    assert EDITORIAL_TOKENS["text"] == "#1F1814"
    assert EDITORIAL_TOKENS["accent"] == "#B05A38"
    assert EDITORIAL_TOKENS["up"] == "#4A6B3E"
    assert EDITORIAL_TOKENS["down"] == "#8B2A2A"
    assert EDITORIAL_TOKENS["series"] == ["#1F1814", "#B05A38", "#4A6B3E", "#6B5C4A"]


def test_burgundy_tokens_match_plan_19_3() -> None:
    """Plan §19.3 의 Burgundy Mono 토큰이 byte-equal."""
    assert BURGUNDY_TOKENS["bg"] == "#2A0F18"
    assert BURGUNDY_TOKENS["card"] == "#371721"
    assert BURGUNDY_TOKENS["text"] == "#EFE5D1"
    assert BURGUNDY_TOKENS["accent"] == "#D4A858"        # gold
    assert BURGUNDY_TOKENS["up"] == "#A8B582"
    assert BURGUNDY_TOKENS["down"] == "#C9837A"
    assert BURGUNDY_TOKENS["series"] == ["#EFE5D1", "#D4A858", "#A8B582", "#C9837A"]


def test_fonts_match_plan_19_4() -> None:
    """Plan §19.4 의 3종 폰트 트리플렛 보존."""
    assert "Newsreader" in V5_FONTS["title"]
    assert "Noto Serif KR" in V5_FONTS["title"]
    assert "IBM Plex Sans KR" in V5_FONTS["body"]
    assert "IBM Plex Mono" in V5_FONTS["mono"]


def test_v5_theme_registry_has_two_themes() -> None:
    """Plan §19.1 — Editorial + Burgundy 두 테마만."""
    assert set(V5_THEME.keys()) == {"editorial", "burgundy"}


def test_get_token_set_exports_css_variables() -> None:
    css_tokens = get_token_set("editorial")
    assert "--bg" in css_tokens
    assert css_tokens["--bg"] == "#F2EBDB"
    assert "--accent" in css_tokens
    assert css_tokens["--accent"] == "#B05A38"
    # series 는 1~4 로 enumerate.
    assert "--series-1" in css_tokens
    assert css_tokens["--series-1"] == "#1F1814"
    assert css_tokens["--series-4"] == "#6B5C4A"


# ─── Plan §7.4 — Vega-Lite config 강제 적용 ──────────────────────────


def _minimal_vega_spec() -> dict:
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": "테스트",
        "data": {"values": [{"x": 1, "y": 30}, {"x": 2, "y": 80}]},
        "mark": "bar",
        "encoding": {
            "x": {"field": "x", "type": "ordinal"},
            "y": {"field": "y", "type": "quantitative"},
        },
    }


def test_apply_theme_overwrites_existing_config() -> None:
    """AP-V5-2 — composer 가 색을 박아도 V5 config 가 *덮어쓴다*."""
    spec = _minimal_vega_spec()
    # composer 가 임의 색을 박은 케이스 — 무시되어야.
    spec["config"] = {"background": "#FF0000", "mark": {"color": "#00FF00"}}

    themed = apply_theme_to_spec(spec, theme="editorial", overwrite_existing_config=True)
    assert themed["config"]["background"] == EDITORIAL_TOKENS["bg"]
    assert themed["config"]["mark"]["color"] == EDITORIAL_TOKENS["accent"]
    # 원본 spec 은 변형되지 않음 (deepcopy).
    assert spec["config"]["background"] == "#FF0000"


def test_apply_theme_burgundy_uses_gold_accent() -> None:
    spec = _minimal_vega_spec()
    themed = apply_theme_to_spec(spec, theme="burgundy")
    assert themed["config"]["background"] == "#2A0F18"
    assert themed["config"]["mark"]["color"] == "#D4A858"


def test_apply_theme_unknown_raises() -> None:
    spec = _minimal_vega_spec()
    with pytest.raises(ValueError):
        apply_theme_to_spec(spec, theme="rainbow")  # type: ignore[arg-type]


def test_get_theme_config_axis_grid_dash_per_plan_19_5() -> None:
    """Plan §19.5 — 그리드 라인 stroke 0.5px, dash [2,3], opacity 0.55."""
    cfg = get_theme_config("editorial")
    axis = cfg["axis"]
    assert axis["gridDash"] == [2, 3]
    assert axis["gridWidth"] == 0.5
    assert axis["gridOpacity"] == 0.55


def test_get_theme_config_range_category_uses_single_accent() -> None:
    """Plan §19.5 — 단일 액센트 정책 (range.category[0] = accent)."""
    cfg = get_theme_config("editorial")
    assert cfg["range"]["category"][0] == EDITORIAL_TOKENS["accent"]


# ─── Plan §7.4 — render_vega_lite 어댑터 ─────────────────────────────


def test_render_vega_lite_spec_only_returns_themed_dict() -> None:
    spec = _minimal_vega_spec()
    result = render_vega_lite(spec, theme="editorial", output="spec_only")
    assert isinstance(result, dict)
    assert result["config"]["background"] == EDITORIAL_TOKENS["bg"]
    assert result["data"]["values"] == [{"x": 1, "y": 30}, {"x": 2, "y": 80}]


def test_render_vega_lite_force_width_height() -> None:
    """CHART-AP-4 가드 — width/height 가 강제로 박힘."""
    spec = _minimal_vega_spec()
    result = render_vega_lite(spec, output="spec_only", width=800, height=400)
    assert result["width"] == 800
    assert result["height"] == 400


def test_render_vega_lite_falls_back_when_vl_convert_missing() -> None:
    """vl-convert 미설치 환경에서 spec dict 로 fallback."""
    spec = _minimal_vega_spec()
    result = render_vega_lite(spec, output="svg")
    if is_vl_convert_available():
        # 설치되어 있으면 SVG 문자열.
        assert isinstance(result, str)
        assert "<svg" in result.lower() or "<?xml" in result.lower()
    else:
        # 미설치면 themed spec dict.
        assert isinstance(result, dict)
        assert result["config"]["background"] == EDITORIAL_TOKENS["bg"]


# ─── Plan §7.2 / Phase 6 Gate A 사전 — validate_vega_spec ───────────


def test_validate_vega_spec_passes_clean() -> None:
    spec = _minimal_vega_spec()
    validate_vega_spec(spec)  # raises 없음.


def test_validate_vega_spec_rejects_non_dict() -> None:
    with pytest.raises(VegaSpecError):
        validate_vega_spec("not a dict")  # type: ignore[arg-type]


def test_validate_vega_spec_rejects_missing_data() -> None:
    spec = {"$schema": "https://vega.github.io/schema/vega-lite/v5.json", "mark": "bar"}
    with pytest.raises(VegaSpecError):
        validate_vega_spec(spec)


def test_validate_vega_spec_rejects_empty_data_values() -> None:
    """CHART-AP-7 사전 가드."""
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": []},
        "mark": "bar",
    }
    with pytest.raises(VegaSpecError) as exc:
        validate_vega_spec(spec)
    assert "CHART-AP-7" in str(exc.value)


def test_validate_vega_spec_rejects_no_mark_or_view() -> None:
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": [{"x": 1}]},
    }
    with pytest.raises(VegaSpecError):
        validate_vega_spec(spec)


def test_validate_vega_spec_rejects_non_vega_lite_schema() -> None:
    spec = {
        "$schema": "https://vega.github.io/schema/vega/v5.json",   # 일반 Vega
        "data": {"values": [{"x": 1}]},
        "mark": "bar",
    }
    with pytest.raises(VegaSpecError):
        validate_vega_spec(spec)


# ─── chart_dict_to_vega_spec — v4.5.7 호환 변환 ────────────────────


def test_chart_dict_to_vega_spec_bar() -> None:
    chart = {
        "type": "bar",
        "title": "테스트",
        "data": [{"label": "A", "value": 30}, {"label": "B", "value": 80}],
    }
    spec = chart_dict_to_vega_spec(chart)
    assert spec["mark"] == "bar"
    assert spec["data"]["values"] == chart["data"]
    validate_vega_spec(spec)


def test_chart_dict_to_vega_spec_donut_uses_arc() -> None:
    chart = {
        "type": "donut",
        "title": "테스트",
        "data": [{"label": "A", "value": 30}],
    }
    spec = chart_dict_to_vega_spec(chart)
    assert spec["mark"]["type"] == "arc"
    assert spec["mark"]["innerRadius"] == 50


def test_chart_dict_to_vega_spec_unknown_type_fails() -> None:
    chart = {"type": "totally_new_type", "data": [{"v": 1}]}
    with pytest.raises(VegaSpecError):
        chart_dict_to_vega_spec(chart)


def test_chart_dict_to_vega_spec_empty_data_fails() -> None:
    chart = {"type": "bar", "data": []}
    with pytest.raises(VegaSpecError):
        chart_dict_to_vega_spec(chart)


# ─── Plan §7.7 — antipattern 자동 해결 매핑 검증 ──────────────────────


def test_chart_ap1_color_field_supported_by_vega_lite() -> None:
    """AP-1 (group/category 시각 분리) — Vega-Lite encoding.color 가 자동 처리."""
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": [
            {"label": "A", "value": 30, "group": "x"},
            {"label": "B", "value": 80, "group": "y"},
        ]},
        "mark": "bar",
        "encoding": {
            "x": {"field": "label", "type": "nominal"},
            "y": {"field": "value", "type": "quantitative"},
            "color": {"field": "group", "type": "nominal"},
        },
    }
    validate_vega_spec(spec)
    themed = apply_theme_to_spec(spec, theme="editorial")
    # color 인코딩 보존 + V5 range.category 가 색을 결정 (단일 accent 정책).
    assert themed["encoding"]["color"]["field"] == "group"
    assert "range" in themed["config"]


def test_chart_ap11_card_background_uses_v5_token() -> None:
    """AP-11 (차트 카드 배경 하드코딩) — V5 token 강제."""
    spec = _minimal_vega_spec()
    themed = apply_theme_to_spec(spec, theme="editorial")
    assert themed["background"] == EDITORIAL_TOKENS["bg"]
    # 배경에 #321F1F (v4.5.3 회귀의 잘못된 fallback) 가 절대 없음.
    assert "#321F1F" not in str(themed["config"])


def test_chart_ap12_bubble_extent_handled_by_vega_lite() -> None:
    """AP-12 (버블 차트 스케일 고정) — Vega-Lite 가 도메인 자동 감지."""
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "data": {"values": [
            {"x": 0.6, "y": 0.7, "size": 0.5},
            {"x": 30, "y": 70, "size": 50},  # 0~100 스케일이 섞임
        ]},
        "mark": "circle",
        "encoding": {
            "x": {"field": "x", "type": "quantitative"},
            "y": {"field": "y", "type": "quantitative"},
            "size": {"field": "size", "type": "quantitative"},
        },
    }
    validate_vega_spec(spec)
    # Vega-Lite 가 자동으로 extent 계산. 회귀의 v4.5.3 buggy `domain([0,1])` 강제 없음.
    themed = apply_theme_to_spec(spec, theme="editorial")
    assert "domain" not in themed["encoding"]["x"].get("scale", {})
