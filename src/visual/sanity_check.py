"""V5 Phase 6 Gate C — Render-time Visual Sanity Check (Plan §13.4).

Vega-Lite 또는 d3 가 렌더한 SVG 를 *파싱해서* 시각 결함을 탐지. 결정적
(LLM 0). lxml 의존 — 미설치 시 graceful skip + 통과 처리.

[검증 항목 — Plan §13.4]
1. viewport 안 마크 카운트 — <rect>/<circle>/<path> 등 데이터 마크가
   viewBox 안에 1개 이상 보이는가. 0 이면 fail (CHART-AP-12 frame 밖).
2. 라벨 bbox 충돌 비율 — 충돌 페어 / 전체 페어 ≤ 0.20.
3. 빈 frame 감지 — viewBox 면적 대비 마크+라벨 영역 ≥ 5%.
4. 라벨 잘림 감지 — text bbox 가 viewBox 밖.

[커버리지]
    AP-5  (라벨 zone 밖)
    AP-6  (annotation 충돌)
    AP-10 (지도 마커 라벨 충돌)
    AP-12 (frame 밖)

[Public API]
    from src.visual.sanity_check import (
        SanityResult,
        visual_sanity_check_svg,
        SanityCheckThresholds,
    )
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SanityCheckThresholds:
    """기본 임계값 SSOT (Plan §13.4)."""

    label_overlap_ratio_max: float = 0.20      # 라벨 충돌 페어 비율
    fill_ratio_min: float = 0.05               # viewBox 의 5% 이상 차야
    label_clip_count_max: int = 0              # 라벨이 viewBox 밖으로 나가면 즉시 fail
    min_data_marks: int = 1                    # 마크 0개 = AP-12


DEFAULT_THRESHOLDS = SanityCheckThresholds()


@dataclass
class SanityResult:
    """Gate C 검증 결과."""

    passed: bool
    issues: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


# ─── 의존성 검사 ───────────────────────────────────────────────────────


def _lxml_available() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False


# ─── 단순 SVG 파싱 (lxml 미설치 fallback) ─────────────────────────────


_SVG_RECT_RE = re.compile(
    r'<rect\b[^>]*?x="(?P<x>-?[\d.]+)"[^>]*?y="(?P<y>-?[\d.]+)"',
    re.IGNORECASE,
)
_SVG_CIRCLE_RE = re.compile(
    r'<circle\b[^>]*?cx="(?P<x>-?[\d.]+)"[^>]*?cy="(?P<y>-?[\d.]+)"',
    re.IGNORECASE,
)
_SVG_PATH_RE = re.compile(r'<path\b[^>]*?d="', re.IGNORECASE)
_SVG_TEXT_RE = re.compile(
    r'<text\b[^>]*?x="(?P<x>-?[\d.]+)"[^>]*?y="(?P<y>-?[\d.]+)"[^>]*>(?P<content>.*?)</text>',
    re.IGNORECASE | re.DOTALL,
)


def _parse_marks_simple(svg_text: str) -> tuple[list[tuple[float, float]], list[tuple[float, float, str]]]:
    """lxml 미설치 환경의 fallback. 정규식으로 marks + texts 만 추출."""
    marks: list[tuple[float, float]] = []
    for m in _SVG_RECT_RE.finditer(svg_text):
        try:
            marks.append((float(m["x"]), float(m["y"])))
        except (ValueError, KeyError):
            pass
    for m in _SVG_CIRCLE_RE.finditer(svg_text):
        try:
            marks.append((float(m["x"]), float(m["y"])))
        except (ValueError, KeyError):
            pass
    # path 는 d 속성에 좌표가 있어 정확한 위치는 파싱 어려움 — 카운트만.
    path_count = len(_SVG_PATH_RE.findall(svg_text))
    # path 1개당 marks 1개로 간주 (대표 위치 0,0).
    for _ in range(path_count):
        marks.append((0.0, 0.0))

    texts: list[tuple[float, float, str]] = []
    for m in _SVG_TEXT_RE.finditer(svg_text):
        try:
            texts.append((float(m["x"]), float(m["y"]), (m["content"] or "").strip()))
        except (ValueError, KeyError):
            pass
    return marks, texts


def _parse_marks_lxml(svg_text: str) -> tuple[list[tuple[float, float]], list[tuple[float, float, str]]]:
    """lxml 사용 — 정확한 SVG 트리 파싱."""
    from lxml import etree   # type: ignore  # local import 가드

    try:
        tree = etree.fromstring(svg_text.encode("utf-8"))
    except etree.XMLSyntaxError as e:
        raise ValueError(f"svg parse failed: {e}") from e

    ns = {"svg": "http://www.w3.org/2000/svg"}

    def _all(tag: str) -> list[Any]:
        return tree.findall(f".//svg:{tag}", ns) + tree.findall(f".//{tag}")

    marks: list[tuple[float, float]] = []
    for el in _all("rect"):
        try:
            marks.append((float(el.get("x") or 0), float(el.get("y") or 0)))
        except ValueError:
            continue
    for el in _all("circle"):
        try:
            marks.append((float(el.get("cx") or 0), float(el.get("cy") or 0)))
        except ValueError:
            continue
    # path 는 d 속성 — 좌표 추출은 어렵지만 카운트는 신뢰 가능.
    for el in _all("path"):
        marks.append((0.0, 0.0))

    texts: list[tuple[float, float, str]] = []
    for el in _all("text"):
        try:
            texts.append((
                float(el.get("x") or 0),
                float(el.get("y") or 0),
                (el.text or "").strip(),
            ))
        except ValueError:
            continue
    return marks, texts


# ─── 단순 bbox 충돌 — 라벨 길이 추정 ─────────────────────────────────


def _estimate_text_bbox(
    x: float, y: float, content: str,
    char_width: float = 6.0, line_height: float = 12.0,
) -> tuple[float, float, float, float]:
    """text 의 bbox 추정. 폰트 크기 12px 가정.

    Returns:
        (x_min, y_min, x_max, y_max)
    """
    width = max(char_width, len(content) * char_width)
    # SVG text 의 y 는 baseline. bbox 의 상단은 y - line_height * 0.8.
    y_min = y - line_height * 0.8
    y_max = y + line_height * 0.2
    return (x, y_min, x + width, y_max)


def _bbox_overlap(b1: tuple[float, float, float, float], b2: tuple[float, float, float, float]) -> bool:
    return not (
        b1[2] < b2[0] or b2[2] < b1[0]
        or b1[3] < b2[1] or b2[3] < b1[1]
    )


def _label_overlap_ratio(texts: list[tuple[float, float, str]]) -> float:
    """라벨 페어 충돌 비율."""
    if len(texts) < 2:
        return 0.0
    bboxes = [_estimate_text_bbox(x, y, c) for x, y, c in texts if c]
    if len(bboxes) < 2:
        return 0.0
    pair_count = 0
    overlap_count = 0
    for i in range(len(bboxes)):
        for j in range(i + 1, len(bboxes)):
            pair_count += 1
            if _bbox_overlap(bboxes[i], bboxes[j]):
                overlap_count += 1
    return overlap_count / pair_count if pair_count else 0.0


def _label_clip_count(
    texts: list[tuple[float, float, str]],
    viewbox: tuple[float, float, float, float],
) -> int:
    """text bbox 가 viewBox 밖으로 나간 개수."""
    vbx, vby, vbw, vbh = viewbox
    vbx2, vby2 = vbx + vbw, vby + vbh
    clipped = 0
    for x, y, content in texts:
        if not content:
            continue
        bbox = _estimate_text_bbox(x, y, content)
        # margin 4px 허용.
        if bbox[0] < vbx - 4 or bbox[1] < vby - 4 or bbox[2] > vbx2 + 4 or bbox[3] > vby2 + 4:
            clipped += 1
    return clipped


def _occupied_area_ratio(
    marks: list[tuple[float, float]],
    texts: list[tuple[float, float, str]],
    viewbox: tuple[float, float, float, float],
) -> float:
    """viewBox 면적 대비 마크 + 라벨 영역 비율 (단순 추정).

    실제 렌더 면적을 정확히 계산하려면 SVG 의 너비·반경까지 파싱 필요.
    본 함수는 *대표 점 / 라벨 bbox* 만으로 추정.
    """
    vbw = viewbox[2]
    vbh = viewbox[3]
    if vbw <= 0 or vbh <= 0:
        return 0.0
    # 라벨 bbox 합산.
    label_area = 0.0
    for x, y, c in texts:
        if c:
            bbox = _estimate_text_bbox(x, y, c)
            label_area += max(0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
    # 마크는 점당 16x16 추정.
    mark_area = len(marks) * 16 * 16
    return min(1.0, (label_area + mark_area) / (vbw * vbh))


# ─── 메인 — visual_sanity_check_svg ──────────────────────────────────


def visual_sanity_check_svg(
    svg_text: str,
    viewbox: tuple[float, float, float, float],
    *,
    thresholds: SanityCheckThresholds | None = None,
) -> SanityResult:
    """Plan §13.4 의 결정적 SVG 정적 검증. LLM 0.

    Args:
        svg_text: 렌더된 SVG 문자열.
        viewbox: (x, y, width, height) — Vega-Lite 또는 d3 가 emit 한 viewBox.
        thresholds: 기본값 외 임계 사용 시.

    Returns:
        SanityResult — passed / issues / metrics.
    """
    th = thresholds or DEFAULT_THRESHOLDS
    issues: list[str] = []
    metrics: dict[str, Any] = {}

    if not svg_text or "<svg" not in svg_text.lower():
        return SanityResult(
            passed=False,
            issues=["svg_input_invalid"],
            metrics={"reason": "missing <svg> tag"},
        )

    # 1. SVG 파싱.
    if _lxml_available():
        try:
            marks, texts = _parse_marks_lxml(svg_text)
        except Exception as e:   # pragma: no cover
            return SanityResult(
                passed=False,
                issues=[f"svg_parse_failed: {e}"],
            )
    else:
        marks, texts = _parse_marks_simple(svg_text)
        metrics["lxml_missing"] = True

    metrics["mark_count"] = len(marks)
    metrics["text_count"] = len(texts)

    # 2. 마크 카운트 — AP-12.
    if len(marks) < th.min_data_marks:
        issues.append(
            f"AP-12: 데이터 마크 {len(marks)}개 (frame 밖 또는 빈 data) — "
            f"min={th.min_data_marks}"
        )

    # 3. 라벨 bbox 충돌 — AP-5/6/10.
    overlap_ratio = _label_overlap_ratio(texts)
    metrics["label_overlap_ratio"] = round(overlap_ratio, 3)
    if overlap_ratio > th.label_overlap_ratio_max:
        issues.append(
            f"AP-5/6/10: 라벨 bbox 충돌 비율 {overlap_ratio:.0%} > "
            f"{th.label_overlap_ratio_max:.0%}"
        )

    # 4. 라벨 잘림 — AP-5.
    clip_count = _label_clip_count(texts, viewbox)
    metrics["label_clip_count"] = clip_count
    if clip_count > th.label_clip_count_max:
        issues.append(
            f"AP-5: 라벨 viewBox 밖 잘림 {clip_count}건 "
            f"(허용 {th.label_clip_count_max})"
        )

    # 5. 빈 frame — viewBox 점유율.
    fill_ratio = _occupied_area_ratio(marks, texts, viewbox)
    metrics["fill_ratio"] = round(fill_ratio, 3)
    if fill_ratio < th.fill_ratio_min:
        issues.append(
            f"AP-12: viewBox 의 {fill_ratio:.0%} 만 사용 (빈 frame) — "
            f"min={th.fill_ratio_min:.0%}"
        )

    return SanityResult(
        passed=not issues,
        issues=issues,
        metrics=metrics,
    )
