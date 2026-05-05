"""V5 Phase 2 — Design token SSOT (Plan §19).

Plan §19.6 의 SSOT 정책:
    samples/chart_map_mono_compare.html  ← 사람-친화 시각 레퍼런스
    src/templates/themes/editorial.css   ← :root[data-theme="editorial"] 토큰
    src/templates/themes/burgundy.css    ← :root[data-theme="burgundy"] 토큰
    src/visual/v5_theme.py:V5_THEME      ← Vega-Lite config 토큰 (본 모듈)

위 4곳이 *byte-equal* 일치해야 한다 (drift 검증 회귀 테스트가 강제).
본 모듈은 Vega-Lite config 토큰의 코드 SSOT.

[사용]
    from src.visual.v5_theme import (
        V5_THEME,
        get_theme_config,
        apply_theme_to_spec,
        EDITORIAL_TOKENS,
        BURGUNDY_TOKENS,
    )

[Plan §19.5 차트 시각 규칙 — Vega-Lite config 로 박힘]
- 단일 액센트만 색상으로 사용 (range.category[0] = accent, 나머지는 series + dash 패턴).
- 그리드 라인 stroke 0.5px, dash [2,3], opacity 0.55.
- 영역 채움은 45° 사선 패턴 (Vega-Lite 의 fillPattern 또는 fillOpacity 로 매핑).
- 차트당 annotation 합계 ≤ 3 (annotation 카운트 가드는 Phase 6 Critic).
- 이모지 마커 금지.
"""

from __future__ import annotations

from typing import Any, Literal

# ─── Plan §19.2 Editorial Cream — 정본 토큰 ─────────────────────────────

EDITORIAL_TOKENS = {
    # surfaces
    "bg":           "#F2EBDB",
    "card":         "#ECE3D0",
    "card_deep":    "#E5DBC4",       # v4.5.3 의 --card-deep
    "border":       "#D4C8B0",
    "border_light": "#E2D8C0",
    # type
    "text":   "#1F1814",
    "muted":  "#6B5C4A",
    "faded":  "#A89A7E",
    # accent
    "accent": "#B05A38",              # terracotta
    "up":     "#4A6B3E",
    "down":   "#8B2A2A",
    # 4-series + dash 패턴
    "series": ["#1F1814", "#B05A38", "#4A6B3E", "#6B5C4A"],
    "series_dash": [None, [5, 3], [2, 3], [1, 3]],
    # map
    "map_land":     "#F2EBDB",
    "map_water":    "#DFD3B8",
    "map_boundary": "#1F1814",
}


# ─── Plan §19.3 Burgundy Mono — 정본 토큰 ──────────────────────────────

BURGUNDY_TOKENS = {
    "bg":           "#2A0F18",
    "card":         "#371721",
    "card_deep":    "#1A0810",
    "border":       "#5A2832",
    "border_light": "#371721",
    "text":   "#EFE5D1",
    "muted":  "#A88E7A",
    "faded":  "#6B5040",
    "accent": "#D4A858",              # gold
    "up":     "#A8B582",
    "down":   "#C9837A",
    "series": ["#EFE5D1", "#D4A858", "#A8B582", "#C9837A"],
    "series_dash": [None, [5, 3], [2, 3], [1, 3]],
    "map_land":     "#2A0F18",
    "map_water":    "#1A0810",
    "map_boundary": "#EFE5D1",
}


# ─── Plan §19.4 폰트 — 3종 트리플렛 고정 ──────────────────────────────

V5_FONTS = {
    "title":  "Newsreader, 'Noto Serif KR', serif",        # 헤드라인·차트 제목
    "body":   "'IBM Plex Sans KR', 'Noto Sans KR', sans-serif",  # 본문·축 라벨
    "mono":   "'IBM Plex Mono', monospace",                # 수치·일련번호
}


# ─── Theme registry ────────────────────────────────────────────────────

ThemeName = Literal["editorial", "burgundy"]

V5_THEME: dict[ThemeName, dict[str, Any]] = {
    "editorial": EDITORIAL_TOKENS,
    "burgundy":  BURGUNDY_TOKENS,
}


# ─── Vega-Lite config 빌더 ────────────────────────────────────────────


def get_theme_config(theme: ThemeName = "editorial") -> dict[str, Any]:
    """Vega-Lite spec 의 ``config`` 필드에 박을 dict 반환.

    Plan §19.5 의 차트 시각 규칙을 모두 적용한 *완성된* config.

    Args:
        theme: "editorial" (default) 또는 "burgundy".

    Returns:
        Vega-Lite config dict — spec.config 에 그대로 박으면 됨.
    """
    if theme not in V5_THEME:
        raise ValueError(f"Unknown V5 theme: {theme!r} — Plan §19.1 의 2종만 허용")

    t = V5_THEME[theme]
    return {
        "background": t["bg"],
        "title": {
            "color":         t["text"],
            "subtitleColor": t["muted"],
            "font":          V5_FONTS["title"],
            "subtitleFont":  V5_FONTS["body"],
            "fontSize":      14,
            "fontWeight":    "bold",
            "anchor":        "start",
            "subtitleFontSize": 11,
        },
        "axis": {
            "labelColor":     t["muted"],
            "titleColor":     t["text"],
            "labelFont":      V5_FONTS["body"],
            "titleFont":      V5_FONTS["body"],
            "labelFontSize":  10,
            "titleFontSize":  11,
            "gridColor":      t["border_light"],
            "gridOpacity":    0.55,
            "gridDash":       [2, 3],         # Plan §19.5
            "gridWidth":      0.5,            # Plan §19.5
            "tickColor":      t["border"],
            "domainColor":    t["border"],
            "domainWidth":    0.5,
        },
        "legend": {
            "labelColor":     t["muted"],
            "titleColor":     t["text"],
            "labelFont":      V5_FONTS["body"],
            "titleFont":      V5_FONTS["body"],
            "labelFontSize":  10,
            "titleFontSize":  11,
        },
        "view": {
            "stroke": "transparent",          # 차트 카드의 테두리는 호스트 CSS 가 담당
        },
        "range": {
            # 단일 accent + 3 종 series. Plan §19.5 단일 액센트 정책.
            "category": [t["accent"]] + t["series"][1:],
            "ramp":     [t["card_deep"], t["accent"], t["text"]],
            "diverging": [t["down"], t["card"], t["up"]],
        },
        "mark": {
            # 이모지 / 점 마커 금지 — 기본 mark 색은 accent.
            "color":         t["accent"],
            "stroke":        t["text"],
            "strokeWidth":   0.5,
            "tooltip":       True,
        },
        "bar": {
            "fill":            t["accent"],
            "stroke":          t["text"],
            "strokeWidth":     0.5,
            "fillOpacity":     0.85,           # 45° 패턴 적용 시 sparingly opacity
        },
        "line": {
            "stroke":          t["accent"],
            "strokeWidth":     1.5,
        },
        "area": {
            "fill":            t["accent"],
            "fillOpacity":     0.55,
            "stroke":          t["accent"],
            "strokeWidth":     1.0,
        },
        "point": {
            "fill":            t["accent"],
            "stroke":          t["text"],
            "strokeWidth":     0.5,
            "size":            40,
        },
        "text": {
            "color":           t["text"],
            "font":            V5_FONTS["body"],
            "fontSize":        10,
        },
    }


def apply_theme_to_spec(
    spec: dict[str, Any],
    theme: ThemeName = "editorial",
    *,
    overwrite_existing_config: bool = True,
) -> dict[str, Any]:
    """Vega-Lite spec 에 V5 design token 을 *덮어쓴다* (Plan §7.5).

    LLM 또는 외부 입력이 spec 에 색·폰트를 박아도 *무시* 하고 V5 token 으로
    강제 적용. AP-V5-2 (Vega-Lite spec 의 색 직접 지정 금지) 의 가드.

    Args:
        spec: 원본 Vega-Lite spec dict. 변형되지 않음 (deepcopy 후 반환).
        theme: 적용할 V5 테마.
        overwrite_existing_config: True 면 기존 spec.config 를 *완전히 덮어씀*.
            False 면 기존 config 와 V5 config 를 머지하되 충돌 시 V5 우선.

    Returns:
        새 spec dict — V5 theme 적용된 사본.
    """
    import copy

    out = copy.deepcopy(spec)
    v5_config = get_theme_config(theme)

    if overwrite_existing_config or "config" not in out:
        out["config"] = v5_config
    else:
        # 머지 — 기존 config 의 키 중 V5 가 정의한 것은 V5 우선.
        existing = out.get("config") or {}
        merged: dict[str, Any] = {**existing}
        for key, val in v5_config.items():
            if isinstance(val, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged[key], **val}
            else:
                merged[key] = val
        out["config"] = merged

    # 추가 가드 — top-level background / mark / encoding 의 직접 색 지정도 정리.
    # spec 자체에 박힌 'background' 는 V5 token 으로.
    out["background"] = v5_config["background"]

    return out


# ─── SSOT drift 검증 ──────────────────────────────────────────────────


def get_token_set(theme: ThemeName = "editorial") -> dict[str, str]:
    """CSS variable 형태로 토큰 export — drift 검증 회귀 테스트가 사용.

    samples/chart_map_mono_compare.html / src/templates/report.css 의 :root
    선언과 *byte-equal* 일치해야 한다. 회귀 테스트
    (test_design_token_drift) 가 본 함수의 출력을 위 두 파일과 정합 검증.
    """
    t = V5_THEME[theme]
    flat: dict[str, str] = {}
    for key, val in t.items():
        if isinstance(val, str):
            flat[f"--{key.replace('_', '-')}"] = val
        elif isinstance(val, list):
            for i, v in enumerate(val, start=1):
                if isinstance(v, str):
                    flat[f"--{key.replace('_', '-')}-{i}"] = v
    return flat
