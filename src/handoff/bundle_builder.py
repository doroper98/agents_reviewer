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
    BundleReportVideo,
    BundleSection,
    BundleSectionVideo,
    BundleSignal,
    BundleSource,
    BundleTheme,
    BundleTimeline,
    BundleTimelinePoint,
    BundleTimelineVideo,
    BundleTopSource,
    FullAnalysisResult,
    ReportBundle,
)
from src.timeline_flow import build_timeline_flow

logger = logging.getLogger(__name__)

_CSS_PATH = Path(__file__).resolve().parent.parent / "templates" / "report.css"
_TOKEN_NAMES = ("bg", "card", "text", "muted", "accent", "up", "down", "border")
_MARKET_CHART_TYPES = ("candle", "line", "area")

# 계약 §13 — 영상 자막 한도 (consumer 가 초과분을 … 로 자르므로 producer 는 warn).
# v7.6.0 — 1차 음성 검수: 축약 금지·말하듯 풀어쓰기 위해 58→75 완화 (자막 줄바꿈은
# 영상 쪽 처리, 양측 합의값).
_NARRATION_MAX_CHARS = 75
_HIGHLIGHT_MAX_CHARS = 40
_NARRATION_MAX_ITEMS = 4
_HIGHLIGHT_MAX_ITEMS = 3
_REPORT_NARRATION_MAX_ITEMS = 2

# 계약 §13 / prompts/tts_narration_guide.md — TTS가 깨뜨릴 표기 탐지 (warn-only).
# 영문(약어), 숫자(콤마·소수·범위 포함), 발화 변환 필요한 기호. 자동 재작성은 안 한다
# (한자어/고유어·문맥 의존이라 결정적 변환은 오히려 오독을 만든다 — 가이드 §0/§7).
_TTS_RISK_RE = re.compile(r"[A-Za-z]|[0-9]|[%/:~→±<>]")


def _strs(items, cap: int | None = None) -> list[str]:
    out = [s.strip() for s in (items or []) if isinstance(s, str) and s.strip()]
    return out[:cap] if cap else out


def _warn_tts_gap(narration: list[str], narration_tts: list[str], where: str) -> None:
    """narration 에 TTS 위험 표기가 있는데 narration_tts 누락/개수불일치면 warn.

    영상 음성 품질의 1차 방어는 composer SYSTEM_PROMPT(★ TTS 발화 규칙) + 가이드.
    여기선 누락만 표면화 (운영자가 bot.log 로 인지) — 자동 보정은 하지 않는다.
    """
    risky = [s for s in narration if _TTS_RISK_RE.search(s)]
    if not risky:
        return
    if not narration_tts:
        logger.warning(
            "[bundle] §13 %s: narration 에 TTS 위험 표기 있음(%d문장)인데 narration_tts 누락 "
            "— 음성 오독 위험. 예: %r", where, len(risky), risky[0],
        )
    elif len(narration_tts) != len(narration):
        logger.warning(
            "[bundle] §13 %s: narration_tts 개수(%d)가 narration(%d)과 불일치 "
            "— consumer 정렬 깨짐 위험.", where, len(narration_tts), len(narration),
        )


def _section_video(video: dict | None, section_id: str) -> BundleSectionVideo | None:
    """계약 §13 — composer 의 섹션 video emit → BundleSectionVideo (결정론 가드).

    - narration ≤4 / highlights ≤3 캡 (초과분 절단).
    - emphasis 는 narration/highlights 안의 *정확한 부분 문자열* 만 보존 — 불일치
      항목은 drop (consumer 액센트 매칭이 어차피 실패하므로 emit 전에 정리).
    - 길이 한도(75/40자) 초과는 drop 하지 않고 warn (consumer 가 … 로 자름 — 정보
      파괴보다 graceful 절단이 낫다. 1차 방어는 composer SYSTEM_PROMPT).
    - narration/highlights 둘 다 비면 None (= video 부재, consumer 기존 동작).
    """
    if not isinstance(video, dict):
        return None
    narration = _strs(video.get("narration"), _NARRATION_MAX_ITEMS)
    highlights = _strs(video.get("highlights"), _HIGHLIGHT_MAX_ITEMS)
    if not narration and not highlights:
        return None
    narration_tts = _strs(video.get("narration_tts"))
    haystack = narration + highlights
    emphasis: list[str] = []
    for e in _strs(video.get("emphasis")):
        if any(e in h for h in haystack):
            emphasis.append(e)
        else:
            logger.warning(
                "[bundle] §13 %s: emphasis %r 가 narration/highlights 의 부분 문자열이 아님 — drop",
                section_id, e,
            )
    for s in narration:
        if len(s) > _NARRATION_MAX_CHARS:
            logger.warning(
                "[bundle] §13 %s: narration %d자 > %d자 한도 (영상에서 잘림): %r",
                section_id, len(s), _NARRATION_MAX_CHARS, s,
            )
    for s in highlights:
        if len(s) > _HIGHLIGHT_MAX_CHARS:
            logger.warning(
                "[bundle] §13 %s: highlight %d자 > %d자 한도 (영상에서 잘림): %r",
                section_id, len(s), _HIGHLIGHT_MAX_CHARS, s,
            )
    _warn_tts_gap(narration, narration_tts, section_id)
    return BundleSectionVideo(
        narration=narration, highlights=highlights,
        emphasis=emphasis, narration_tts=narration_tts,
    )


def _report_video(video: dict | None) -> BundleReportVideo | None:
    """계약 §13 — 보고서 레벨 intro/outro 내레이션. 둘 다 비면 None.

    v7.4.1 — 섹션과 동일한 표기/발화 분리: `intro_narration_tts` /
    `outro_narration_tts` (위험 표기 누락 시 `_warn_tts_gap` warn).
    """
    if not isinstance(video, dict):
        return None
    intro = _strs(video.get("intro_narration"), _REPORT_NARRATION_MAX_ITEMS)
    outro = _strs(video.get("outro_narration"), _REPORT_NARRATION_MAX_ITEMS)
    if not intro and not outro:
        return None
    intro_tts = _strs(video.get("intro_narration_tts"), _REPORT_NARRATION_MAX_ITEMS)
    outro_tts = _strs(video.get("outro_narration_tts"), _REPORT_NARRATION_MAX_ITEMS)
    _warn_tts_gap(intro, intro_tts, "report.video(intro)")
    _warn_tts_gap(outro, outro_tts, "report.video(outro)")
    return BundleReportVideo(
        intro_narration=intro, outro_narration=outro,
        intro_narration_tts=intro_tts, outro_narration_tts=outro_tts,
    )


def _timeline_video(video: dict | None) -> BundleTimelineVideo | None:
    """계약 §13 (v7.6.0) — 타임라인 씬 내레이션. narration 비면 None.

    composer 의 timeline_flow.video 패스스루(src/timeline_flow.py)를 섹션과 같은
    결정론 가드(캡·길이 warn·TTS gap warn)로 정리해 emit. 영상 쪽 기계 문장
    폴백을 producer 대본으로 대체하는 채널 — 분기점 라벨 낭독 금지 등 작성
    규칙의 1차 방어는 composer SYSTEM_PROMPT.
    """
    if not isinstance(video, dict):
        return None
    narration = _strs(video.get("narration"), _NARRATION_MAX_ITEMS)
    if not narration:
        return None
    narration_tts = _strs(video.get("narration_tts"))
    for s in narration:
        if len(s) > _NARRATION_MAX_CHARS:
            logger.warning(
                "[bundle] §13 timeline.video: narration %d자 > %d자 한도 (영상에서 잘림): %r",
                len(s), _NARRATION_MAX_CHARS, s,
            )
    _warn_tts_gap(narration, narration_tts, "timeline.video")
    return BundleTimelineVideo(narration=narration, narration_tts=narration_tts)


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
        video=_report_video(composed.video if composed else None),  # 계약 §13
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
                    # v6.1.1 — 계약 §12: compact strip(보조 시계열 묶음) vs 본문 단일차트.
                    # 렌더러(freeform_essay.html)와 동일 규칙 — role=='compact' → strip.
                    display="strip" if (ch.get("role") == "compact") else "full",
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
                video=_section_video(sec.video, f"s{i + 1}"),  # 계약 §13 (v7.3.0)
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
            video=_timeline_video(tf.get("video")),  # 계약 §13 (v7.6.0)
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
