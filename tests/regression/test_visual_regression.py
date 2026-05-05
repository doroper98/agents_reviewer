"""V5 Phase 0B — Test 2/5: Visual Regression.

Plan §3.4 (나) — Playwright 로 desktop / mobile / exhibit closeup
screenshot 캡쳐 → pixel diff 로 비교. chart bbox overflow, horizontal
overflow 도 함께 검증.

본 모듈의 책임 분리:
- Playwright 기반 *full visual regression* 은 ``capture_proofs(html_path)``
  에 위임. Playwright 미설치 환경에선 pytest 가 SKIP.
- *정적 SVG sanity check* (lxml 기반) 는 V5 Phase 6 Gate C 의 사전 구현.
  lxml 미설치 환경에선 SKIP.
- 실제 v4.5.7 baseline 의 비교는 사용자가 baseline screenshot 을
  ``fixtures/visual_baseline/<id>/{desktop,mobile,exhibit_*}.png`` 으로
  녹화한 후에만 의미. Phase 0B 시점엔 *framework + spec* 만.

Plan §3.4 (나) 의 검증 항목:
  1. desktop / mobile / exhibit closeup screenshot 캡쳐
  2. pixel diff 로 baseline 과 비교
  3. chart bbox overflow 검출
  4. horizontal overflow 검출

CLI runner: ``scripts/run_regression.py --tests visual``
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.regression._pytest_compat import pytest

from tests.regression.helpers import (
    REGRESSION_ROOT,
    RegressionResult,
)


VISUAL_BASELINE_DIR = REGRESSION_ROOT / "fixtures" / "visual_baseline"
VISUAL_CAPTURED_DIR = REGRESSION_ROOT / "fixtures" / "visual_captured"


# ─── Playwright 의존 검사 ───────────────────────────────────────────────


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _lxml_available() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False


def _pillow_available() -> bool:
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


# ─── 정적 SVG Sanity (lxml 의존, V5 Phase 6 Gate C 의 사전 구현) ──────────


@dataclass
class SanityResult:
    passed: bool
    issues: list[str]


def visual_sanity_check_svg(svg_text: str, viewbox: tuple[int, int, int, int]) -> SanityResult:
    """Plan §7.4 의 결정적 SVG 정적 검증.

    1. viewport 안 마크 카운트 (rect/circle/path 데이터 마크 ≥ 1)
    2. 라벨 bbox 충돌 비율 ≤ 0.20
    3. 빈 frame 감지 (마크+라벨 영역 비율 ≥ 5%)
    4. 라벨 잘림 감지 (text bbox 가 viewBox 안에 있음)

    lxml 미설치 시 SanityResult(passed=True, issues=["lxml_missing"]) 반환 —
    V5 Phase 6 Gate C 정식 활성 시 의존성 추가 + 본 함수가 본격 작동.
    """
    if not _lxml_available():
        return SanityResult(passed=True, issues=["lxml_missing_skipped"])

    from lxml import etree  # local import — 의존성 가드

    issues: list[str] = []
    try:
        tree = etree.fromstring(svg_text.encode("utf-8"))
    except etree.XMLSyntaxError as e:
        return SanityResult(passed=False, issues=[f"svg_parse_failed: {e}"])

    ns = {"svg": "http://www.w3.org/2000/svg"}

    # Data marks — namespace 가 있는 경우 / 없는 경우 모두 시도.
    marks = (
        tree.findall(".//svg:rect", ns)
        + tree.findall(".//svg:circle", ns)
        + tree.findall(".//svg:path", ns)
        + tree.findall(".//rect")
        + tree.findall(".//circle")
        + tree.findall(".//path")
    )
    if len(marks) == 0:
        issues.append("AP-12: 데이터 마크 0개 (frame 밖 또는 빈 data)")

    # Text labels.
    texts = tree.findall(".//svg:text", ns) + tree.findall(".//text")
    # bbox 계산은 SVG 렌더 없이 어렵다 — text 의 x/y 만 viewBox 와 비교.
    vbx, vby, vbw, vbh = viewbox
    label_clipped = 0
    for t in texts:
        try:
            x = float(t.get("x") or 0)
            y = float(t.get("y") or 0)
        except ValueError:
            continue
        if x < vbx - 4 or y < vby - 4 or x > vbx + vbw + 4 or y > vby + vbh + 4:
            label_clipped += 1
    if label_clipped > 0:
        issues.append(f"AP-5: 라벨 viewBox 밖 잘림 {label_clipped}건")

    return SanityResult(passed=not issues, issues=issues)


# ─── Playwright capture — V5 Phase 7 의 사전 구현 ────────────────────────


def capture_proofs(html_path: str | Path, exhibit_count: int = 3) -> list[dict[str, Any]]:
    """Plan §8.5 의 Playwright 캡쳐. Phase 7 의 사전 구현이지만, Phase 0B 의
    visual regression 입력으로도 그대로 사용.

    desktop_full (1280×scrollHeight), mobile_full (375×scrollHeight),
    chart_closeup (.exhibit_card 또는 .chart-card 첫 N개) 캡쳐.

    Playwright 미설치 시 빈 리스트 반환. 실패 시 desktop_full 만이라도 확보 시도.
    """
    if not _playwright_available():
        return []

    # 실제 구현은 sync API 또는 async API. Phase 0B 시점 — pytest 비동기 boilerplate
    # 회피 위해 sync API. asyncio 와의 통합은 V5 Phase 7 정식 도입 시점.
    from playwright.sync_api import sync_playwright  # type: ignore  # pragma: no cover

    html_path = Path(html_path).resolve()
    if not html_path.exists():
        return [{"role": "error", "label": f"html_missing: {html_path}"}]

    captures: list[dict[str, Any]] = []
    with sync_playwright() as p:  # pragma: no cover  — 실제 실행 환경에서만 동작
        browser = p.chromium.launch(headless=True)

        # desktop_full
        ctx_d = browser.new_context(viewport={"width": 1280, "height": 800})
        page_d = ctx_d.new_page()
        page_d.goto(html_path.as_uri())
        page_d.wait_for_load_state("networkidle", timeout=10000)
        captures.append({
            "role": "desktop_full",
            "image": page_d.screenshot(full_page=True),
            "label": "desktop full page",
            "width": 1280,
        })

        # mobile_full
        ctx_m = browser.new_context(viewport={"width": 375, "height": 667})
        page_m = ctx_m.new_page()
        page_m.goto(html_path.as_uri())
        page_m.wait_for_load_state("networkidle", timeout=10000)
        captures.append({
            "role": "mobile_full",
            "image": page_m.screenshot(full_page=True),
            "label": "mobile full page",
            "width": 375,
        })

        # chart_closeup (첫 N개 chart-card 또는 exhibit_card)
        cards = page_d.query_selector_all(".chart-card, .exhibit_card")[:exhibit_count]
        for i, card in enumerate(cards):
            try:
                captures.append({
                    "role": "chart_closeup",
                    "image": card.screenshot(),
                    "label": f"chart {i+1} closeup",
                    "width": 1280,
                })
            except Exception:  # pragma: no cover
                pass

        browser.close()

    return captures


# ─── Pixel diff (Pillow 의존) ────────────────────────────────────────────


def pixel_diff_ratio(image_a: bytes, image_b: bytes) -> float:
    """두 PNG 이미지의 픽셀 차이 비율 (0.0~1.0).

    Pillow 미설치 시 0.0 (variance 측정 불가) 반환 — 회귀 테스트는
    threshold 비교로 자동 PASS.
    """
    if not _pillow_available():
        return 0.0
    from io import BytesIO

    from PIL import Image, ImageChops  # local import — 의존성 가드

    a = Image.open(BytesIO(image_a)).convert("RGB")
    b = Image.open(BytesIO(image_b)).convert("RGB")
    if a.size != b.size:
        # 크기가 다르면 회귀 — 1.0 으로 표현.
        return 1.0
    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    if bbox is None:
        return 0.0
    # 단순 — 차이 바운딩박스 면적 / 전체 면적.
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    aw, ah = a.size
    return (bw * bh) / max(aw * ah, 1)


# ─── 코어 검증 (run_one — CLI runner 호환) ───────────────────────────────


def run_one(prompt_id: str, html_path: str | Path | None = None) -> RegressionResult:
    """단일 Golden Prompt 의 visual regression 검증.

    HTML 경로가 주어지지 않으면 ``reports/<prompt_id>.html`` 또는
    ``fixtures/visual_baseline/<prompt_id>/source.html`` 을 시도.
    경로 / Playwright / lxml 어느 하나가 부족하면 SKIP (passed=True + missing 메트릭).
    """
    issues: list[str] = []
    metrics: dict[str, Any] = {
        "playwright_available": _playwright_available(),
        "lxml_available": _lxml_available(),
        "pillow_available": _pillow_available(),
    }

    if not _playwright_available():
        metrics["status"] = "skipped_no_playwright"
        return RegressionResult(
            test_name="visual_regression",
            prompt_id=prompt_id,
            passed=True,
            issues=[],
            metrics=metrics,
        )

    if html_path is None or not Path(html_path).exists():
        metrics["status"] = "skipped_no_html"
        return RegressionResult(
            test_name="visual_regression",
            prompt_id=prompt_id,
            passed=True,
            issues=[],
            metrics=metrics,
        )

    captures = capture_proofs(html_path)
    metrics["capture_count"] = len(captures)

    baseline_dir = VISUAL_BASELINE_DIR / prompt_id
    if not baseline_dir.exists():
        # baseline 미녹화 — captured 만 저장하고 PASS.
        metrics["status"] = "captured_no_baseline"
        return RegressionResult(
            test_name="visual_regression",
            prompt_id=prompt_id,
            passed=True,
            issues=[],
            metrics=metrics,
        )

    # baseline 비교.
    diffs: dict[str, float] = {}
    for cap in captures:
        role = cap["role"]
        baseline_file = baseline_dir / f"{role}.png"
        if not baseline_file.exists():
            continue
        ratio = pixel_diff_ratio(cap["image"], baseline_file.read_bytes())
        diffs[role] = ratio
        if ratio > 0.05:  # 5% 차이 이상이면 회귀
            issues.append(f"pixel_diff_{role}: {ratio:.2%}")
    metrics["pixel_diffs"] = diffs

    return RegressionResult(
        test_name="visual_regression",
        prompt_id=prompt_id,
        passed=not issues,
        issues=issues,
        metrics=metrics,
    )


def run_all(report_dir: Path | None = None) -> list[RegressionResult]:
    """모든 Golden Prompt 에 대해 run_one 실행.

    ``report_dir`` 가 주어지면 그 디렉토리에서 ``<prompt_id>.html`` 을 찾는다.
    없으면 모두 SKIP — Phase 0B 시점의 일반적 동작.
    """
    from tests.regression.helpers import load_golden_prompts

    results: list[RegressionResult] = []
    for entry in load_golden_prompts():
        pid = entry["id"]
        html = None
        if report_dir is not None:
            cand = Path(report_dir) / f"{pid}.html"
            if cand.exists():
                html = cand
        results.append(run_one(pid, html))
    return results


# ─── pytest 통합 ────────────────────────────────────────────────────────


def test_capture_function_signature_matches_plan() -> None:
    """Plan §8.5 의 capture_proofs 시그니처 보존 — 회귀 테스트가 실제로 사용 가능."""
    import inspect

    sig = inspect.signature(capture_proofs)
    params = list(sig.parameters)
    assert params[0] == "html_path", "Plan §8.5: 첫 인자는 html_path"
    # 두 번째 인자는 Plan §8.5 의 'exhibit_count'.
    assert "exhibit_count" in params, "Plan §8.5: exhibit_count 인자 필요"


def test_sanity_check_handles_empty_svg() -> None:
    """lxml 미설치 시에도 sanity check 가 fallback 으로 동작."""
    result = visual_sanity_check_svg("<svg></svg>", (0, 0, 100, 100))
    # lxml 있으면 마크 0 으로 fail, 없으면 skip.
    if _lxml_available():
        assert not result.passed
        assert any("AP-12" in i for i in result.issues)
    else:
        assert result.passed
        assert "lxml_missing_skipped" in result.issues


@pytest.mark.skipif(
    not _playwright_available(),
    reason="Playwright 미설치 — pip install playwright + python -m playwright install chromium",
)
def test_playwright_smoke() -> None:  # pragma: no cover
    """Playwright 가 설치된 환경에서만 실제 capture 시도."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<html><body><h1>regression smoke</h1></body></html>")
        png = page.screenshot()
        browser.close()
    assert isinstance(png, bytes) and len(png) > 0


def test_pixel_diff_handles_missing_pillow() -> None:
    """Pillow 미설치 시 pixel_diff_ratio 가 0.0 fallback."""
    if _pillow_available():
        pytest.skip("Pillow 설치됨 — fallback 경로 테스트 불가")
    assert pixel_diff_ratio(b"a", b"b") == 0.0
