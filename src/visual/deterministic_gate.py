"""V5 Phase 7A — Deterministic Publish Gate (Plan §15).

DeskEditor (LLM Vision, Phase 7) 호출 *전* 결정적 (rule-based) 검사. 기계적으로
잡을 수 있는 결함은 LLM 비용을 쓰지 않고 차단한다.

[위치 — Plan §15.3]
    Renderer → reports/dev/<id>.html
        ↓
    [Phase 7A] Deterministic Publish Gate    ← 본 모듈
        ↓ pass / fail (hard / soft)
    [Phase 7-pre] Playwright Capture
        ↓
    [Phase 7] LLM DeskEditor

[Plan §15.4 — Hard Fail (11종, 즉시 KILL)]
    1. html_render_failed         — HTML 파일이 존재하지 않음
    2. html_unparseable           — HTML 파싱 실패 (xml/html lib)
    3. required_section_missing   — AnalysisBrief.must_have_sections 누락
    4. exhibit_ref_broken         — [[ex:N]] 가 존재하지 않는 exhibit 참조
    5. chart_without_source       — exhibit.source_ids 비어있음 (AP-V5-26)
    6. chart_container_empty      — HTML 안의 chart-card 가 비어있음
    7. report_too_short           — total_chars < mode_lower_bound
    8. closing_missing            — composed_report.closing 비어있음
    9. asset_404                  — 정적 자산 (charts.js / maps.js 등) 누락
    10. mobile_horizontal_overflow — 모바일 viewport (375px) 가로 overflow > 24px
    11. playwright_timeout        — Playwright capture 가 timeout

[Plan §15.5 — Soft Fail (5종, DeskEditor 에 신호)]
    1. asymmetry_gini            — 섹션 분량 지니 계수 > 0.6
    2. chart_count_exceeded      — mode 상한 초과 (fast 2 / std 4 / deep 5)
    3. heading_pattern_repetitive — 모든 heading 이 비슷한 길이·구조
    4. watch_signal_all_ambiguous — direction 가 모두 ambiguous
    5. stale_source_ratio_high   — 3개월+ 된 출처가 70%+

[AP-V5-29 — Plan §23]
"LLM Desk Editor 호출은 *반드시* Phase 7A 통과 후 발생. Hard fail 시 LLM
호출 발생 0이 강제. soft fail 은 DeskEditor system prompt 에 명시적으로 전달."

[Public API]
    from src.visual.deterministic_gate import (
        DeterministicGateResult,
        run_deterministic_gate,
        HARD_FAIL_RULES,
        SOFT_FAIL_RULES,
        MODE_LOWER_BOUND,
        ChartCountLimits,
    )
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ─── Threshold SSOT ────────────────────────────────────────────────────


# Plan §6.3 의 mode 별 분량 가이드 (Phase 5 와 동일).
MODE_LOWER_BOUND: dict[str, int] = {
    "fast": 1500,
    "standard": 3500,
    "deep": 6000,
}


# Plan §13.8 + AP-V5-9 — mode 별 차트 상한.
class ChartCountLimits:
    fast = 2
    standard = 4
    deep = 5


SOFT_GINI_THRESHOLD = 0.60                # 섹션 분량 비대칭 임계
SOFT_STALE_RATIO_THRESHOLD = 0.70         # 3개월+ 된 출처 비율
MOBILE_OVERFLOW_THRESHOLD_PX = 24         # 모바일 가로 overflow 허용


# ─── 결과 자료구조 ────────────────────────────────────────────────────


@dataclass
class DeterministicGateResult:
    """Plan §15.4/§15.5 의 통합 결과.

    [정책]
        passed=True          : Hard fail 0 → Phase 7 LLM Desk 호출 가능.
        decision="kill"      : Hard fail ≥1 → KILL (LLM 호출 X).
        decision="soft_fail" : Hard 0 + Soft ≥1 → DeskEditor 에 hold 신호로 전달.
        decision="publish"   : 모두 통과.
    """

    passed: bool
    decision: Literal["publish", "soft_fail", "kill"]
    hard_failures: list[str] = field(default_factory=list)
    soft_failures: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


# ─── HTML 검사 헬퍼 ───────────────────────────────────────────────────


def _is_parseable_html(html_text: str) -> bool:
    """HTML 의 minimal 파싱 가능성. 외부 lib 미설치 시 단순 문자열 검증."""
    if not html_text or not html_text.strip():
        return False
    s = html_text.lstrip()
    return s.startswith("<!DOCTYPE") or s.startswith("<html") or s.startswith("<HTML")


_EXHIBIT_REF_RE = re.compile(r"\[\[exr?:\s*(\d+)\s*\]\]")
_EXHIBIT_RANGE_RE = re.compile(r"\[\[exs:\s*(\d+)\s*[-~]\s*(\d+)\s*\]\]")


def _collect_exhibit_refs(prose: str) -> set[int]:
    """prose 안의 [[ex:N]] / [[exr:N]] / [[exs:N-M]] 참조 수집."""
    refs: set[int] = set()
    for m in _EXHIBIT_REF_RE.finditer(prose):
        try:
            refs.add(int(m.group(1)))
        except ValueError:
            continue
    for m in _EXHIBIT_RANGE_RE.finditer(prose):
        try:
            a, b = int(m.group(1)), int(m.group(2))
            for i in range(min(a, b), max(a, b) + 1):
                refs.add(i)
        except ValueError:
            continue
    return refs


_CHART_CARD_RE = re.compile(
    r'<(?:div|figure)[^>]*class="[^"]*chart-card[^"]*"[^>]*>(.*?)</(?:div|figure)>',
    re.IGNORECASE | re.DOTALL,
)


def _has_empty_chart_containers(html_text: str) -> bool:
    """HTML 안의 chart-card 가 *내부 컨텐츠 0* 인지.

    SVG / inline payload / 자식 element 가 하나도 없으면 empty.
    """
    if not html_text:
        return False
    for m in _CHART_CARD_RE.finditer(html_text):
        content = (m.group(1) or "").strip()
        if not content:
            return True
        # SVG 태그 / script payload 둘 다 없으면 empty.
        if not re.search(r"<svg|<script", content, re.IGNORECASE):
            return True
    return False


_ASSET_REF_RE = re.compile(
    r'<(?:script|link)[^>]*?(?:src|href)="([^"]+\.(?:js|css|json))"',
    re.IGNORECASE,
)


def _has_404_assets(html_text: str, html_dir: Path | None) -> tuple[bool, list[str]]:
    """HTML 이 참조하는 *로컬* 정적 자산이 디스크에 존재하는지.

    외부 URL (https://) 은 검사 X. 상대 경로만 디스크 verify.
    Returns (has_404, missing_paths).
    """
    if not html_text or html_dir is None:
        return False, []
    missing: list[str] = []
    for m in _ASSET_REF_RE.finditer(html_text):
        url = m.group(1)
        if url.startswith(("http://", "https://", "//", "data:")):
            continue
        # 상대 경로 — html_dir 기준.
        full = (html_dir / url).resolve()
        if not full.exists():
            missing.append(url)
    return bool(missing), missing


# ─── 분량 검사 ─────────────────────────────────────────────────────────


def _total_prose_chars(composed: dict[str, Any]) -> int:
    sections = composed.get("sections") or []
    return sum(len(((s or {}).get("prose") or "")) for s in sections)


def _gini_coefficient(values: list[float]) -> float:
    """섹션 분량의 지니 계수 (0=균등, 1=극단 집중)."""
    if not values or all(v == 0 for v in values):
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cum = 0.0
    for i, v in enumerate(sorted_vals, start=1):
        cum += i * v
    total = sum(sorted_vals)
    return (2.0 * cum) / (n * total) - (n + 1) / n if total > 0 else 0.0


def _heading_repetitive(composed: dict[str, Any]) -> bool:
    """모든 heading 이 길이 ±2자 안 + 동일 어두 패턴 → 반복."""
    sections = composed.get("sections") or []
    headings = [(s or {}).get("heading", "") for s in sections]
    headings = [h for h in headings if h]
    if len(headings) < 3:
        return False
    lengths = [len(h) for h in headings]
    if max(lengths) - min(lengths) > 4:
        return False
    # 어두 (첫 2자) 가 모두 같으면 반복.
    prefixes = [h[:2] for h in headings]
    if len(set(prefixes)) == 1:
        return True
    return False


def _stale_source_ratio(composed: dict[str, Any], threshold_days: int = 90) -> float:
    """sources 의 timestamp 가 N일 이상 오래된 비율."""
    from datetime import datetime, timezone

    sources = composed.get("sources") or []
    if not sources:
        return 0.0
    if isinstance(sources, list) and sources and isinstance(sources[0], str):
        # v4.5.7 의 sources 는 URL list — timestamp 정보 없음.
        return 0.0
    now = datetime.now(timezone.utc)
    stale = 0
    counted = 0
    for src in sources:
        if not isinstance(src, dict):
            continue
        ts = src.get("timestamp") or src.get("published_at")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = (now - dt).days
            counted += 1
            if age > threshold_days:
                stale += 1
        except ValueError:
            continue
    if counted == 0:
        return 0.0
    return stale / counted


# ─── 11종 Hard Fail 함수 (Plan §15.4) ────────────────────────────────


def _check_html_render_failed(rendered_html_path: str | Path | None) -> bool:
    if not rendered_html_path:
        return True
    return not Path(rendered_html_path).exists()


def _check_html_unparseable(html_text: str) -> bool:
    return not _is_parseable_html(html_text)


def _check_required_section_missing(
    composed: dict[str, Any],
    must_have_sections: list[str] | None,
) -> bool:
    """AnalysisBrief.must_have_sections 가 보고서 sections 에 모두 있는지.

    matching 은 *부분 일치* — must_have='situation' 이고 section.heading 에
    'situation' 이 들어있으면 OK. 사람-친화 헤딩 라벨링 허용.
    """
    if not must_have_sections:
        return False
    sections = composed.get("sections") or []
    for required in must_have_sections:
        req_lower = (required or "").lower()
        found = False
        for s in sections:
            heading = ((s or {}).get("heading") or "").lower()
            kicker = ((s or {}).get("kicker") or "").lower()
            if req_lower in heading or req_lower in kicker or heading.startswith(req_lower):
                found = True
                break
        if not found:
            return True   # 누락.
    return False


def _check_exhibit_ref_broken(composed: dict[str, Any]) -> tuple[bool, list[int]]:
    """prose 안의 [[ex:N]] 가 실제 exhibit 에 있는지."""
    exhibits = composed.get("exhibits") or composed.get("charts") or []
    if not isinstance(exhibits, list):
        exhibits = []
    valid_ids = {
        i for i in range(1, len(exhibits) + 1)
    }
    # exhibit_id 가 명시적으로 박혀 있다면 그것도 valid.
    for i, ex in enumerate(exhibits, start=1):
        if isinstance(ex, dict):
            xid = ex.get("exhibit_id")
            if isinstance(xid, int):
                valid_ids.add(xid)

    sections = composed.get("sections") or []
    broken: list[int] = []
    for s in sections:
        prose = (s or {}).get("prose") or ""
        refs = _collect_exhibit_refs(prose)
        for ref in refs:
            if ref not in valid_ids:
                broken.append(ref)
    return bool(broken), sorted(set(broken))


def _check_chart_without_source(composed: dict[str, Any]) -> tuple[bool, list[str]]:
    """exhibit.source_ids 비어있음 (AP-V5-26)."""
    exhibits = composed.get("exhibits") or []
    if not isinstance(exhibits, list):
        return False, []
    bad: list[str] = []
    for ex in exhibits:
        if not isinstance(ex, dict):
            continue
        sids = ex.get("source_ids") or []
        non_empty = [s for s in sids if isinstance(s, str) and s.strip()]
        if not non_empty:
            bad.append(ex.get("title", "<untitled>"))
    return bool(bad), bad


def _check_report_too_short(composed: dict[str, Any], mode: str) -> tuple[bool, int, int]:
    chars = _total_prose_chars(composed)
    lower = MODE_LOWER_BOUND.get(mode, 3500)
    return chars < lower, chars, lower


def _check_closing_missing(composed: dict[str, Any]) -> bool:
    closing = composed.get("closing") or ""
    return not closing.strip()


def _check_mobile_overflow(html_text: str) -> bool:
    """모바일 viewport 가로 overflow 검출 — 정적 가드.

    Playwright 가 렌더 후 측정하는 게 정확하지만, 본 모듈은 *결정적*. CSS
    의 hard-coded width / table 의 colspan 같은 *명백한 신호* 만 검사.
    """
    if not html_text:
        return False
    # width: NNNpx (NNN > 400) 가 inline 스타일에 박혀 있으면 모바일 오버플로 가능.
    suspicious = re.findall(r'width:\s*(\d+)px', html_text)
    for w in suspicious:
        try:
            if int(w) > 400:   # 모바일 375px + 24px 임계
                return True
        except ValueError:
            continue
    # min-width 도 검사.
    suspicious2 = re.findall(r'min-width:\s*(\d+)px', html_text)
    for w in suspicious2:
        try:
            if int(w) > 375:
                return True
        except ValueError:
            continue
    return False


# ─── 5종 Soft Fail (Plan §15.5) ──────────────────────────────────────


def _check_asymmetry_gini(composed: dict[str, Any]) -> tuple[bool, float]:
    sections = composed.get("sections") or []
    chars = [len(((s or {}).get("prose") or "")) for s in sections]
    gini = _gini_coefficient([float(c) for c in chars if c > 0])
    return gini > SOFT_GINI_THRESHOLD, gini


def _check_chart_count_exceeded(
    composed: dict[str, Any], mode: str
) -> tuple[bool, int, int]:
    """mode 별 차트 상한 초과 — Plan §13.8 + AP-V5-9."""
    exhibits = composed.get("exhibits") or composed.get("charts") or []
    if not isinstance(exhibits, list):
        # ComposedSection.charts 가 분산된 v4.5.7 형식일 수도.
        sections = composed.get("sections") or []
        exhibits = []
        for s in sections:
            if isinstance(s, dict):
                exhibits.extend(s.get("charts") or [])

    count = len(exhibits)
    limit = {
        "fast": ChartCountLimits.fast,
        "standard": ChartCountLimits.standard,
        "deep": ChartCountLimits.deep,
    }.get(mode, ChartCountLimits.standard)
    return count > limit, count, limit


def _check_chart_type_monotony(
    composed: dict[str, Any], mode: str
) -> tuple[bool, int, int]:
    """v5.2.14 Layer 4 — chart type diversity 쿼터.

    캔들 회귀 (production 13종 중 70% 가 bar/line/donut) 차단의 SSOT.
    한 보고서 안에 충분한 차트가 있는데도 type 다양성이 부족하면 soft fail.

    임계:
        fast       : skip (1-2 차트는 자연스레 monotony)
        standard   : charts ≥ 3 + distinct types < 2 → soft fail
        deep       : charts ≥ 5 + distinct types < 3 → soft fail

    Returns:
        (flag, chart_count, distinct_types)
    """
    exhibits = composed.get("exhibits") or composed.get("charts") or []
    if not isinstance(exhibits, list):
        sections = composed.get("sections") or []
        exhibits = []
        for s in sections:
            if isinstance(s, dict):
                exhibits.extend(s.get("charts") or [])
    types: list[str] = []
    for ch in exhibits:
        if isinstance(ch, dict):
            t = ch.get("type")
            if isinstance(t, str) and t:
                types.append(t)
    chart_count = len(types)
    distinct = len(set(types))
    if mode == "fast":
        return False, chart_count, distinct
    if mode == "standard" and chart_count >= 3 and distinct < 2:
        return True, chart_count, distinct
    if mode == "deep" and chart_count >= 5 and distinct < 3:
        return True, chart_count, distinct
    return False, chart_count, distinct


def _check_watch_signal_all_ambiguous(composed: dict[str, Any]) -> tuple[bool, int]:
    signals = composed.get("watch_signals") or []
    if not signals:
        return False, 0
    actionable = sum(
        1 for s in signals
        if isinstance(s, dict) and (s.get("direction") or "") in ("confirms_base", "rejects_base")
    )
    return actionable == 0, len(signals)


# ─── 통합 entry — run_deterministic_gate ─────────────────────────────


def run_deterministic_gate(
    composed: dict[str, Any],
    *,
    rendered_html_path: str | Path | None = None,
    mode: str = "standard",
    must_have_sections: list[str] | None = None,
    playwright_timed_out: bool = False,
) -> DeterministicGateResult:
    """Plan §15 의 통합 진입. Phase 7 LLM Desk *전* 호출.

    Args:
        composed: ComposedReport dict (v4.5.7 형식 또는 V5 dict).
        rendered_html_path: Renderer 가 emit 한 HTML 경로. None 이면 일부
            검사 (html_render_failed / asset_404 등) 자동 fail.
        mode: fast / standard / deep — chart count + report length 임계.
        must_have_sections: ResearchDirector AnalysisBrief.must_have_sections.
        playwright_timed_out: capture stage 의 timeout 신호 — Phase 7-pre 가
            전달.

    Returns:
        DeterministicGateResult — decision (publish/soft_fail/kill) +
        hard_failures + soft_failures + metrics.
    """
    hard: list[str] = []
    soft: list[str] = []
    metrics: dict[str, Any] = {}

    # ─── Hard 1: html_render_failed
    if rendered_html_path and _check_html_render_failed(rendered_html_path):
        hard.append("html_render_failed")

    # HTML 텍스트 로드.
    html_text = ""
    html_dir = None
    if rendered_html_path and Path(rendered_html_path).exists():
        try:
            html_text = Path(rendered_html_path).read_text(encoding="utf-8")
            html_dir = Path(rendered_html_path).resolve().parent
        except Exception as e:
            logger.warning("[deterministic_gate] HTML 로드 실패: %s", e)

    # ─── Hard 2: html_unparseable
    if html_text and _check_html_unparseable(html_text):
        hard.append("html_unparseable")

    # ─── Hard 3: required_section_missing
    if _check_required_section_missing(composed, must_have_sections):
        hard.append("required_section_missing")
        metrics["missing_sections"] = [
            s for s in (must_have_sections or [])
            if not _section_present(composed, s)
        ]

    # ─── Hard 4: exhibit_ref_broken
    broken_flag, broken_ids = _check_exhibit_ref_broken(composed)
    if broken_flag:
        hard.append("exhibit_ref_broken")
        metrics["broken_exhibit_refs"] = broken_ids

    # ─── Hard 5: chart_without_source (AP-V5-26)
    chart_no_src_flag, bad_charts = _check_chart_without_source(composed)
    if chart_no_src_flag:
        hard.append("chart_without_source")
        metrics["charts_without_source"] = bad_charts

    # ─── Hard 6: chart_container_empty
    if html_text and _has_empty_chart_containers(html_text):
        hard.append("chart_container_empty")

    # ─── Hard 7: report_too_short
    short_flag, total_chars, lower_bound = _check_report_too_short(composed, mode)
    metrics["total_prose_chars"] = total_chars
    metrics["mode_lower_bound"] = lower_bound
    if short_flag:
        hard.append("report_too_short")

    # ─── Hard 8: closing_missing
    if _check_closing_missing(composed):
        hard.append("closing_missing")

    # ─── Hard 9: asset_404
    if html_text and html_dir is not None:
        has404, missing = _has_404_assets(html_text, html_dir)
        if has404:
            hard.append("asset_404")
            metrics["missing_assets"] = missing

    # ─── Hard 10: mobile_horizontal_overflow
    if html_text and _check_mobile_overflow(html_text):
        hard.append("mobile_horizontal_overflow")

    # ─── Hard 11: playwright_timeout
    if playwright_timed_out:
        hard.append("playwright_timeout")

    # ─── Soft 1: asymmetry_gini
    gini_flag, gini = _check_asymmetry_gini(composed)
    metrics["section_length_gini"] = round(gini, 3)
    if gini_flag:
        soft.append(f"asymmetry_gini({gini:.2f}>{SOFT_GINI_THRESHOLD})")

    # ─── Soft 2: chart_count_exceeded
    exc_flag, count, limit = _check_chart_count_exceeded(composed, mode)
    metrics["chart_count"] = count
    metrics["chart_limit"] = limit
    if exc_flag:
        soft.append(f"chart_count_exceeded({count}>{limit})")

    # ─── Soft 3: heading_pattern_repetitive
    if _heading_repetitive(composed):
        soft.append("heading_pattern_repetitive")

    # ─── Soft 4: watch_signal_all_ambiguous
    ws_flag, ws_total = _check_watch_signal_all_ambiguous(composed)
    metrics["watch_signal_count"] = ws_total
    if ws_flag:
        soft.append("watch_signal_all_ambiguous")

    # ─── Soft 5: stale_source_ratio
    stale_ratio = _stale_source_ratio(composed)
    metrics["stale_source_ratio"] = round(stale_ratio, 2)
    if stale_ratio > SOFT_STALE_RATIO_THRESHOLD:
        soft.append(f"stale_source_ratio({stale_ratio:.0%}>{int(SOFT_STALE_RATIO_THRESHOLD*100)}%)")

    # ─── Soft 6: chart_type_monotony (v5.2.14 Layer 4)
    mono_flag, mono_count, mono_distinct = _check_chart_type_monotony(composed, mode)
    metrics["chart_distinct_types"] = mono_distinct
    if mono_flag:
        soft.append(
            f"chart_type_monotony({mono_distinct} distinct of {mono_count} charts, mode={mode})"
        )

    # ─── 결정 ──────────────────────────────────────────────────────
    if hard:
        return DeterministicGateResult(
            passed=False,
            decision="kill",
            hard_failures=hard,
            soft_failures=soft,
            metrics=metrics,
        )
    if soft:
        return DeterministicGateResult(
            passed=True,
            decision="soft_fail",
            hard_failures=[],
            soft_failures=soft,
            metrics=metrics,
        )
    return DeterministicGateResult(
        passed=True,
        decision="publish",
        hard_failures=[],
        soft_failures=[],
        metrics=metrics,
    )


def _section_present(composed: dict[str, Any], required: str) -> bool:
    sections = composed.get("sections") or []
    req_lower = (required or "").lower()
    for s in sections:
        heading = ((s or {}).get("heading") or "").lower()
        kicker = ((s or {}).get("kicker") or "").lower()
        if req_lower in heading or req_lower in kicker:
            return True
    return False


# ─── 명세 SSOT export ────────────────────────────────────────────────


HARD_FAIL_RULES: list[str] = [
    "html_render_failed",
    "html_unparseable",
    "required_section_missing",
    "exhibit_ref_broken",
    "chart_without_source",
    "chart_container_empty",
    "report_too_short",
    "closing_missing",
    "asset_404",
    "mobile_horizontal_overflow",
    "playwright_timeout",
]


SOFT_FAIL_RULES: list[str] = [
    "asymmetry_gini",
    "chart_count_exceeded",
    "heading_pattern_repetitive",
    "watch_signal_all_ambiguous",
    "stale_source_ratio",
    # v5.2.14 — Layer 4 of 5-Layer Usage Guarantee. 차트 type collapse 차단.
    "chart_type_monotony",
]
