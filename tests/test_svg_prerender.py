"""v5.5.6 — svg_prerender (계약 §5 B안 폴백 SVG) 단위 테스트.

브라우저(Playwright/chromium) 불요: `_render_batch` 를 monkeypatch 하여 순수
로직 + bundle wiring (type 게이팅 / standalone 래핑 / graceful no-op) 만 검증.
실제 헤드리스 렌더는 VM 에서 smoke-test (pragma no cover).
"""

from __future__ import annotations

from types import SimpleNamespace

from src.handoff import svg_prerender as sp


_TOKENS = {
    "bg": "#F2EBDB", "card": "#ECE3D0", "text": "#1F1814", "muted": "#6B5C4A",
    "accent": "#B05A38", "up": "#4A6B3E", "down": "#8B2A2A", "border": "#D4C8B0",
}


def _chart(cid, ctype, data=None):
    return SimpleNamespace(
        chart_id=cid, type=ctype, title="t", note="", data=data or {"nodes": [1, 2]},
        prerendered_svg=None,
    )


# ─── B_PLAN 대상 집합 ──────────────────────────────────────────────────


def test_b_plan_types_are_the_three_complex_charts():
    assert sp.B_PLAN_CHART_TYPES == {"network", "choropleth", "sankey"}


# ─── _standalone_svg ───────────────────────────────────────────────────


def test_standalone_svg_injects_xmlns_and_bg_rect():
    out = sp._standalone_svg('<svg viewBox="-12 -12 100 80"><g></g></svg>', _TOKENS)
    assert 'xmlns="http://www.w3.org/2000/svg"' in out
    assert '<rect' in out and _TOKENS["card"] in out
    # 배경 rect 는 open tag 직후 (첫 자식 = 뒤).
    assert out.index("<rect") < out.index("<g>")
    assert out.endswith("</svg>")


def test_standalone_svg_passthrough_when_not_svg():
    assert sp._standalone_svg("", _TOKENS) == ""
    assert sp._standalone_svg("<div>x</div>", _TOKENS) == "<div>x</div>"


def test_standalone_svg_does_not_double_inject_xmlns():
    src = '<svg xmlns="http://www.w3.org/2000/svg"><g/></svg>'
    out = sp._standalone_svg(src, _TOKENS)
    assert out.count('xmlns="http://www.w3.org/2000/svg"') == 1


# ─── isolation HTML 빌더 ───────────────────────────────────────────────


def test_chart_isolation_html_has_payload_and_type_and_tokens():
    html = sp._chart_isolation_html(
        {"type": "network", "title": "T", "data": {"nodes": []}, "note": ""},
        "editorial_cream", _TOKENS,
    )
    assert 'data-chart-type="network"' in html
    assert 'class="chart-payload-inline"' in html
    assert '"type": "network"' in html
    assert "--accent: #B05A38" in html
    assert "charts.js" in html and "d3.v7.min.js" in html


def test_map_isolation_html_has_map_payload_and_topojson():
    html = sp._map_isolation_html({"center": [0, 0]}, "burgundy_mono", _TOKENS)
    assert 'id="freeform-map"' in html
    assert 'id="map-payload"' in html
    assert "topojson-client" in html
    assert "maps.js" in html


def test_style_block_falls_back_card_deep_to_card():
    block = sp._style_block("editorial_cream", _TOKENS)
    assert f"--card-deep: {_TOKENS['card']}" in block


# ─── prerender_chart_svgs — graceful + 게이팅 ───────────────────────────


def test_chart_prerender_noop_when_unavailable(monkeypatch):
    monkeypatch.setattr(sp, "is_prerender_available", lambda: False)
    charts = [_chart("ch-1", "network")]
    assert sp.prerender_chart_svgs(charts, "editorial_cream", _TOKENS) == 0
    assert charts[0].prerendered_svg is None


def test_chart_prerender_noop_when_no_tokens(monkeypatch):
    monkeypatch.setattr(sp, "is_prerender_available", lambda: True)
    charts = [_chart("ch-1", "network")]
    assert sp.prerender_chart_svgs(charts, "editorial_cream", {}) == 0


def test_chart_prerender_targets_only_b_plan_types(monkeypatch):
    monkeypatch.setattr(sp, "is_prerender_available", lambda: True)
    captured = {}

    def fake_render(items, selector, timeout_ms=8000):
        captured["keys"] = [k for k, _ in items]
        return {k: "<svg><g/></svg>" for k, _ in items}

    monkeypatch.setattr(sp, "_render_batch", fake_render)
    charts = [
        _chart("ch-1", "network"),
        _chart("ch-2", "bar"),          # A안 — 대상 아님
        _chart("ch-3", "sankey"),
        _chart("ch-4", "line"),         # A안 — 대상 아님
        _chart("ch-5", "choropleth"),
    ]
    n = sp.prerender_chart_svgs(charts, "editorial_cream", _TOKENS)
    assert n == 3
    assert set(captured["keys"]) == {"ch-1", "ch-3", "ch-5"}
    # B안만 채워지고 standalone 래핑됨.
    for c in charts:
        if c.type in sp.B_PLAN_CHART_TYPES:
            assert c.prerendered_svg and 'xmlns=' in c.prerendered_svg
        else:
            assert c.prerendered_svg is None


def test_chart_prerender_skips_empty_data(monkeypatch):
    monkeypatch.setattr(sp, "is_prerender_available", lambda: True)
    monkeypatch.setattr(sp, "_render_batch", lambda items, sel, timeout_ms=8000: {})
    charts = [SimpleNamespace(chart_id="ch-1", type="network", title="", note="",
                              data=None, prerendered_svg=None)]
    assert sp.prerender_chart_svgs(charts, "editorial_cream", _TOKENS) == 0


def test_chart_prerender_graceful_on_render_exception(monkeypatch):
    monkeypatch.setattr(sp, "is_prerender_available", lambda: True)

    def boom(items, selector, timeout_ms=8000):
        raise RuntimeError("no chromium")

    monkeypatch.setattr(sp, "_render_batch", boom)
    charts = [_chart("ch-1", "network")]
    assert sp.prerender_chart_svgs(charts, "editorial_cream", _TOKENS) == 0
    assert charts[0].prerendered_svg is None


# ─── prerender_map_svg ─────────────────────────────────────────────────


def test_map_prerender_sets_svg(monkeypatch):
    monkeypatch.setattr(sp, "is_prerender_available", lambda: True)
    monkeypatch.setattr(
        sp, "_render_batch",
        lambda items, sel, timeout_ms=12000: {"map": "<svg><path/></svg>"},
    )
    bm = SimpleNamespace(prerendered_svg=None)
    assert sp.prerender_map_svg(bm, {"center": [0, 0]}, "editorial_cream", _TOKENS) is True
    assert bm.prerendered_svg and "xmlns=" in bm.prerendered_svg


def test_map_prerender_noop_when_no_map(monkeypatch):
    monkeypatch.setattr(sp, "is_prerender_available", lambda: True)
    assert sp.prerender_map_svg(None, {"center": [0, 0]}, "x", _TOKENS) is False
    bm = SimpleNamespace(prerendered_svg=None)
    assert sp.prerender_map_svg(bm, {}, "x", _TOKENS) is False
