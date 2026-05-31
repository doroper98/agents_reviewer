"""v5.5.0 — FullAnalysisResult → ReportBundle 빌더 (osint_generator 계약 v1).

SSOT: docs/CONTRACTS/report_bundle_v1.md. composer 산출(composed_report) +
context 를 버전 박힌 핸드오프 산출물로 매핑한다. composer SYSTEM_PROMPT 는
건드리지 않는다 — provenance 는 *결정론* 으로 배선 (계약 §2 + market_fetcher
출처 자동주입).

Q5 verification 배선 (결정론, 보수적):
- 차트가 context.time_series 의 instrument 와 매칭 (candle/line/area) → measured
  → confirmed + source 자동주입.
- type == forecast (미매칭) → model_forecast → inferred.
- 그 외 composer 차트 → narrative_inference → inferred.
거짓 confirmed 가 거짓 inferred 보다 위험하므로(§3, consumer floor 없음),
positive 매칭일 때만 confirmed.

v5.5.0 한계 (계약에 명시):
- claims[] = [] — 라이브 2-call 경로는 Claim/Evidence 그래프를 안 만든다.
  라벨 척추는 charts[].provenance.verification 가 진다. prose→claim 추출은 fast-follow.
- prerendered_svg — A안 17종 차트는 None (consumer 가 데이터로 재렌더). B안 복잡
  4종 (map/choropleth/network/sankey) 은 ``prerender_svg=True`` + Playwright 가용 시
  폴백 SVG 로 채워짐 (v5.5.6, 계약 §5). 미가용 시 None (graceful). SSOT: svg_prerender.py.
- section.map_ref = None — composer 가 섹션↔지도 바인딩을 emit 하기 전까지(§10).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from src.timeutil import now_kst, today_kst
from src.models import (
    ORIGIN_TO_VERIFICATION,
    BundleChart,
    BundleConfidence,
    BundleContradiction,
    BundleMap,
    BundleProducer,
    BundleProvenance,
    BundleReport,
    BundleSection,
    BundleSignal,
    BundleSource,
    BundleTheme,
    BundleTimeline,
    BundleTimelinePoint,
    BundleTopSource,
    FullAnalysisResult,
    ReportBundle,
)
from src.timeline_flow import build_timeline_flow

logger = logging.getLogger(__name__)

_CSS_PATH = Path(__file__).resolve().parent.parent / "templates" / "report.css"
_TOKEN_NAMES = ("bg", "card", "text", "muted", "accent", "up", "down", "border")
_MARKET_CHART_TYPES = ("candle", "line", "area")


def _theme_tokens(theme_id: str, css_path: Path = _CSS_PATH) -> dict[str, str]:
    """report.css 의 [data-theme="id"] 블록에서 8개 토큰 추출.

    report.css 를 단일 SSOT 로 유지 (Python 사본 안 만듦 — anti-pattern #1).
    """
    if not theme_id:
        return {}
    try:
        css = css_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    needle = f'[data-theme="{theme_id}"]'
    idx = css.find(needle)
    if idx == -1:
        return {}
    brace = css.find("{", idx)
    end = css.find("}", brace) if brace != -1 else -1
    if brace == -1 or end == -1:
        return {}
    block = css[brace + 1:end]
    tokens: dict[str, str] = {}
    for m in re.finditer(r"--([\w-]+)\s*:\s*([^;]+);", block):
        name, val = m.group(1), m.group(2).strip()
        if name in _TOKEN_NAMES and name not in tokens:
            tokens[name] = val
    return tokens


def _publisher_from_url(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _market_index(time_series: list[dict]) -> dict[str, dict]:
    """instrument 표시명 → {source, code, unit} 룩업."""
    idx: dict[str, dict] = {}
    for s in time_series or []:
        if not isinstance(s, dict):
            continue
        inst = (s.get("instrument") or "").strip()
        if inst:
            idx[inst] = {
                "source": s.get("source") or "",
                "code": s.get("code") or "",
                "unit": s.get("unit") or "",
            }
    return idx


def _match_market(chart: dict, mkt_index: dict[str, dict]) -> dict | None:
    ctype = (chart.get("type") or "").lower()
    if ctype not in _MARKET_CHART_TYPES:
        return None
    title = chart.get("title") or ""
    for inst, meta in mkt_index.items():
        if inst and inst in title:
            return meta
    return None


def _chart_provenance(
    chart: dict, mkt_index: dict[str, dict], fetched_at: str, source_id: str,
) -> BundleProvenance:
    """결정론 provenance — 계약 §2. 개별 차트가 verification 직접 지정 시 우선."""
    ctype = (chart.get("type") or "").lower()
    matched = _match_market(chart, mkt_index)
    if matched:
        origin = "measured"
        sources = [BundleSource(
            source_id=source_id, provider=matched["source"],
            code=matched["code"], unit=matched["unit"], fetched_at=fetched_at,
        )]
    elif ctype == "forecast":
        origin = "model_forecast"
        sources = []
    else:
        origin = "narrative_inference"
        sources = []

    # §2 단서: composer 가 차트 dict 에 verification 을 직접 박았으면 존중.
    explicit = chart.get("verification")
    verification = explicit if explicit in ORIGIN_TO_VERIFICATION.values() or explicit in (
        "claim", "unverified", "disputed",
    ) else ORIGIN_TO_VERIFICATION[origin]
    confidence = "high" if verification == "confirmed" else "medium"
    return BundleProvenance(
        origin=origin, verification=verification,
        confidence=confidence, sources=sources,
    )


def build_report_bundle(
    result: FullAnalysisResult,
    *,
    html_url: str = "",
    system_version: str = "",
    prerender_svg: bool = False,
) -> ReportBundle:
    """FullAnalysisResult → ReportBundle (계약 v1).

    prerender_svg=True 면 B안 복잡 4종(map/choropleth/network/sankey)의
    prerendered_svg 를 Playwright 로 폴백 렌더 (계약 §5). 미가용 시 graceful None.
    """
    composed = result.composed_report
    context = result.context
    fetched_at = (context.date if context and context.date else
                  today_kst())  # v5.7.0 — KST 기준 fallback
    mkt_index = _market_index(context.time_series if context else [])

    # report_id: 저장 파일 stem (analysis_{ts}) — report_path 우선.
    report_id = ""
    if result.report_path:
        report_id = Path(result.report_path).stem
    version = system_version or result.system_version or ""
    theme_id = result.report_theme or ""

    theme = None
    if theme_id:
        theme = BundleTheme(id=theme_id, tokens=_theme_tokens(theme_id))

    report = BundleReport(
        report_id=report_id or "report",
        headline=(composed.headline if composed else ""),
        deck=(composed.deck if composed else ""),
        closing=(composed.closing if composed else ""),
        html_url=html_url or result.report_url or "",
        theme=theme,
    )

    sections: list[BundleSection] = []
    charts: list[BundleChart] = []
    src_counter = 0
    if composed:
        for i, sec in enumerate(composed.sections):
            sec_chart_refs: list[str] = []
            for ch in (sec.charts or []):
                if not isinstance(ch, dict):
                    continue
                chart_id = f"ch-{len(charts) + 1}"
                src_counter += 1
                prov = _chart_provenance(
                    ch, mkt_index, fetched_at, source_id=f"mkt-{src_counter}",
                )
                charts.append(BundleChart(
                    chart_id=chart_id,
                    type=(ch.get("type") or "").lower(),
                    title=ch.get("title") or "",
                    data=ch.get("data"),
                    note=ch.get("note") or "",
                    provenance=prov,
                ))
                sec_chart_refs.append(chart_id)
            sections.append(BundleSection(
                section_id=f"s{i + 1}",
                heading=sec.heading,
                kicker=sec.kicker or "",
                prose=sec.prose or "",
                pull_quote=sec.pull_quote or "",
                chart_refs=sec_chart_refs,
                map_ref=None,        # 계약 §10 — v5.5.0 은 null
                image_refs=[],       # v5.5.0 — 이미지 ref 는 fast-follow
                claim_refs=[],       # v5.5.0 — claims[] 비어있음
            ))

    bundle_map = None
    if composed and composed.embedded_map:
        em = composed.embedded_map
        bundle_map = BundleMap(
            id="map-1",
            center=[float(x) for x in (em.get("center") or [])][:2],
            zoom=float(em.get("zoom") or 0.0),
            markers=list(em.get("markers") or []),
            arcs=list(em.get("arcs") or []),
            legend=list(em.get("legend") or []),
            provenance=BundleProvenance(
                origin="narrative_inference",
                verification=ORIGIN_TO_VERIFICATION["narrative_inference"],
                confidence="medium",
            ),
        )

    # 계약 §5 B안 — 복잡 4종 폴백 SVG. graceful: 실패/미가용 시 prerendered_svg=None 유지.
    if prerender_svg:
        try:
            from src.handoff.svg_prerender import (
                prerender_chart_svgs,
                prerender_map_svg,
            )
            tokens = theme.tokens if theme else _theme_tokens(theme_id or "editorial_cream")
            n = prerender_chart_svgs(charts, theme_id, tokens)
            if bundle_map and composed and composed.embedded_map:
                prerender_map_svg(bundle_map, composed.embedded_map, theme_id, tokens)
            if n:
                logger.info("[bundle] prerendered %d B안 chart SVG(s)", n)
        except Exception as e:  # pragma: no cover — 안전망
            logger.warning("[bundle] prerender skip (graceful): %s", e)

    signals = [
        BundleSignal(
            signal=str(s.get("signal") or s.get("description") or ""),
            description=str(s.get("description") or ""),
            indicates=str(s.get("indicates") or ""),
            deadline=str(s.get("deadline") or ""),
        )
        for s in (composed.watch_signals if composed else [])
        if isinstance(s, dict)
    ]
    contradictions = [
        BundleContradiction(
            side_a=str(c.get("side_a") or ""),
            side_b=str(c.get("side_b") or ""),
            evidence=str(c.get("evidence") or ""),
            resolution=str(c.get("resolution") or ""),
        )
        for c in (composed.contradictions if composed else [])
        if isinstance(c, dict)
    ]

    sources: list[BundleTopSource] = []
    for i, url in enumerate(context.sources if context else []):
        if not isinstance(url, str) or not url:
            continue
        sources.append(BundleTopSource(
            source_id=f"src-{i + 1}", url=url,
            publisher=_publisher_from_url(url), fetched_at=fetched_at,
        ))

    confidence = None
    if composed:
        confidence = BundleConfidence(
            score=float(composed.confidence_score or 0.0),
            summary=composed.confidence_summary or "",
        )

    bundle_timeline = None
    tf = build_timeline_flow(context, composed)
    if tf and tf.get("points"):
        bundle_timeline = BundleTimeline(
            heading=tf.get("heading", ""),
            points=[BundleTimelinePoint(**p) for p in tf["points"]],
        )

    return ReportBundle(
        schema_version=1,
        generated_at=now_kst().isoformat(),  # v5.7.0 — KST 기준
        producer=BundleProducer(
            system="agents_reviewer", version=version,
            mode=result.request.mode if result.request else "standard",
        ),
        report=report,
        sections=sections,
        charts=charts,
        map=bundle_map,
        claims=[],
        signals=signals,
        contradictions=contradictions,
        sources=sources,
        confidence=confidence,
        timeline=bundle_timeline,
    )
