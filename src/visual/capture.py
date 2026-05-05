"""V5 Phase 7-pre — Playwright capture pipeline (Plan §16.5).

Phase 7 DeskEditor 호출 *전* 단계. ReportSynthesizer 가 HTML 을 디스크에
쓴 후, Playwright 가 desktop / mobile / chart_closeup 캡쳐를 만들어
DeskEditor 의 입력 (PublishManifest.screenshots) 으로 넘긴다.

[Plan §16.5 캡쳐 정책]
- 1장: desktop_full   1280×ScrollHeight  — 페이지 전체 풀 캡쳐
- 1장: mobile_full     375×ScrollHeight  — mobile breakpoint
- 1~3장: chart_closeup  각 Exhibit 의 .chart-card / .exhibit_card  close-up
- 캡쳐 timeout 10초. 실패 시 desktop_full 만이라도 확보.
- 캡쳐 자체 실패 시 Visual rubric 검사 skip + telemetry 기록.

[의존성]
    playwright>=1.40 (optional). 미설치 시 본 모듈은 *empty list* 반환.
    설치 명령: pip install playwright && python -m playwright install chromium

Public API:
    from src.visual.capture import (
        ScreenshotCapture,
        capture_proofs,
        is_playwright_available,
    )
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


CaptureRole = Literal["desktop_full", "mobile_full", "chart_closeup", "map_closeup"]


@dataclass
class ScreenshotCapture:
    """Plan §16.2 의 ScreenshotCapture — DeskEditor 가 입력으로 받는 1장.

    Note: Pydantic 모델 (src/state/models.py:ScreenshotCapture) 도 별도 정의됨.
    본 dataclass 는 capture.py 내부 사용 + 변환 보조.
    """

    role: CaptureRole
    image_b64: str
    label: str = ""
    width: int = 0
    height: int = 0


# ─── 의존성 검사 ───────────────────────────────────────────────────────


def is_playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


# ─── 캡쳐 함수 ─────────────────────────────────────────────────────────


def capture_proofs(
    html_path: str | Path,
    *,
    exhibit_count: int = 3,
    timeout_ms: int = 10000,
) -> list[ScreenshotCapture]:
    """Plan §16.5 — Playwright 로 desktop / mobile / chart_closeup 캡쳐.

    Args:
        html_path: 렌더된 HTML 파일의 로컬 경로.
        exhibit_count: chart_closeup 캡쳐 개수 상한 (Plan §16.5 — 첫 3개만).
        timeout_ms: 페이지 로드 timeout.

    Returns:
        list[ScreenshotCapture]. Playwright 미설치 또는 페이지 로드 실패 시
        빈 list (graceful degrade — DeskEditor 가 Visual rubric skip).
    """
    if not is_playwright_available():
        logger.info(
            "[capture] Playwright 미설치 — 빈 list 반환 (Visual rubric skip). "
            "Install: pip install playwright && python -m playwright install chromium"
        )
        return []

    html_path = Path(html_path).resolve()
    if not html_path.exists():
        logger.warning("[capture] HTML 파일 미존재: %s", html_path)
        return []

    try:
        return _capture_with_playwright(html_path, exhibit_count, timeout_ms)
    except Exception as e:  # pragma: no cover  — 실 환경에서만 발생
        logger.warning(
            "[capture] Playwright capture 실패 (graceful skip): %s", e
        )
        return []


def _capture_with_playwright(
    html_path: Path,
    exhibit_count: int,
    timeout_ms: int,
) -> list[ScreenshotCapture]:
    """실제 Playwright 호출. is_playwright_available() True 일 때만 호출."""
    from playwright.sync_api import sync_playwright   # type: ignore  # pragma: no cover

    captures: list[ScreenshotCapture] = []

    with sync_playwright() as p:  # pragma: no cover  — 실제 실행 환경에서만
        browser = p.chromium.launch(headless=True)

        # 1. desktop_full — 1280×scrollHeight 풀 캡쳐.
        try:
            ctx_d = browser.new_context(viewport={"width": 1280, "height": 800})
            page_d = ctx_d.new_page()
            page_d.goto(html_path.as_uri())
            page_d.wait_for_load_state("networkidle", timeout=timeout_ms)
            png = page_d.screenshot(full_page=True)
            captures.append(ScreenshotCapture(
                role="desktop_full",
                image_b64=base64.b64encode(png).decode("ascii"),
                label="desktop full page",
                width=1280,
                height=800,
            ))
        except Exception as e:
            logger.warning("[capture] desktop_full 실패: %s", e)

        # 2. mobile_full — 375×scrollHeight.
        try:
            ctx_m = browser.new_context(viewport={"width": 375, "height": 667})
            page_m = ctx_m.new_page()
            page_m.goto(html_path.as_uri())
            page_m.wait_for_load_state("networkidle", timeout=timeout_ms)
            png = page_m.screenshot(full_page=True)
            captures.append(ScreenshotCapture(
                role="mobile_full",
                image_b64=base64.b64encode(png).decode("ascii"),
                label="mobile full page",
                width=375,
                height=667,
            ))
        except Exception as e:
            logger.warning("[capture] mobile_full 실패: %s", e)

        # 3. chart_closeup — 첫 N개 chart-card scroll-into-view + close-up.
        if exhibit_count > 0 and captures:
            try:
                page_cc = browser.new_context(
                    viewport={"width": 1280, "height": 800},
                ).new_page()
                page_cc.goto(html_path.as_uri())
                page_cc.wait_for_load_state("networkidle", timeout=timeout_ms)
                cards = page_cc.query_selector_all(
                    ".chart-card, .exhibit_card, .freeform-chart-wrap"
                )[:exhibit_count]
                for i, card in enumerate(cards):
                    try:
                        card.scroll_into_view_if_needed(timeout=2000)
                        png = card.screenshot()
                        captures.append(ScreenshotCapture(
                            role="chart_closeup",
                            image_b64=base64.b64encode(png).decode("ascii"),
                            label=f"chart {i+1} closeup",
                            width=1280,
                            height=400,
                        ))
                    except Exception as e:
                        logger.warning(
                            "[capture] chart_closeup %d 실패: %s", i, e
                        )
            except Exception as e:
                logger.warning("[capture] chart_closeup setup 실패: %s", e)

        browser.close()

    return captures


# ─── 디스크에 저장 (선택) ───────────────────────────────────────────


def save_captures_to_disk(
    captures: list[ScreenshotCapture],
    out_dir: str | Path,
) -> list[Path]:
    """캡쳐를 디스크에 저장 (DeskEditor 디버깅 또는 visual baseline 용).

    Returns:
        저장된 파일 경로 list.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, cap in enumerate(captures):
        png_bytes = base64.b64decode(cap.image_b64)
        path = out_dir / f"{i:02d}_{cap.role}.png"
        path.write_bytes(png_bytes)
        paths.append(path)
    return paths
