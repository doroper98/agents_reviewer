"""B안 (계약 §5) — 복잡 차트 4종의 정적 SVG 폴백 prerender.

osint_generator 가 cinematic 렌더러를 갖추기 전 *폴백* 으로 받는
`prerendered_svg` 를 채운다. 합의 (계약 v1, A안):

    · 17종 데이터-온리 차트 → consumer 가 family 렌더러로 직접 그림 (대상 아님).
    · 복잡 4종 (map / choropleth / network / sankey) → 폴백 SVG 제공 (B안).

[방식] 격리 렌더 — charts.js / maps.js 가 이미 그리는 DOM 구조를 최소 HTML 1장에
재현 → Playwright(headless chromium) 로 렌더 → 렌더된 `<svg>` outerHTML 추출 →
독립 SVG 로 래핑 (xmlns + 배경 rect). chart_id 별 1:1 격리라 매핑 모호성 없음.

[graceful] Playwright / chromium 미가용·렌더 실패·timeout 시 *조용히 None* —
기존 v5.5.x 동작 (계약 §5 의 null) 과 byte-equal. 보고서/번들 흐름 영향 0.
market_fetcher / image_fetcher / capture 와 동일한 graceful degrade 패턴.

[의존성]
    · charts.js 3종 (network/choropleth/sankey): 로컬 자산만 (d3.v7.min.js + charts.js).
    · map: 추가로 CDN fetch 2건 (topojson-client@3 + world-atlas@2/110m) — 렌더
      시점 네트워크 필요. 차단 환경에선 graceful None.
    · playwright (optional, capture.py 와 공유). 미설치 시 전체 no-op.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "templates" / "static"

# 계약 §5 B안 대상 — charts.js 가 그리는 복잡 차트. (map 은 별도 함수.)
# v8.6.2 — treemap/tree 추가: osint 렌더 게이트가 모르는 신규 type 이라
# prerendered_svg 폴백이 없으면 영상에서 무경고로 사라진다.
# ("network" 는 v7.9.17 폐기 type — 옛 번들 호환용으로만 남긴다.)
B_PLAN_CHART_TYPES = frozenset({
    "network", "choropleth", "sankey", "treemap", "tree",
    # v8.6.3 — 분포·달력 2종
    "histogram", "calendar_heat",
})

# CDN (report 템플릿과 동일 — maps.js 의 world-atlas fetch 용).
_TOPOJSON_CDN = "https://cdn.jsdelivr.net/npm/topojson-client@3"


def is_prerender_available() -> bool:
    """Playwright 설치 여부. (chromium 바이너리까지는 검사 안 함 — 렌더 실패 시 graceful.)"""
    try:
        from src.visual.capture import is_playwright_available
        return is_playwright_available()
    except Exception:
        return False


# ─── 순수 헬퍼 (브라우저 불요, 단위 테스트 대상) ──────────────────────────


def _style_block(theme_id: str, tokens: dict[str, str]) -> str:
    """:root 토큰 + chart-card-stage 최소 규칙. charts.js 가 getComputedStyle 로 읽음."""
    card_deep = tokens.get("card") or "#ffffff"  # report.css 는 card-deep 미정의 → card 폴백
    decls = "; ".join(f"--{k}: {v}" for k, v in tokens.items())
    sel = f':root, [data-theme="{theme_id}"]' if theme_id else ":root"
    return (
        f"{sel} {{ {decls}; --card-deep: {card_deep}; }}\n"
        "body { margin: 0; background: var(--bg); }\n"
        ".chart-card-stage { width: 760px; background: var(--card-deep); padding: 12px; }\n"
        "#freeform-map { width: 760px; background: var(--card-deep); padding: 12px; }\n"
        ".chart-card-stage svg, #freeform-map svg { display: block; width: 100%; height: auto; "
        "font-family: 'Noto Sans KR', sans-serif; }\n"
    )


def _asset_uri(name: str) -> str:
    return (_STATIC_DIR / name).as_uri()


def _chart_isolation_html(payload: dict, theme_id: str, tokens: dict[str, str]) -> str:
    """charts.js 가 자동 렌더하는 최소 페이지 (chart-card-stage + payload script)."""
    payload_json = json.dumps(payload, ensure_ascii=False)
    ctype = str(payload.get("type") or "bar")
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="ko" data-theme="{theme_id}"><head><meta charset="utf-8">\n'
        f"<style>\n{_style_block(theme_id, tokens)}</style>\n"
        f'<script src="{_asset_uri("d3.v7.min.js")}"></script>\n'
        f'</head><body data-theme="{theme_id}">\n'
        '<div class="chart-card"><div class="chart-card-stage" '
        f'data-chart-type="{ctype}" data-chart-id="c"><svg></svg></div>\n'
        f'<script type="application/json" class="chart-payload-inline">{payload_json}</script>\n'
        "</div>\n"
        f'<script src="{_asset_uri("charts.js")}"></script>\n'
        "</body></html>"
    )


def _map_isolation_html(em: dict, theme_id: str, tokens: dict[str, str]) -> str:
    """maps.js 가 자동 렌더하는 최소 페이지 (#freeform-map + #map-payload). CDN fetch 의존."""
    payload_json = json.dumps(em, ensure_ascii=False)
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="ko" data-theme="{theme_id}"><head><meta charset="utf-8">\n'
        f"<style>\n{_style_block(theme_id, tokens)}</style>\n"
        f'<script src="{_asset_uri("d3.v7.min.js")}"></script>\n'
        f'<script src="{_TOPOJSON_CDN}"></script>\n'
        f'</head><body data-theme="{theme_id}">\n'
        f'<div id="freeform-map" class="map-stage" data-theme="{theme_id}"></div>\n'
        f'<script type="application/json" id="map-payload">{payload_json}</script>\n'
        f'<script src="{_asset_uri("maps.js")}"></script>\n'
        "</body></html>"
    )


def _standalone_svg(svg_outer: str, tokens: dict[str, str]) -> str:
    """렌더된 <svg> outerHTML → 독립 SVG. xmlns 보강 + 배경 rect 삽입 (mono 스테이지 bg)."""
    s = (svg_outer or "").strip()
    if not s.startswith("<svg") or ">" not in s:
        return s
    open_tag, rest = s.split(">", 1)
    if "xmlns=" not in open_tag:
        open_tag = open_tag.replace(
            "<svg",
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:xlink="http://www.w3.org/1999/xlink"',
            1,
        )
    bg = tokens.get("card") or "#ffffff"
    # viewBox 전체를 덮는 거대 배경 rect (viewBox 음수 origin 대비 — 항상 첫 자식 = 뒤).
    bg_rect = f'<rect x="-100000" y="-100000" width="200000" height="200000" fill="{bg}"/>'
    return f"{open_tag}>{bg_rect}{rest}"


# ─── 브라우저 렌더 (pragma no cover — chromium 가용 환경에서만) ──────────


def _render_batch(
    items: list[tuple[str, str]],
    selector: str,
    timeout_ms: int = 8000,
) -> dict[str, str]:  # pragma: no cover  — 실제 chromium 환경에서만 실행
    """(key, html) 목록을 헤드리스 렌더 → key → selector 의 outerHTML.

    실패 key 는 빈 문자열. 단일 browser/context 재사용 (per-chart page).
    """
    import os
    import tempfile

    from playwright.sync_api import sync_playwright

    out: dict[str, str] = {}
    wait_js = (
        "() => { const e = document.querySelector(%r); "
        "return !!(e && e.querySelector('*')); }" % selector
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 900, "height": 760})
        for key, html in items:
            page = ctx.new_page()
            tmp_name = ""
            try:
                with tempfile.NamedTemporaryFile(
                    "w", suffix=".html", delete=False, encoding="utf-8",
                ) as tmp:
                    tmp.write(html)
                    tmp_name = tmp.name
                page.goto(Path(tmp_name).as_uri(), timeout=timeout_ms)
                try:
                    page.wait_for_function(wait_js, timeout=timeout_ms)
                except Exception:
                    pass  # 렌더 미완 → el 추출 시도 후 빈 문자열일 수 있음
                el = page.query_selector(selector)
                out[key] = el.evaluate("e => e.outerHTML") if el else ""
            except Exception as e:
                logger.warning("[svg_prerender] render fail (%s): %s", key, e)
                out[key] = ""
            finally:
                page.close()
                if tmp_name:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass
        browser.close()
    return out


# ─── 공개 API (bundle_builder 가 호출) ──────────────────────────────────


def prerender_chart_svgs(
    charts: list,
    theme_id: str,
    tokens: dict[str, str],
) -> int:
    """B안 대상 차트(network/choropleth/sankey)의 prerendered_svg 를 채운다 (in-place).

    Returns: 채운 개수. 미가용/실패 시 0 (charts 무변경).
    """
    if not tokens or not is_prerender_available():
        return 0
    targets = {
        c.chart_id: c
        for c in charts
        if getattr(c, "type", "") in B_PLAN_CHART_TYPES and getattr(c, "data", None)
    }
    if not targets:
        return 0
    items = [
        (cid, _chart_isolation_html(
            {"type": c.type, "title": c.title, "data": c.data, "note": c.note},
            theme_id, tokens,
        ))
        for cid, c in targets.items()
    ]
    try:
        rendered = _render_batch(items, ".chart-card-stage svg")
    except Exception as e:
        logger.warning("[svg_prerender] chart batch failed (graceful): %s", e)
        return 0
    n = 0
    for cid, svg in rendered.items():
        if svg:
            targets[cid].prerendered_svg = _standalone_svg(svg, tokens)
            n += 1
    return n


def prerender_map_svg(
    bundle_map,
    embedded_map: dict,
    theme_id: str,
    tokens: dict[str, str],
) -> bool:
    """BundleMap.prerendered_svg 를 채운다 (CDN fetch 의존). 성공 True."""
    if bundle_map is None or not embedded_map or not tokens:
        return False
    if not is_prerender_available():
        return False
    html = _map_isolation_html(embedded_map, theme_id, tokens)
    try:
        rendered = _render_batch([("map", html)], "#freeform-map svg", timeout_ms=12000)
    except Exception as e:
        logger.warning("[svg_prerender] map render failed (graceful): %s", e)
        return False
    svg = rendered.get("map") or ""
    if not svg:
        return False
    bundle_map.prerendered_svg = _standalone_svg(svg, tokens)
    return True
