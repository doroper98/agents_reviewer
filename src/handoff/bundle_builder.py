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
    BundleContradictionVideo,
    BundleImage,
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
_CONTRA_LABEL_MAX_CHARS = 8   # v7.6.2 — 쟁점 진영 이름 (label_a/b)
_CONTRA_LINE_MAX_CHARS = 40   # v7.6.2 — 쟁점 한 줄 경어체 (line_a/b)
_NARRATION_MAX_ITEMS = 4
_HIGHLIGHT_MAX_ITEMS = 3
_REPORT_NARRATION_MAX_ITEMS = 2

# 계약 §13 / prompts/tts_narration_guide.md — TTS가 깨뜨릴 표기 탐지 (warn-only).
# 영문(약어), 숫자(콤마·소수·범위 포함), 발화 변환 필요한 기호. 자동 재작성은 안 한다
# (한자어/고유어·문맥 의존이라 결정적 변환은 오히려 오독을 만든다 — 가이드 §0/§7).
_TTS_RISK_RE = re.compile(r"[A-Za-z]|[0-9]|[%/:~→±<>]")

# 계약 §13 / 3차 음성 검수 (v7.6.3) — narration 비문·완결성·레지스터 결정론 warn
# (warn-only, 절대 drop·재작성 안 함 — 한국어 문법 판정은 휴리스틱이라 보수적).
# 1차 방어는 composer SYSTEM_PROMPT(★ 3차 검수) + 가이드 §1.
_NEG_INTENT_RE = re.compile(r"절대로|결코")          # 부정·불가능 의도 부사
# 실제 부정어 (수 없는/않는/못 …). '못' 은 부정 보조용언 형태만 — '못박다'(강조
# 합성동사)의 '못' 을 부정으로 오인하지 않도록 뒤 음절을 제한 (검수 BAD 예 '못박았다').
_NEG_WORD_RE = re.compile(r"없|않|아니|말[아라]|못(?=\s|하|한|할|해|했|함|합)")
# 비교·접속 도중 절단 의심: 문장이 이런 연결 형태로 *끝나면* 미완성.
_TRUNCATED_TAIL_RE = re.compile(
    r"(보다|보단|때문|위해|통해|대해|에서|으로|로서|면서|지만|는데|"
    r"그리고|그러나|또는|및|와|과|의)$"
)
# 다큐 경어체 평서종결: '다'로 끝나되 '니다'(입니다/합니다/됩니다)가 아니면 논설체 의심.
_PLAIN_ENDING_TAIL = ".…!?\"')]》」』 \t"


def _warn_narration_quality(sentences: list[str], where: str) -> None:
    """3차 음성 검수 (v7.6.3) — narration 문장의 비문·미완결·논설체 종결을 warn.

    셋 다 검수에서 *반복* 발견된 사고라 결정론으로 표면화한다 (drop 아님):
    1) '절대로/결코' 부정 의도인데 부정어(없/않/못)가 없음 → 의미 반전 위험.
    2) 비교·접속 어미('…보다', '…때문에')로 끝나는 절단 문장.
    3) 종결어미가 경어체(~입니다/합니다/됩니다)가 아닌 평서형 '~다'.
    """
    for s in sentences:
        body = s.rstrip(_PLAIN_ENDING_TAIL)
        if not body:
            continue
        if _NEG_INTENT_RE.search(s) and not _NEG_WORD_RE.search(s):
            logger.warning(
                "[bundle] §13 %s: '절대로/결코' 있는데 부정어(수 없는/않는) 없음 "
                "— 의미 반전 위험: %r", where, s,
            )
        if _TRUNCATED_TAIL_RE.search(body):
            logger.warning(
                "[bundle] §13 %s: 비교·접속 어미로 끝나는 미완결 문장 (자막 절단) "
                "— 서술어로 닫을 것: %r", where, s,
            )
        if body.endswith("다") and not body.endswith("니다"):
            logger.warning(
                "[bundle] §13 %s: 종결어미가 평서형 '~다' (논설체) — 다큐 경어체"
                "(~입니다/합니다/됩니다)로: %r", where, s,
            )


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


def _section_video(
    video: dict | None, section_id: str, heading: str = "",
) -> BundleSectionVideo | None:
    """계약 §13 — composer 의 섹션 video emit → BundleSectionVideo (결정론 가드).

    - narration ≤4 / highlights ≤3 캡 (초과분 절단).
    - emphasis 는 narration/highlights 안의 *정확한 부분 문자열* 만 보존 — 불일치
      항목은 drop (consumer 액센트 매칭이 어차피 실패하므로 emit 전에 정리).
    - 길이 한도(75/40자) 초과는 drop 하지 않고 warn (consumer 가 … 로 자름 — 정보
      파괴보다 graceful 절단이 낫다. 1차 방어는 composer SYSTEM_PROMPT).
    - highlight 가 heading 을 그대로 메아리치면 warn (v7.6.2, 2차 음성 검수 —
      화면에 같은 말 두 번. highlight 는 heading 이 안 보여준 수치·고유명사를 담아야).
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
    heading_norm = (heading or "").strip()
    for s in highlights:
        if len(s) > _HIGHLIGHT_MAX_CHARS:
            logger.warning(
                "[bundle] §13 %s: highlight %d자 > %d자 한도 (영상에서 잘림): %r",
                section_id, len(s), _HIGHLIGHT_MAX_CHARS, s,
            )
        if heading_norm and s.strip() == heading_norm:
            logger.warning(
                "[bundle] §13 %s: highlight %r 가 heading 을 그대로 반복 (화면 중복) "
                "— heading 이 안 보여준 수치·고유명사로 교체 권장 (WRITE 2차 검수)",
                section_id, s,
            )
    _warn_tts_gap(narration, narration_tts, section_id)
    _warn_narration_quality(narration, section_id)  # v7.6.3 — 비문·완결성·경어체
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
    _warn_narration_quality(intro, "report.video(intro)")    # v7.6.3
    _warn_narration_quality(outro, "report.video(outro)")    # v7.6.3
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
    _warn_narration_quality(narration, "timeline.video")  # v7.6.3
    return BundleTimelineVideo(narration=narration, narration_tts=narration_tts)


def _contradiction_video(video: dict | None, where: str) -> BundleContradictionVideo | None:
    """계약 §13 (v7.6.2) — 쟁점(모순) 카드 내레이션. 모든 필드 비면 None.

    영상이 side_a/side_b 논설체 원문을 카드/자막에 그대로 노출하던 것을 producer
    의 다큐 경어체 대본으로 대체 (2차 음성 검수). label_a/b(≤8자)·line_a/b(≤40자)
    초과는 drop 하지 않고 warn (consumer 절단), narration 은 섹션과 동일 규칙.
    label/line/narration 이 모두 비면 None (= video 부재, consumer 기존 원문 폴백).
    """
    if not isinstance(video, dict):
        return None
    label_a = (str(video.get("label_a") or "")).strip()
    label_b = (str(video.get("label_b") or "")).strip()
    line_a = (str(video.get("line_a") or "")).strip()
    line_b = (str(video.get("line_b") or "")).strip()
    narration = _strs(video.get("narration"), _NARRATION_MAX_ITEMS)
    if not any((label_a, label_b, line_a, line_b)) and not narration:
        return None
    narration_tts = _strs(video.get("narration_tts"))
    for tag, val, cap in (
        ("label_a", label_a, _CONTRA_LABEL_MAX_CHARS),
        ("label_b", label_b, _CONTRA_LABEL_MAX_CHARS),
        ("line_a", line_a, _CONTRA_LINE_MAX_CHARS),
        ("line_b", line_b, _CONTRA_LINE_MAX_CHARS),
    ):
        if len(val) > cap:
            logger.warning(
                "[bundle] §13 %s: %s %d자 > %d자 한도 (영상에서 잘림): %r",
                where, tag, len(val), cap, val,
            )
    for s in narration:
        if len(s) > _NARRATION_MAX_CHARS:
            logger.warning(
                "[bundle] §13 %s: narration %d자 > %d자 한도 (영상에서 잘림): %r",
                where, len(s), _NARRATION_MAX_CHARS, s,
            )
    _warn_tts_gap(narration, narration_tts, where)
    # v7.6.3 — narration + 한 줄 경어체(line_a/b) 의 비문·논설체 종결 warn.
    _warn_narration_quality(narration + [v for v in (line_a, line_b) if v], where)
    return BundleContradictionVideo(
        label_a=label_a, label_b=label_b, line_a=line_a, line_b=line_b,
        narration=narration, narration_tts=narration_tts,
    )


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


# ── 보도 사진 (계약 IMAGE_BUNDLE_CONTRACT v1, v8.3.5) ───────────────────────
_CAPTION_MAX = 60  # 계약 §1 — caption ≤60자 (영상 화면 캡션 겸 대체텍스트)

# 계약(개정) §3.1 — 정부 공식 배포(공공누리 계열)·보도자료 와이어 도메인. credit
# 유무와 무관하게 '공식 배포' 근거로 cleared.
_CLEARED_HOST_SUFFIXES = (
    ".go.kr", ".gov", ".gov.kr", "korea.kr",           # 정부 공식 배포 (공공누리)
    "prnewswire.com", "businesswire.com", "newswire.co.kr", "prtimes.jp",  # 보도자료 와이어
)


def _cap_caption(text: str, limit: int = _CAPTION_MAX) -> str:
    """계약 §1 — caption ≤60자. 넘으면 잘라 말줄임 (영상 화면 캡션용)."""
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1].rstrip() + "…"


def _image_rights(credit: str, source_url: str) -> tuple[str, str]:
    """계약(개정) §3.1-a — 보도 사진 권리 상태 + license 근거.

    본 시스템은 *봇 본인 사용 목적* 이라 출처표기(credit)로 저작권을 갈음한다
    (CLAUDE.md 기존 방침 'Report Images'; 사용자 결정 2026-07-08 —
    IMAGE_BUNDLE_CONTRACT §3.1-a 개정, osint_generator 와 동기화).

    **불변식: cleared ⇒ credit 비어있지 않음.** cleared 의 근거가 '출처표기 갈음'
    이므로 credit 없이는 attribution 이 불가 → cleared 불가. consumer(osint_generator
    v0.42.2)의 credit gate(credit 빈 cleared 거부)와 정합 — producer 가 애초에
    credit 없는 cleared 를 emit 하지 않는다 (공식배포 도메인이라도 credit 필수).

      · credit 없음                          → needs_review (영상 스킵 + 기록)
      · credit 있음 + 정부 공식 배포·와이어 도메인 → cleared (license='공식 배포')
      · credit 있음 (그 외)                   → cleared (license='출처표기')
    반환: (rights_status, license).
    """
    credit = (credit or "").strip()
    if not credit:
        return "needs_review", ""
    try:
        host = (urlparse(source_url).hostname or "").lower()
    except Exception:
        host = ""
    official = bool(host and any(
        host == suf.lstrip(".") or host.endswith(suf) for suf in _CLEARED_HOST_SUFFIXES
    ))
    return ("cleared", "공식 배포") if official else ("cleared", "출처표기")


def _build_images(
    composed, sources: list[BundleTopSource],
) -> tuple[list[BundleImage], dict[int, list[str]]]:
    """composer 가 고른 hero/섹션 사진 → BundleImage[] + 섹션 인덱스별 image_refs.

    계약 IMAGE_BUNDLE_CONTRACT v1. dedup by url (hero==섹션사진 중복 방지). hero 는
    첫 섹션의 오프닝(발단) 사진으로 연결. 반환: (images, {section_idx: [image_id]}).
    """
    if not composed:
        return [], {}
    src_by_url = {s.url: s.source_id for s in sources if s.url}
    url_to_id: dict[str, str] = {}
    images: list[BundleImage] = []
    section_refs: dict[int, list[str]] = {}

    def _add(img: object) -> str | None:
        if not isinstance(img, dict):
            return None
        url = (img.get("image_url") or "").strip()
        if not url:
            return None
        if url in url_to_id:
            return url_to_id[url]
        image_id = f"img-{len(images) + 1}"
        source_url = (img.get("source_url") or "").strip()
        credit = (img.get("credit") or "").strip()
        rights, lic = _image_rights(credit, source_url)
        images.append(BundleImage(
            image_id=image_id,
            url=url,
            caption=_cap_caption(img.get("caption") or ""),
            credit=credit,
            rights_status=rights,
            license=lic,
            source_id=src_by_url.get(source_url, ""),
            focus="center",
        ))
        url_to_id[url] = image_id
        return image_id

    hero_id = _add(composed.hero_image) if composed.hero_image else None

    for i, sec in enumerate(composed.sections):
        refs: list[str] = []
        for img in (getattr(sec, "images", None) or []):
            iid = _add(img)
            if iid and iid not in refs:
                refs.append(iid)
        if refs:
            section_refs[i] = refs

    # hero → 첫 섹션 오프닝 사진 (발단). 섹션 자체 사진보다 앞.
    if hero_id is not None and composed.sections:
        first = section_refs.setdefault(0, [])
        if hero_id not in first:
            first.insert(0, hero_id)

    return images, section_refs


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
                video=_section_video(sec.video, f"s{i + 1}", sec.heading),  # 계약 §13 (v7.3.0, heading-echo warn v7.6.2)
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
            video=_contradiction_video(c.get("video"), f"contradiction[{ci}]"),  # 계약 §13 (v7.6.2)
        )
        for ci, c in enumerate(composed.contradictions if composed else [])
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

    # 계약 IMAGE_BUNDLE_CONTRACT v1 (v8.3.5) — hero/섹션 사진 → images[] + image_refs.
    images, section_refs = _build_images(composed, sources)
    for i, s in enumerate(sections):
        refs = section_refs.get(i)
        if refs:
            s.image_refs = refs

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
        images=images,
        map=bundle_map,
        claims=[],
        signals=signals,
        contradictions=contradictions,
        sources=sources,
        confidence=confidence,
        timeline=bundle_timeline,
    )
