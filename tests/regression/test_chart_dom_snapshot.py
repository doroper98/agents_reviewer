"""차트 렌더 DOM 스냅샷 회귀 (CHART_REDESIGN_V8_6_PLAN.md §3.2, v8.6.0).

두 층으로 나뉜다.

1. **구조 검증 (항상 실행, 브라우저 불요)** — 갤러리 fixture 가 production
   ``RENDERERS`` 와 1:1 인지, 폐기된 ``network`` 가 남아 있지 않은지,
   baseline JSON 이 그 목록과 일치하는지. CHART-AP-17(type starvation)·
   CHART-AP-36(폐기 type 잔존) 의 갤러리 측 재발 차단.
2. **렌더 대조 (헤드리스 chromium 있을 때만)** — 실제로 렌더한 DOM 해시가
   baseline 과 같은지. chromium 이 없으면 skip (플랜 §3.2).

렌더 대조는 기본 1테마(midnight_indigo)만 돈다 — 전 6테마 확인은
``python scripts/chart_dom_snapshot.py --check tests/regression/fixtures/chart_dom_baseline.json``
가 담당한다. 환경변수 ``CHART_DOM_SNAPSHOT_THEMES`` 로 넓힐 수 있다.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from tests.regression._pytest_compat import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import chart_dom_snapshot as snap  # noqa: E402

GALLERY = REPO_ROOT / "samples" / "chart_gallery_v7.html"
CHARTS_JS = REPO_ROOT / "src" / "templates" / "static" / "charts.js"
BASELINE = REPO_ROOT / "tests" / "regression" / "fixtures" / "chart_dom_baseline.json"

TEST_THEMES = tuple(
    t.strip()
    for t in os.environ.get("CHART_DOM_SNAPSHOT_THEMES", "midnight_indigo").split(",")
    if t.strip()
)


# ─── 헬퍼 ────────────────────────────────────────────────────────────
def _renderer_types() -> set[str]:
    """charts.js 의 ``RENDERERS`` dict 키 집합."""
    src = CHARTS_JS.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"const RENDERERS = \{(.*?)\n  \};", src, re.S)
    assert m, "charts.js 의 RENDERERS 블록을 찾지 못했다"
    return set(re.findall(r"([a-z_]+):\s*draw[A-Z]", m.group(1)))


def _gallery_types() -> list[str]:
    src = GALLERY.read_text(encoding="utf-8")
    return re.findall(r"\{\s*type:\s*'([a-z_]+)'", src)


def _baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


# ─── 1. 구조 검증 ─────────────────────────────────────────────────────
def test_gallery_covers_every_renderer() -> None:
    """갤러리 fixture ↔ RENDERERS 1:1 (CHART-AP-17 갤러리 측 가드)."""
    gallery, renderers = set(_gallery_types()), _renderer_types()
    assert gallery == renderers, (
        f"갤러리에만 있는 type: {sorted(gallery - renderers)} / "
        f"RENDERERS 에만 있는 type: {sorted(renderers - gallery)}"
    )


def test_gallery_has_no_retired_network_fixture() -> None:
    """CHART-AP-36 — network 는 v7.9.17 에 폐기, 갤러리에 남으면 unknown type warn."""
    assert "network" not in _gallery_types()


def test_gallery_theme_buttons_match_tool_default() -> None:
    """갤러리 테마 버튼 목록 ↔ 스냅샷 도구 기본 테마 목록 정합."""
    src = GALLERY.read_text(encoding="utf-8")
    m = re.search(r"var THEMES = \[(.*?)\];", src, re.S)
    assert m, "갤러리의 THEMES 배열을 찾지 못했다"
    themes = tuple(re.findall(r"'([a-z_]+)'", m.group(1)))
    assert themes == snap.DEFAULT_THEMES
    assert "reportage_steel" in themes  # v8.6.0 추가


def test_baseline_covers_every_renderer_and_theme() -> None:
    doc = _baseline()
    assert doc["schema"] == 1
    assert set(doc["types"]) == _renderer_types()
    assert tuple(doc["themes"]) == snap.DEFAULT_THEMES
    for ctype, per_theme in doc["types"].items():
        assert tuple(sorted(per_theme)) == tuple(sorted(snap.DEFAULT_THEMES)), ctype
        for theme, entry in per_theme.items():
            assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]), (ctype, theme)
            # 요소 0 = 렌더러가 조기 return 한 것 (빈 카드 CHART-AP-28 클래스)
            assert entry["elements"] > 0, f"{ctype}/{theme} 이 아무것도 그리지 않았다"


def test_baseline_declares_getbbox_loose_types() -> None:
    """getBBox 로 viewBox 를 보정하는 3종은 폰트 의존 → loose 비교 대상."""
    assert set(_baseline()["loose_types"]) == set(snap.LOOSE_TYPES)
    assert set(snap.LOOSE_TYPES) == {"sankey", "dot_matrix", "stakeholder_map"}


def test_compare_tolerates_theme_subset_but_not_type_subset() -> None:
    """`--themes` 부분 실행은 diff 가 아니고, type 누락은 diff 다."""
    base = {
        "loose_types": list(snap.LOOSE_TYPES),
        "types": {
            "bar": {
                "a": {"sha256": "x", "elements": 3, "tags": "rect:3"},
                "b": {"sha256": "y", "elements": 3, "tags": "rect:3"},
            }
        },
    }
    same_subset = {"bar": {"a": {"sha256": "x", "elements": 3, "tags": "rect:3"}}}
    assert snap.compare(base, same_subset) == {}
    changed = {"bar": {"a": {"sha256": "z", "elements": 4, "tags": "rect:4"}}}
    assert "bar" in snap.compare(base, changed)
    assert "bar" in snap.compare(base, {})


def test_compare_loose_type_ignores_hash_but_catches_shape() -> None:
    base = {
        "loose_types": ["sankey"],
        "types": {"sankey": {"a": {"sha256": "x", "elements": 9, "tags": "path:9"}}},
    }
    hash_only = {"sankey": {"a": {"sha256": "DIFFERENT", "elements": 9, "tags": "path:9"}}}
    assert snap.compare(base, hash_only) == {}
    shape = {"sankey": {"a": {"sha256": "x", "elements": 11, "tags": "path:11"}}}
    assert "sankey" in snap.compare(base, shape)


# ─── 2. 렌더 대조 (chromium 있을 때만) ────────────────────────────────
def test_rendered_dom_matches_baseline() -> None:
    browser = snap.find_browser()
    if not browser:
        pytest.skip("헤드리스 chromium 없음 — 렌더 대조 skip (플랜 §3.2)")
    types, warnings = snap.collect(browser, TEST_THEMES)

    bad = [w for w in warnings if "unknown type" in w or "render error" in w]
    assert not bad, f"갤러리 렌더 중 경고: {bad}"

    diffs = snap.compare(_baseline(), types)
    assert not diffs, (
        "렌더 DOM 이 baseline 과 다르다 — 의도한 표현 변경이면 "
        "`python scripts/chart_dom_snapshot.py --out tests/regression/fixtures/"
        f"chart_dom_baseline.json` 로 갱신할 것. 변경 type: {sorted(diffs)}"
    )
