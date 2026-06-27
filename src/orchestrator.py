"""Orchestrator -- mode-aware analysis pipeline coordinator (v3.1.0)."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import shutil
import time
from typing import Any, Callable, Coroutine, Optional

from src.archetypes.registry import get_archetype, list_archetypes, select_archetype
from src.config import Config
from src.lens_policy import select_lenses, select_theme
from src.lenses.registry import get_lens, list_lenses
from src.models import (
    AnalysisRequest, AnalysisStrategy, AnalyticalFinding, Claim, ConfidenceProfile,
    Evidence, FullAnalysisResult, JudgmentVerdict, ParentContext,
)
from src.telemetry import RunTelemetry
from src.token_budget import (
    AnalysisMode,
    TokenBudget,
    resolve_mode,
    resolve_report_format,
    strip_reportage_trigger,
)
from src.visual_builder import needs_advanced_visuals
from src.watchlist import WatchlistRegistry, convert_watch_signals
from src.agents.context_analyst import ContextAnalyst
from src.agents.report_synthesizer import ReportSynthesizer
from src.agents.narrative_composer import NarrativeComposer
from src.visual_builder import build_chart_catalog

logger = logging.getLogger(__name__)

VERSION = "v8.2.10"


# v3.4.1 — 봇 프로세스 시작 시점에 git 상태를 캡처해 두 곳에서 표시한다:
#   ① 시작 로그 (tmux/journal 으로 운영자가 즉시 확인)
#   ② /status 명령 응답 (텔레그램에서 어떤 commit 이 돌고 있는지 명시)
# pull 만 하고 재기동을 안 했다면 BUILD_INFO 는 "이미 실행 중인" 코드의 commit 을 가리킨다 —
# 그래야 "v3.4.0 머지했는데 왜 v3.3.0 이 뜨지?" 류 디버깅이 즉시 풀린다.
def _capture_build_info() -> dict:
    """Capture git branch + commit at process start. Static — does not refresh post-start."""
    import subprocess as _sp
    info = {"branch": "?", "commit": "?", "commit_date": "?", "dirty": False}
    try:
        info["branch"] = _sp.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=_sp.DEVNULL, text=True, timeout=2,
        ).strip()
        info["commit"] = _sp.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            stderr=_sp.DEVNULL, text=True, timeout=2,
        ).strip()
        info["commit_date"] = _sp.check_output(
            ["git", "log", "-1", "--format=%cd", "--date=format:%Y-%m-%d %H:%M"],
            stderr=_sp.DEVNULL, text=True, timeout=2,
        ).strip()
        info["dirty"] = bool(_sp.check_output(
            ["git", "status", "--porcelain"],
            stderr=_sp.DEVNULL, text=True, timeout=2,
        ).strip())
    except (OSError, _sp.SubprocessError, _sp.TimeoutExpired):
        # git 미설치 / repo 밖 / 권한 없음 — 모두 "?" 로 graceful degrade.
        pass
    return info


BUILD_INFO = _capture_build_info()

# v3.1.0: legacy keywords map → fast mode (quick mode 와 같은 의미).
QUICK_MODE_KEYWORDS = {"짧게", "간략히", "간략하게", "빠르게", "요약", "간단히", "간단하게"}

StatusCallback = Optional[Callable[[str], Coroutine[Any, Any, None]]]


# v5.2.0 — Market data period 선택 헬퍼 (mode-aware).
# 사건 / 데일리 브리핑 / 역사적 분석 보고서별로 시계열 fetch 기간 분기.
_HISTORICAL_KEYWORDS = (
    "10년 만에", "지난 10년", "20년", "5년 만에",
    "imf", "외환위기", "글로벌 금융위기", "리먼", "코로나 이전",
    "역사적 회고", "장기 추이", "decade",
)
_DAILY_BRIEFING_KEYWORDS = (
    "간밤", "어제", "오늘 새벽", "daily briefing", "일일 브리핑",
    "야간", "장 마감", "전일 마감",
)


# v5.2.0+ — composer 가 available_time_series 무시했을 때 시계열 차트 자동 보충.
# composer prompt 강화는 LLM 지시 준수에 의존 — 결정적 hook 이 안전망.
_TS_CHART_TYPES = {"line", "candle", "area"}

# v5.2.2+ — source 표기 매핑 (사용자 노출용)
_SOURCE_DISPLAY = {
    "YAHOO": "Yahoo Finance",
    "KRX": "KRX",
    "FRED": "FRED",
    "ECOS": "한국은행 ECOS",
}


def _count_existing_ts_charts(composed) -> int:
    """composer (또는 fallback) 가 박은 *풀 카드* 시계열 차트 개수.

    v5.2.13 — strip row (``role='compact'``) 는 제외. strip 의 ``type`` 도 ``line``
    이지만 sparkline 만 그리는 다른 시각 역할 — 풀 카드 보장 (fallback 의
    강제 emit 조건) 판정에 strip 을 분자로 세면 v5.2.5 회귀가 영구화된다.
    """
    n = 0
    for sec in composed.sections or []:
        for ch in (sec.charts or []):
            if not isinstance(ch, dict):
                continue
            if ch.get("role") == "compact":
                continue
            if (ch.get("type") or "").lower() in _TS_CHART_TYPES:
                n += 1
    return n


def _composer_instruments(composed) -> set[str]:
    """composer 가 박은 시계열 차트의 instrument 이름 집합 (title / instrument 필드 기반).

    v5.2.5 — compact strip row (role='compact') 의 ``instrument`` 필드도 함께
    집계. _ensure_market_strip 이 먼저 박은 instrument 는 _ensure_time_series_chart
    가 풀 차트로 중복 emit 안 함.
    """
    out: set[str] = set()
    for sec in composed.sections or []:
        for ch in (sec.charts or []):
            if not isinstance(ch, dict):
                continue
            # compact strip row — instrument 필드 직접 사용
            if ch.get("role") == "compact":
                inst = ch.get("instrument")
                if inst:
                    out.add(inst)
                    continue
            if (ch.get("type") or "").lower() not in _TS_CHART_TYPES:
                continue
            title = (ch.get("title") or "")
            # 가장 흔한 instrument 이름과 매치 — exact match 우선
            for inst in ("코스피", "코스닥", "삼성전자", "SK하이닉스", "달러인덱스",
                         "미국채 1Y", "미국채 10Y", "WTI", "금", "국고채 10Y", "원/달러"):
                if inst in title:
                    out.add(inst)
                    break
    return out


# v5.2.3 — instrument-aware event filtering 키 워드 셋.
# 동일 timeline 을 모든 차트에 균등 부착하던 v5.2.2 회귀의 안전망. 차트마다
# instrument 와 관련 있는 이벤트만 골라 부착 — 사용자 노출 footnote/배지가
# 차트별로 다르게 보이도록.
_INDEX_INSTRUMENTS = ("코스피", "코스닥", "다우", "나스닥", "S&P 500", "닛케이", "항생")

# 사건 텍스트가 알려진 자산 중 하나라도 명시했는지 판정용. 여기 안 잡히는
# 일반 시장 이벤트는 모든 개별 자산 차트가 흡수 (정보 손실 방지).
_KNOWN_INSTRUMENTS_LC = tuple(s.lower() for s in (
    "코스피", "코스닥",
    "삼성전자", "SK하이닉스", "TSMC", "엔비디아", "마이크론",
    "달러인덱스", "원/달러", "엔/달러", "유로/달러", "위안/달러",
    "WTI", "브렌트유", "두바이", "천연가스",
    "금", "은", "구리", "철광석",
    "미국채 1Y", "미국채 2Y", "미국채 10Y", "미국채 30Y",
    "국고채 3Y", "국고채 10Y",
    "비트코인", "이더리움",
))


def _event_mentions_any_instrument(text_lower: str) -> bool:
    """Event 텍스트가 알려진 instrument 중 하나라도 언급하는지."""
    return any(inst in text_lower for inst in _KNOWN_INSTRUMENTS_LC)


def _event_relevant_to(text: str, instrument: str) -> bool:
    """v5.2.3 — 이 이벤트가 이 차트의 instrument 에 관련 있는지.

    규칙:
    1) 자기 instrument 이름이 명시된 이벤트 → 부착.
    2) 지수/벤치마크 차트 (코스피·코스닥 등) → 모든 이벤트 흡수 (시장 풍향
       자체가 지수 차트의 컨텍스트).
    3) 개별 자산 차트 → 어떤 instrument 도 명시 안 된 '일반 시장 이벤트' 도
       흡수 (예: '외국인 5.3조원 순매도' 는 종목 mention 없지만 종목 영향).
    4) 그 외 (다른 instrument 가 명시된 이벤트) → 스킵.
    """
    if not text or not instrument:
        return False
    text_l = text.lower()
    inst_l = instrument.lower()
    if inst_l in text_l:
        return True
    if instrument in _INDEX_INSTRUMENTS:
        return True
    return not _event_mentions_any_instrument(text_l)


def _attach_event_markers(
    chart_data: list, timeline: list, ctype: str, instrument: str = "",
) -> list:
    """timeline 의 date 와 매치되는 row 에 ``event`` 필드 부착.

    charts.js 가 ``event`` 필드 보고 번호 배지 + footnote 자동 렌더.
    date 매핑: 'YYYY-MM-DD' 정확 일치만 인정.

    v5.2.3 — ``instrument`` 매개변수 추가. 차트의 instrument 와 관련 있는
    이벤트만 통과시켜, 같은 timeline 을 모든 차트에 균등 부착하던 v5.2.2
    회귀 (사용자 노출 결함: KOSPI/삼성/하이닉스 차트가 동일 1-5 번호 + 동일
    풋노트) 를 해결. instrument="" 면 종전처럼 모든 이벤트 통과.
    """
    if not timeline:
        return chart_data
    idx: dict[str, str] = {}
    for ev in timeline:
        if not isinstance(ev, dict):
            continue
        date_str = (ev.get("date") or "").strip()
        if len(date_str) < 10:
            continue
        d_iso = date_str[:10]
        if not (d_iso[:4].isdigit() and d_iso[4] == "-" and d_iso[7] == "-"):
            continue
        text = (ev.get("event") or "").strip()
        if not text:
            continue
        if instrument and not _event_relevant_to(text, instrument):
            continue
        idx[d_iso] = text[:60]
    if not idx:
        return chart_data
    out = []
    for row in chart_data:
        if not isinstance(row, dict):
            out.append(row); continue
        d = (row.get("date") if ctype == "candle" else row.get("x")) or ""
        d = str(d)[:10]
        if d in idx:
            out.append({**row, "event": idx[d]})
        else:
            out.append(row)
    return out


def _format_ts_title(name: str, source: str, code: str) -> str:
    """instrument 별 사용자 노출 title."""
    if source == "YAHOO" and name in ("코스피", "코스닥"):
        return f"{name} 종합지수"
    if source == "KRX" and code and code.isdigit() and len(code) == 6:
        return f"{name} ({code})"
    return name


def _format_ts_subtitle(data: list, start_date: str, end_date: str, ctype: str) -> str:
    """변화율 % + 기간."""
    if not data or len(data) < 2:
        return f"{start_date} ~ {end_date}".strip(" ~")
    def _close(d):
        return d.get("close") if ctype == "candle" else d.get("y", d.get("close"))
    first = _close(data[0]) or 0
    last = _close(data[-1]) or 0
    if first <= 0:
        return f"{start_date} ~ {end_date}"
    pct = (last / first - 1) * 100
    sign = "+" if pct >= 0 else ""
    period = f"{start_date} ~ {end_date}" if (start_date and end_date) else ""
    fmt_n = (lambda v: f"{v:,.0f}") if abs(last) >= 1000 else (lambda v: f"{v:.2f}")
    parts = [p for p in (period, f"{sign}{pct:.2f}% ({fmt_n(first)} → {fmt_n(last)})") if p]
    return " · ".join(parts)


def _format_ts_source(series: dict) -> str:
    """source 표기 — '한국은행 ECOS / 2026-04-15 ~ 2026-05-15 · 일간'."""
    src = _SOURCE_DISPLAY.get(series.get("source", ""), series.get("source", "?"))
    period = f"{series.get('start_date', '')} ~ {series.get('end_date', '')}".strip(" ~")
    parts = [src, period, "일간"]
    return " / ".join(p for p in parts if p)


def _format_ts_takeaway(
    data: list, ctype: str, context, *, instrument: str = "",
) -> str:
    """차트별 데이터 기반 takeaway — 결정적, 절단 불가, 차트마다 다름.

    v5.2.7 — 이전 구현은 ``context.summary.split(".")[0]`` 을 1순위로 두어
    두 회귀 동시 유발: ① 모든 차트가 동일 문장 (summary 는 보고서 전역 1개),
    ② 소수점에서 문장 절단 ("...5월 15일 4.52%로" → "...5월 15일 4"). 두
    경로 모두 제거. summary 인자 (``context``) 는 시그니처 호환용으로 남기되
    참조 안 함.

    공식: ``{instrument} 가 기간 중 {hi}~{lo}, 마지막 {last}({sign}{pct}%).
    변동폭 {range_pct}%.`` — subtitle 의 시점 변화율과 겹치지 않게 *범위* 와
    *현재 위치* 에 초점.
    """
    if not data:
        return ""
    def _close(d):
        return d.get("close") if ctype == "candle" else d.get("y", d.get("close"))
    closes = [c for c in (_close(d) for d in data) if isinstance(c, (int, float)) and c > 0]
    if len(closes) < 2:
        return ""
    hi, lo = max(closes), min(closes)
    last = closes[-1]
    first = closes[0]
    range_pct = (hi - lo) / lo * 100
    pct_change = (last / first - 1) * 100 if first > 0 else 0.0
    sign = "+" if pct_change >= 0 else ""
    direction = "상승" if pct_change > 0.1 else ("하락" if pct_change < -0.1 else "횡보")
    fmt_n = (lambda v: f"{v:,.0f}") if hi >= 1000 else (lambda v: f"{v:.2f}")
    name = (instrument or "").strip() or "값"
    return (
        f"{name} 기간 중 {fmt_n(lo)}~{fmt_n(hi)} 사이 {direction} — "
        f"마지막 {fmt_n(last)} ({sign}{pct_change:.2f}%), 변동폭 {range_pct:.1f}%"
    )


def _is_finite_num(v) -> bool:
    """NaN/inf/None/비숫자 차단. 시장 데이터 무결성 가드의 공용 술어."""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _sanitize_market_nan(time_series: list) -> int:
    """context.time_series 의 각 series.data 에서 비유한값(NaN/inf) 행을 제거 (in-place).

    CHART-AP-29 — Yahoo/pykrx 의 미완성 마지막 봉이나 결측이 NaN 으로 흘러들면
    line/candle 차트가 빈 프레임이 되고 등락률·감시 스트립이 "nan%" 로 노출된다
    (2026-06 코스피 회귀: 본문 takeaway 는 9,064 인데 차트 마지막은 nan). 모든
    소스가 합류하는 단일 길목(fetch 직후)에서 결정적으로 비유한 행을 버린다.
    candle 은 close 가 유한해야 유지, 그 외(line/area)는 close 유한이면 유지.
    반환값 = 제거한 행 수.
    """
    removed = 0
    for s in time_series or []:
        if not isinstance(s, dict):
            continue
        data = s.get("data")
        if not isinstance(data, list):
            continue
        kept: list = []
        for d in data:
            if not isinstance(d, dict):
                continue
            c = d.get("close")
            if not _is_finite_num(c) or c <= 0:
                removed += 1
                continue
            kept.append(d)
        if len(kept) != len(data):
            s["data"] = kept
    return removed


def _build_ts_chart(series: dict, context) -> dict:
    """단일 series → mockup 수준 chart dict.

    mockup 수준 = title + subtitle + source + takeaway + event markers + 적절한 data shape.
    """
    raw_data = list(series.get("data") or [])
    ctype = (series.get("chart_type") or "line").lower()
    if ctype not in _TS_CHART_TYPES:
        ctype = "line"

    # data shape 변환
    if ctype == "candle":
        chart_data = [
            {
                "date": d.get("date"),
                "open": d.get("open"),
                "high": d.get("high"),
                "low": d.get("low"),
                "close": d.get("close"),
                **({"volume": d.get("volume")} if d.get("volume") else {}),
            }
            for d in raw_data
        ]
    else:
        chart_data = [{"x": d.get("date"), "y": d.get("close")} for d in raw_data]

    # 이벤트 마커 자동 부착 (charts.js 가 번호 배지 + footnote 로 렌더)
    # v5.2.3 — instrument 를 넘겨 차트별 distinct footnote 보장.
    timeline = list(getattr(context, "timeline", None) or [])
    name = series.get("instrument", "시계열")
    chart_data = _attach_event_markers(chart_data, timeline, ctype, instrument=name)
    return {
        "type": ctype,
        "title": _format_ts_title(name, series.get("source", ""), series.get("code", "")),
        "subtitle": _format_ts_subtitle(chart_data, series.get("start_date", ""),
                                         series.get("end_date", ""), ctype),
        "data": chart_data,
        "source": _format_ts_source(series),
        "takeaway": _format_ts_takeaway(chart_data, ctype, context, instrument=name),
    }


def _compact_period_label(start_date: str, end_date: str, n_points: int) -> str:
    """compact strip 의 ``period_label`` — 기간을 짧은 라벨 ("1W"/"3M"/"1Y") 로.

    start_date / end_date 가 ISO (YYYY-MM-DD) 면 일수 차이로 분류. 파싱 실패 또는
    빈 문자열이면 ``n_points`` (data 포인트 수) 로 fallback — 일간 데이터 가정.
    """
    from datetime import date as _date

    days: int | None = None
    try:
        if start_date and end_date:
            s = _date.fromisoformat(str(start_date)[:10])
            e = _date.fromisoformat(str(end_date)[:10])
            days = (e - s).days
    except (ValueError, TypeError):
        days = None
    if days is None or days <= 0:
        if n_points >= 2:
            days = n_points - 1  # 1일 데이터 1포인트 가정
        else:
            return ""
    if days <= 1:
        return "24H"
    if days <= 3:
        return f"{days}D"
    if days <= 10:
        return "1W"
    if days <= 21:
        return "2W"
    if days <= 45:
        return "1M"
    if days <= 100:
        return "3M"
    if days <= 200:
        return "6M"
    if days <= 400:
        return "1Y"
    if days <= 800:
        return "2Y"
    years = max(2, round(days / 365))
    return f"{years}Y"


def _format_compact_value(last_close: float, instrument: str) -> str:
    """compact strip 의 ``last_value_formatted`` — 값 자릿수/통화 기호 자동.

    - 금리·이율 (instrument 에 'Y' / '금리' / '%' 포함) → "4.52%"
    - 환율 / 지수 (1000 미만) → "105.58"
    - 큰 통화 단위 (BTC 등 5자리↑) → "$72,273"
    - 한국 종목 (코스피·코스닥·삼성전자 등) → "{:,.0f}"
    """
    name = (instrument or "")
    if not isinstance(last_close, (int, float)) or last_close != last_close:
        return ""
    is_rate = ("Y" in name and "유가" not in name) or "금리" in name or "%" in name
    if is_rate:
        return f"{last_close:.2f}%"
    if "비트코인" in name or "BTC" in name.upper():
        return f"${last_close:,.0f}"
    if abs(last_close) >= 1000:
        return f"{last_close:,.0f}"
    return f"{last_close:.2f}"


def _build_compact_strip_row(series: dict) -> dict | None:
    """단일 time_series → compact strip row payload (role='compact').

    payload schema (freeform_essay 의 `.compact-row` 가 읽는 필드):
      - instrument, last_value_formatted, change_day_pct, change_day_pct_formatted
      - data: [{x, y}, ...]  (sparkline 그릴 series)
      - role: 'compact'      (template 분기 키)
      - type: 'line'         (model validator 의 type guard 통과용)
      - title, subtitle, source, takeaway — strip 자체엔 안 보이지만 payload
        에 보존 (downstream patch / debug 용).

    ``data`` 가 2 점 미만이면 ``None`` 반환 — strip row 자체를 emit 하지 않음.
    """
    # CHART-AP-29 — 비유한값(NaN/inf) 봉은 sparkline·등락률 양쪽에서 배제.
    raw = [d for d in (series.get("data") or []) if _is_finite_num(d.get("close"))]
    closes = [d.get("close") for d in raw]
    if len(closes) < 2:
        return None
    last_close = closes[-1]
    first_close = closes[0]
    name = series.get("instrument") or series.get("name") or "시계열"
    chart_data = [{"x": d.get("date"), "y": d.get("close")} for d in raw]
    # change_day_pct: 마지막 vs 직전 종가. carry-day 부재 시 첫 vs 끝 fallback.
    if len(closes) >= 2:
        change_day_pct = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] else 0.0
    else:
        change_day_pct = 0.0
    sign = "+" if change_day_pct >= 0 else ""
    period_pct = (last_close / first_close - 1) * 100 if first_close else 0.0
    period_sign = "+" if period_pct >= 0 else ""
    start = series.get("start_date", "")
    end = series.get("end_date", "")
    period = f"{start} ~ {end}".strip(" ~")
    fmt_n = (lambda v: f"{v:,.0f}") if abs(last_close) >= 1000 else (lambda v: f"{v:.2f}")
    subtitle_parts = [p for p in (period, f"{period_sign}{period_pct:.2f}% ({fmt_n(first_close)} → {fmt_n(last_close)})") if p]
    src = _SOURCE_DISPLAY.get(series.get("source", ""), series.get("source", "?"))
    source_text = " / ".join(p for p in (src, period, "일간") if p)
    return {
        "type": "line",
        "role": "compact",
        "instrument": name,
        "title": name,
        "subtitle": " · ".join(subtitle_parts),
        "last_value_formatted": _format_compact_value(last_close, name),
        "change_day_pct": round(change_day_pct, 2),
        "change_day_pct_formatted": f"{sign}{change_day_pct:.2f}%",
        "period_label": _compact_period_label(start, end, len(chart_data)),
        "data": chart_data,
        "source": source_text,
        "takeaway": "",
    }


def _ensure_market_strip(composed, context) -> None:
    """v5.2.5 — 시계열 instrument 3개↑ 면 sections[0] 앞에 compact strip 자동 emit.

    설계:
    - composer 가 박은 풀 차트는 *그대로 보존* — strip 은 *추가 컨텍스트* (별도 row).
    - 시계열 데이터가 있는 instrument 전체 (data 보유) 를 strip row 로 변환.
    - 3개 미만이면 emit 안 함 (1~2개는 풀 차트 1개로 충분, strip 시각 비용만 큼).
    - 이미 sections[0].charts 에 role='compact' 박혀 있으면 skip (idempotent).

    Args:
        composed: ComposedReport (mutated in place)
        context: ContextAnalysis (.time_series 읽음)
    """
    if composed is None or not composed.sections:
        return
    time_series = list(getattr(context, "time_series", None) or [])
    candidates = [s for s in time_series if isinstance(s, dict) and s.get("data")]
    if len(candidates) < 3:
        return
    target = composed.sections[0]
    if target.charts is None:
        target.charts = []
    if any(isinstance(c, dict) and c.get("role") == "compact" for c in target.charts):
        return  # 이미 strip 박혀 있음
    rows = [_build_compact_strip_row(s) for s in candidates]
    rows = [r for r in rows if r is not None]
    if not rows:
        return
    target.charts = rows + list(target.charts)
    import logging
    names = ", ".join(r.get("instrument", "?") for r in rows)
    logging.getLogger(__name__).info(
        "[orchestrator] _ensure_market_strip: +%d compact rows (%s) → sections[0].charts",
        len(rows), names,
    )


def _topic_priority_key(series: dict, title_text: str, summary_text: str):
    """v5.6.9 — 주제 우선 정렬 키. 보고서 주인공 종목의 차트가 먼저 뜨게 한다.
    'NVIDIA 보고서엔 NVIDIA 차트' 보장.

    3단계 우선순위 (작을수록 앞):
      0 — event_name(제목) 에 등장. 제목은 진짜 주인공만 담김.
      1 — summary(본문 요약) 에만 등장.
      2 — 어디에도 없음 (보조 지수/매크로).
    같은 그룹 안에선 data 많은 순. sorted() 에 그대로 사용.
    """
    inst = str(series.get("instrument") or "")
    if inst and inst in title_text:
        rank = 0
    elif inst and inst in summary_text:
        rank = 1
    else:
        rank = 2
    return (rank, -len(series.get("data") or []))


def _ensure_time_series_chart(composed, context) -> None:
    """v5.2.2 — composer 가 시계열 차트 누락 시 mockup 수준으로 자동 보충.

    설계:
    - context.time_series 중 ``data`` 가 있는 series 만 후보
    - composer 가 이미 박은 instrument 는 *skip* (중복 회피)
    - 누락된 series 마다 mockup 수준 차트 (title / subtitle / source /
      takeaway / 이벤트 마커 자동) 를 생성
    - 차트는 ``sections[0].charts`` 앞쪽에 우선 삽입 (data 많은 순)

    Args:
        composed: ``ComposedReport`` (mutated in place)
        context: ``ContextAnalysis`` (time_series / timeline / summary 접근)
    """
    if composed is None or not composed.sections:
        return
    time_series = list(getattr(context, "time_series", None) or [])
    if not time_series:
        return

    candidates = [
        s for s in time_series
        if isinstance(s, dict) and s.get("data")
    ]
    if not candidates:
        return

    # composer 가 이미 박은 instrument 제외 (중복 회피)
    composer_names = _composer_instruments(composed)

    # v5.2.13 — 풀 카드 보장 (사용자 사례: '컴팩트 스트립만 계속 나옴').
    # composer 가 SYSTEM_PROMPT 의 "시계열 차트 1개 이상 emit 강제 규칙" 을
    # 어기고 풀 카드를 0 개 emit 했고, _ensure_market_strip 이 3+ instrument
    # 를 compact row 로 박은 경우, v5.2.5 의 _composer_instruments (strip 도
    # covered 로 인정) 가 dedupe 집합으로 *모든 instrument* 를 반환 → fallback
    # 이 no-op → 사용자가 strip 만 본다. _drop_invalid_charts validator 가
    # composer 의 candle/line/area 를 silent drop 한 케이스도 동일 결과.
    #
    # 안전망: composer 의 *유효 풀 카드* (role!='compact' + type in TS) 가
    # 0 이면, 가장 정보 풍부한 series 1개를 strip dedupe 우회로 풀 카드 강제.
    # 1개만 강제 — 모든 instrument 풀 카드는 strip 의 at-a-glance 역할과
    # 중복돼 시각 혼잡 (사용자 사례 v5.2.5 의 origin).
    # v5.6.9 — 주제 우선. 제목(event_name) 등장 종목 > 요약(summary) 등장 > 그 외.
    title_text = getattr(context, "event_name", "") or ""
    summary_text = getattr(context, "summary", "") or ""
    forced_inst: str | None = None
    if _count_existing_ts_charts(composed) == 0:
        primary_pool = sorted(
            candidates, key=lambda s: _topic_priority_key(s, title_text, summary_text)
        )
        primary = primary_pool[0]
        forced_inst = primary.get("instrument")
        target = composed.sections[0]
        if target.charts is None:
            target.charts = []
        target.charts = [_build_ts_chart(primary, context)] + list(target.charts)
        import logging
        logging.getLogger(__name__).info(
            "[orchestrator] _ensure_time_series_chart: 풀 카드 0 → primary '%s' "
            "(%d points) 강제 추가 (strip dedupe 우회)",
            forced_inst, len(primary.get("data") or []),
        )
        composer_names = composer_names | {forced_inst}

    to_add = [s for s in candidates if s.get("instrument") not in composer_names]
    if not to_add:
        return  # composer (또는 forced primary) 가 다 박았으면 no-op

    # v5.6.9 — 주제 우선, 그 안에서 data 많은 순 (가장 정보 풍부한 series 가 첫 섹션)
    to_add.sort(key=lambda s: _topic_priority_key(s, title_text, summary_text))

    # 첫 섹션 앞쪽에 모두 삽입 (사용자: '적극적이어도 OK, 단 mockup 품질')
    target = composed.sections[0]
    if target.charts is None:
        target.charts = []
    new_charts = [_build_ts_chart(s, context) for s in to_add]
    target.charts = new_charts + list(target.charts)

    import logging
    names = ", ".join(s.get("instrument", "?") for s in to_add)
    logging.getLogger(__name__).info(
        "[orchestrator] _ensure_time_series_chart: +%d 차트 (%s) → sections[0].charts (mockup-quality)",
        len(to_add), names,
    )


def _strip_inline_md(text: str) -> str:
    """마크다운 강조 + em/en dash 제거 (broadcast 합성용 평문화, v5.6.7).

    composer 의 ``_sanitize_symbols`` 와 동일 규칙 — AI 가 인지되는 기호 박멸
    (사용자 최우선 규칙). 이 경로는 composer 가 완전 실패해 context 기반으로
    합성할 때의 백스톱이다.
    """
    if not text:
        return ""
    out = text.replace("**", "").replace("*", "").replace("`", "")
    out = re.sub(r"(?<=\s)_+|_+(?=\s)", "", out)
    out = re.sub(r"^_+|_+$", "", out)
    out = re.sub(r"(?<=\d)\s*[—–―]\s*(?=\d)", "~", out)
    out = re.sub(r"\s+[—–―]\s+", ", ", out)
    out = re.sub(r"[—–―]", " ", out)
    out = re.sub(r"\s+,", ",", out)
    return " ".join(out.split())


def _densify_ts_charts(composed, context) -> None:
    """v7.0.2 (CHART-AP-31, 사용자 catch) — composer 시계열 차트의 *일별 밀도* 보장.

    composer LLM 이 차트 데이터를 손으로 emit 하면서 토큰 절약으로 일별 series
    (3M ≈ 60거래일) 를 듬성하게 추려 쓰는 회귀 — 지수/가격 차트가 8~12 포인트로
    납작해져 "실제 가격의 움직임" 이 사라진다. 본 패스는 0-LLM 으로:

    - 차트 title 에서 instrument 매칭 → context.time_series 의 실 데이터와 대조
    - 차트 *자신의 날짜 창* (composer 가 의도적으로 사건 주간만 확대했을 수 있음)
      안에 실 데이터 행이 더 많으면 → 그 창의 *전체 일별 행* 으로 데이터 교체
    - 날짜 창을 못 읽으면 (단축 표기 등) → 전체 series 로 교체 (일별 종가 기준 원칙)
    - composer 가 단 이벤트 마커 (row.event) 는 날짜(suffix) 매칭으로 보존

    type/제목/해석은 composer 권한 그대로 — 데이터 행만 실측으로 치환.
    """
    if composed is None or not getattr(composed, "sections", None):
        return
    series_list = [
        s for s in (getattr(context, "time_series", None) or [])
        if isinstance(s, dict) and s.get("instrument") and s.get("data")
    ]
    if not series_list:
        return
    import logging
    import re as _re
    _iso = _re.compile(r"^\d{4}-\d{2}-\d{2}")

    def _row_key(row: dict) -> str:
        return str(row.get("date") or row.get("x") or "")

    for sec in composed.sections:
        for ch in (sec.charts or []):
            if not isinstance(ch, dict) or ch.get("role") == "compact":
                continue
            ctype = (ch.get("type") or "").lower()
            if ctype not in _TS_CHART_TYPES:
                continue
            title = ch.get("title") or ""
            series = next((s for s in series_list if s["instrument"] in title), None)
            if series is None:
                continue
            old = ch.get("data")
            if not isinstance(old, list) or len(old) < 2:
                continue
            old_keys = [k for k in (_row_key(r) for r in old if isinstance(r, dict)) if k]
            if not old_keys:
                continue
            all_rows = [
                d for d in series["data"]
                if isinstance(d, dict) and d.get("date") and d.get("close") is not None
            ]
            if all(_iso.match(k) for k in old_keys):
                lo, hi = min(old_keys), max(old_keys)
                rows = [d for d in all_rows if lo <= str(d["date"]) <= hi]
            else:
                rows = all_rows  # 날짜 창 해석 불가 → 전체 일별 series (원칙 우선)
            if len(rows) <= len(old):
                continue  # 이미 일별 밀도 (또는 series 가 더 빈약)
            # 이벤트 마커 보존 — composer 가 쓴 날짜 표기(단축 포함)와 suffix 매칭.
            events: dict[str, str] = {}
            for r in old:
                if isinstance(r, dict) and r.get("event"):
                    k = _row_key(r)
                    if k:
                        events[k] = r["event"]
            if ctype == "candle":
                new_data = [
                    {
                        "date": d.get("date"),
                        "open": d.get("open"),
                        "high": d.get("high"),
                        "low": d.get("low"),
                        "close": d.get("close"),
                        **({"volume": d.get("volume")} if d.get("volume") else {}),
                    }
                    for d in rows
                ]
            else:
                new_data = [{"x": d["date"], "y": d["close"]} for d in rows]
            for nd in new_data:
                full = str(nd.get("date") or nd.get("x"))
                for ek, ev in events.items():
                    if full == ek or full.endswith(ek):
                        nd["event"] = ev
                        break
            ch["data"] = new_data
            logging.getLogger(__name__).info(
                "[orchestrator] _densify_ts_charts: '%s' %d → %d points (일별 밀도 교체)",
                title, len(old), len(new_data),
            )


def _reconcile_visual_references(composed) -> int:
    """v8.2.9 — 본문이 '(아래 관계도/지도/그래프)' 로 *약속한* 시각물이 실제로 없으면
    그 깨진 약속(dangling reference)을 본문에서 지운다 (사용자 catch 2026-06-27).

    사용자 요구: 문장에 '아래 관계도/지도' 를 박아놨으면 그 시각물이 *반드시 보여야*
    한다. 1차 방어는 composer 프롬프트(지시어를 쓰면 시각물 emit 강제)지만, LLM 이
    지시어만 쓰고 시각물을 빠뜨릴 때를 위한 *결정적 안전망*. 없는 시각물을 지어낼 수는
    없으므로(관계도 데이터 부재), 최소한 *깨진 약속 문구를 제거* 해 본문이 존재하지
    않는 그림을 가리키지 않게 한다.

    판정:
    - 관계도/관계망 → 그 섹션에 stakeholder_map 또는 network 차트가 있어야 충족.
    - 그래프/도표 → 그 섹션에 차트가 하나라도 있어야 충족.
    - 지도 → 보고서에 embedded_map 이 있어야 충족(보고서 단위).
    충족 안 된 토큰의 괄호 지시어 '(…아래 관계도…)' 만 제거하고, 충족되면 보존한다.

    반환: 제거한 dangling reference 개수.
    """
    import re as _re
    if composed is None or not getattr(composed, "sections", None):
        return 0
    has_map = getattr(composed, "embedded_map", None) is not None
    removed = 0
    # (토큰들, 충족 차트 타입 집합 | None=아무 차트나)
    groups = [
        (("관계도", "관계망"), {"stakeholder_map", "network"}),
        (("그래프", "도표"), None),
    ]

    def _paren_re(token: str) -> "_re.Pattern":
        # 선행 공백 + 여는 괄호(반각/전각) … token … 닫는 괄호. 괄호 안만 매칭.
        return _re.compile(r"\s*[\(（][^)）]*" + _re.escape(token) + r"[^)）]*[\)）]")

    for sec in composed.sections:
        prose = getattr(sec, "prose", None)
        if not isinstance(prose, str) or not prose:
            continue
        chart_types = {
            (c.get("type") or "").lower()
            for c in (getattr(sec, "charts", None) or [])
            if isinstance(c, dict)
        }
        new_prose = prose
        for tokens, needed in groups:
            satisfied = bool(chart_types) if needed is None else bool(chart_types & needed)
            if satisfied:
                continue
            for tok in tokens:
                new_prose, n = _paren_re(tok).subn("", new_prose)
                removed += n
        if not has_map:
            new_prose, n = _paren_re("지도").subn("", new_prose)
            removed += n
        if new_prose != prose:
            new_prose = _re.sub(r"\s+([.?!,])", r"\1", new_prose)   # ' .' → '.'
            new_prose = _re.sub(r"[ \t]{2,}", " ", new_prose).strip()
            sec.prose = new_prose
    if removed:
        logging.getLogger(__name__).info(
            "[orchestrator] _reconcile_visual_references: dangling 시각물 참조 %d 개 제거", removed,
        )
    return removed


def _ensure_broadcast_summary(composed, context) -> None:
    """v5.6.6 — broadcast_summary(SNS 문구) 결정적 폴백.

    composer 가 성공해도 ``broadcast_summary`` 필드를 비워 emit 하거나(LLM 누락),
    timeout 부분 살림본이라 비어 있는 경우, 텔레그램/일일브리핑이 SNS 문구를 아예
    안 보내던 회귀 차단. deck + 앞 섹션 prose 로 친절한 평문을 합성한다.

    *결정적* hook — LLM 미호출. composer 가 채웠으면 (strip 후 비어있지 않으면)
    그대로 둔다. 합성 텍스트에 마크다운 강조 기호 미사용 (평문만).
    """
    if composed is None:
        return
    existing = (getattr(composed, "broadcast_summary", "") or "").strip()
    if existing:
        return  # composer 가 채웠음 — 존중

    parts: list[str] = []
    deck = _strip_inline_md(getattr(composed, "deck", "") or "")
    if deck:
        parts.append(deck)

    for sec in (getattr(composed, "sections", None) or []):
        prose = _strip_inline_md(getattr(sec, "prose", "") or "")
        if not prose:
            continue
        sentences = [s.strip() for s in prose.replace("\n", " ").split(". ") if s.strip()]
        snippet = ". ".join(sentences[:2])
        if snippet and snippet not in " ".join(parts):
            parts.append(snippet)
        if sum(len(p) for p in parts) >= 240:
            break

    body = "\n\n".join(parts).strip()
    if not body:
        body = _strip_inline_md(getattr(context, "summary", "") or "")
    if not body:
        return  # 정말 아무것도 없으면 첨부 안 함 (graceful, 기존 동작)

    if len(body) > 500:
        body = body[:500].rsplit(". ", 1)[0].rstrip()
        if body and not body.endswith((".", "다", "요", "음")):
            body += "."
    composed.broadcast_summary = body
    logger.info(
        "[orchestrator] _ensure_broadcast_summary: 합성 (%d자) — composer 누락 폴백",
        len(body),
    )


def _select_market_period(request, context) -> str:
    """Mode-aware period 선택.

    Returns:
        "1M" — daily briefing 키워드 매치
        "3Y" — historical keyword 매치
        "3M" — 디폴트 (사건 보고서, event-anchored ±30일)
    """
    pieces: list[str] = []
    if request is not None:
        pieces.append(getattr(request, "event_description", "") or "")
    if context is not None:
        pieces.append(getattr(context, "event_name", "") or "")
        pieces.append(getattr(context, "summary", "") or "")
        pieces.append(getattr(context, "category", "") or "")
    blob = " ".join(pieces).lower()
    if any(kw in blob for kw in _HISTORICAL_KEYWORDS):
        return "3Y"
    if any(kw in blob for kw in _DAILY_BRIEFING_KEYWORDS):
        return "1M"
    return "3M"


class Orchestrator:
    """Coordinates the 4-phase analysis pipeline."""

    def __init__(
        self,
        config: Config,
        watchlist_registry: "WatchlistRegistry | None" = None,
    ) -> None:
        self.config = config
        self.context_analyst = ContextAnalyst(config)
        # v5.2.9: 분석 페르소나 7개 모듈 (PlayerAnalyst/DynamicsAnalyst/ChainReactionAnalyst
        # /ScenarioArchitect/VisualAnalyst/QualityInspector/SynthesisJudge) 폐기.
        # v4.0.0 부터 호출되지 않던 dead code 정리.
        self.report_synthesizer = ReportSynthesizer(config)
        # v3.3.0 — freeform editorial pass (Opus 4.7). 본 시스템의 단일 본문 작성 agent.
        self.narrative_composer = NarrativeComposer(config)
        # V5 Phase 1A — ResearchDirector. opt-in flag 가 꺼진 환경에서도 인스턴스는
        # 만들어 두지만 호출은 Config.enable_research_director 가 True 일 때만.
        # 디폴트 OFF — v4.5.7 호출 경로 byte-equal 보존.
        from src.agents.research_director import ResearchDirector
        self.research_director = ResearchDirector(config)
        # V3 Step 5-B (v2.9.5) — Watchlist Registry. None 이면 watchlist 등록 스킵
        # (단위 테스트 / standalone orchestrator 인스턴스 시 안전).
        self.watchlist_registry = watchlist_registry
        # Counters for gate stats — reset per process. Logged at INFO at end of run.
        self._gate_stats = {
            "gate_1_attempts": 0, "gate_1_passes": 0, "gate_1_retries": 0, "gate_1_partial": 0,
            "gate_2_attempts": 0, "gate_2_passes": 0, "gate_2_retries": 0, "gate_2_partial": 0,
        }
        # v3.1.0: telemetry — 사건당 새 인스턴스를 ``run_analysis`` 가 만든다.
        self.telemetry: Optional[RunTelemetry] = None

    def _wire_telemetry(self) -> None:
        """현재 ``self.telemetry`` 를 모든 BaseAgent 후속에 전파."""
        self.context_analyst.telemetry = self.telemetry
        # narrative_composer 는 BaseAgent 가 아니지만 telemetry 속성 보유.
        self.narrative_composer.telemetry = self.telemetry

    @staticmethod
    def _progress_bar(step: int, total: int = 7) -> str:
        """Generate a text progress bar."""
        pct = int(step / total * 100)
        filled = int(step / total * 20)
        bar = "▓" * filled + "░" * (20 - filled)
        return f"{bar} {pct}%"

    @staticmethod
    def _empty_strategy_fallback() -> AnalysisStrategy:
        """LLM 호출 실패 또는 파싱 실패 시 사용할 최소 유효 AnalysisStrategy.

        Anti-pattern #3 (dict 회귀) 방지를 위해 빈 dict 가 아닌 빈 객체로 폴백.
        Pydantic validator 를 통과해야 하므로 core_questions/recommended_lenses 에
        한 항목씩 더미를 채운다.
        """
        return AnalysisStrategy(
            event_type="unknown",
            user_intent="what_happened",
            intent_confidence=0.5,
            core_questions=["사건의 핵심 사실을 파악한다"],
            recommended_lenses=["context"],
            evidence_plan=[],
            report_archetype="six_act_theater",
            section_plan=[],
            visualization_plan=[],
            theme="editorial_cream",
            legacy_directives={},
        )

    async def _generate_analysis_strategy(
        self,
        event_name: str,
        category: str,
        summary: str,
        mode: AnalysisMode = "standard",
    ) -> AnalysisStrategy:
        """Generate AnalysisStrategy based on the event context.

        v3.1.0: Strategy Planner 프롬프트를 대폭 축소.
        LLM 은 ``event_type`` / ``user_intent`` / ``intent_confidence`` /
        ``core_questions`` / ``complexity`` (선택) 만 출력.
        - archetype 선택은 ``select_archetype()`` 매트릭스가 최종 결정자.
        - theme 선택은 ``lens_policy.select_theme()`` (코드 규칙).
        - recommended_lenses 는 ``lens_policy.select_lenses()`` 가 mode 기반으로 결정.
        - per-agent directive (legacy_directives) 는 더 이상 LLM 으로 생성하지 않음.
        """
        intent_confidence_default = 0.5
        prompt = (
            "당신은 분석 전략 기획자. 아래 사건에 대해 4가지만 출력.\n\n"
            f"사건명: {event_name}\n"
            f"분류: {category}\n"
            f"요약: {summary[:400]}\n\n"
            "출력 항목:\n"
            "1) event_type — 한 단어 (financial/tech/accident/policy/geopolitical/industry/general 중 가장 가까운 것)\n"
            "2) user_intent — 7종 중 1: what_happened|why_happened|who_benefits|where_spreads|"
            "what_next|where_vulnerable|what_to_do\n"
            "3) intent_confidence — 0.0~1.0\n"
            "4) core_questions — 이 사건이 답해야 할 핵심 질문 1~4개\n\n"
            "JSON 만 출력 (다른 텍스트 금지):\n"
            '{"event_type":"...","user_intent":"...",'
            '"intent_confidence":0.0,"core_questions":["q1","q2"]}\n'
        )

        try:
            claude_bin = shutil.which("claude")
            if claude_bin is None:
                logger.warning("[orchestrator] claude CLI not found; using empty strategy")
                return self._empty_strategy_fallback()

            cmd = [
                claude_bin,
                "-p", prompt,
                "--output-format", "text",
                "--model", self.config.model_name_light,
                "--dangerously-skip-permissions",
            ]

            llm_start = time.time()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            llm_elapsed_ms = int((time.time() - llm_start) * 1000)

            if proc.returncode != 0:
                logger.warning("[orchestrator] Strategy generation failed; using empty strategy")
                return self._empty_strategy_fallback()

            raw = stdout.decode().strip()
            if self.telemetry is not None:
                self.telemetry.record_llm_call(
                    agent_name="strategy_planner",
                    input_chars=len(prompt),
                    output_chars=len(raw),
                    elapsed_ms=llm_elapsed_ms,
                )

            import re
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                logger.warning("[orchestrator] No JSON in strategy response; using empty strategy")
                return self._empty_strategy_fallback()

            raw_dict = json.loads(match.group())
            event_type = (raw_dict.get("event_type") or "general").strip().lower()
            user_intent = (raw_dict.get("user_intent") or "what_happened").strip()
            intent_confidence = float(
                raw_dict.get("intent_confidence", intent_confidence_default)
            )
            core_questions = list(raw_dict.get("core_questions") or [])
            core_questions = [q.strip() for q in core_questions if q and q.strip()]
            if not core_questions:
                core_questions = [f"{event_name} 의 핵심 사실을 파악한다"]

            # Lens 결정은 코드 규칙으로. 미사용 LLM 추천은 우선순위 보정에만 활용.
            recommended_lenses = select_lenses(
                event_type=event_type,
                user_intent=user_intent,
                mode=mode,
            )
            theme = select_theme(event_type)

            strategy = AnalysisStrategy(
                event_type=event_type,
                user_intent=user_intent,  # type: ignore[arg-type]
                intent_confidence=max(0.0, min(1.0, intent_confidence)),
                core_questions=core_questions[:5],
                recommended_lenses=recommended_lenses,
                report_archetype="six_act_theater",  # matrix 가 곧 덮어씀
                theme=theme,
                legacy_directives={},
            )

            logger.info(
                "[orchestrator] AnalysisStrategy generated for: %s\n"
                "  mode: %s\n"
                "  user_intent: %s (confidence=%.2f)\n"
                "  event_type: %s\n"
                "  core_questions: %s\n"
                "  recommended_lenses: %s (cap by mode)\n"
                "  theme: %s",
                event_name, mode,
                strategy.user_intent, strategy.intent_confidence,
                strategy.event_type,
                strategy.core_questions,
                strategy.recommended_lenses,
                strategy.theme,
            )
            return strategy

        except Exception as e:
            logger.warning(
                "[orchestrator] Strategy generation error: %s; using empty strategy", e
            )
            return self._empty_strategy_fallback()

    # ------------------------------------------------------------------
    # V3 Step 4 — Findings wrapper (v2 analyses → AnalyticalFinding list)
    # ------------------------------------------------------------------
    #
    # Wraps the existing ContextAnalysis / PlayerAnalysis / ... outputs into
    # AnalyticalFinding instances so Synthesis Judge + Gate 2 can operate on a
    # unified shape. ContextAnalysis.sources are converted to Evidence (real URLs).
    # Lenses without a real source get a single ``model_inference`` evidence with
    # quote_or_data marking the limitation explicitly.
    #
    # Step 5 (Lens Pool) will replace this wrapper — lens runners will produce
    # AnalyticalFinding directly.

    @staticmethod
    def _confidence_from_score(
        score: float, sources_count: int = 0
    ) -> ConfidenceProfile:
        """Convert legacy ``confidence_score: float`` (deprecated) to ConfidenceProfile."""
        # source_diversity: linear ramp on independent source count, capped at 5.
        sd = min(1.0, max(0.0, sources_count / 5.0))
        # data_freshness: web-search era assumption — moderate-to-high.
        df = 0.7
        # expert_consensus: legacy scalar maps here as a rough proxy.
        ec = max(0.0, min(1.0, score))
        return ConfidenceProfile(
            source_diversity=round(sd, 3),
            data_freshness=round(df, 3),
            expert_consensus=round(ec, 3),
        )

    @staticmethod
    def _make_evidence_pool(
        result: FullAnalysisResult,
    ) -> tuple[list[Evidence], list[str]]:
        """Build a shared Evidence pool from result.context.sources + lens-level fallback.

        Returns (evidence_list, evidence_ids). Always returns at least one Evidence
        so that Claim validators (evidence_ids min_length=1) never fail at wrap time.
        """
        evs: list[Evidence] = []
        if result.context and result.context.sources:
            # v5.1.1: fn_index 는 ``result.context.sources`` 순서와 1:1 매칭 — 보고서 하단
            # footnotes ol 의 ``id="fn-{n}"`` anchor 와 정합. evidence_table 블록이 ⁽n⁾
            # 마커로 같은 anchor 를 가리킴.
            for i, src in enumerate(result.context.sources, 1):
                # source can be a URL or free-text — store as source_url if it looks like URL.
                if src.startswith(("http://", "https://")):
                    ev = Evidence(
                        evidence_id=f"E-{i:03d}",
                        source_url=src,
                        quote_or_data=src,
                        reliability="secondary",
                        timestamp=result.context.date or "",
                        fn_index=i,
                    )
                else:
                    ev = Evidence(
                        evidence_id=f"E-{i:03d}",
                        source_url="",
                        quote_or_data=src[:200],
                        reliability="secondary",
                        timestamp=result.context.date or "",
                        fn_index=i,
                    )
                evs.append(ev)
        if not evs:
            # Fallback: one model_inference evidence so claims can still validate.
            evs.append(Evidence(
                evidence_id="E-INF-001",
                source_url="",
                quote_or_data="1차 출처 미수집 — 모델 추론 기반",
                reliability="model_inference",
                timestamp="",
            ))
        return evs, [e.evidence_id for e in evs]

    @staticmethod
    def _assign_question(
        strategy: AnalysisStrategy | None, lens_id: str, idx: int
    ) -> str:
        """Round-robin assignment of strategy.core_questions to findings.
        If strategy is None or core_questions empty, returns generic placeholder.
        """
        if strategy is None or not strategy.core_questions:
            return f"({lens_id} 가 답변하는 질문 미지정)"
        return strategy.core_questions[idx % len(strategy.core_questions)]

    def _wrap_findings(
        self, result: FullAnalysisResult
    ) -> list[AnalyticalFinding]:
        """Wrap available v2 analyses into AnalyticalFinding list."""
        if result.strategy is None:
            logger.warning("[orchestrator] _wrap_findings called with no strategy")
            return []
        evidence_pool, evidence_ids = self._make_evidence_pool(result)
        findings: list[AnalyticalFinding] = []
        idx = 0

        def _add(
            lens_id: str,
            statement: str,
            counter_hyp: str,
            score: float,
            claim_type: str = "inference",
        ) -> None:
            nonlocal idx
            statement = (statement or "").strip()
            if not statement:
                return
            try:
                claim = Claim(
                    claim_id=f"C-{lens_id[:6]}-{idx + 1:03d}",
                    statement=statement[:500],
                    claim_type=claim_type,  # type: ignore[arg-type]
                    evidence_ids=evidence_ids,
                )
            except Exception as e:
                # Anti-pattern #4 guard — must NOT silently downgrade by passing empty
                # evidence. If we can't build a valid claim, log and skip the finding.
                logger.warning(
                    "[orchestrator] Skipping finding for lens=%s; claim invalid: %s",
                    lens_id, e,
                )
                return
            findings.append(AnalyticalFinding(
                finding_id=f"F-{lens_id}-{idx + 1:03d}",
                lens_id=lens_id,
                answers_question=self._assign_question(result.strategy, lens_id, idx),
                main_claim=claim,
                evidence=evidence_pool,
                confidence=self._confidence_from_score(
                    score,
                    len(result.context.sources) if result.context else 0,
                ),
                counter_hypothesis=counter_hyp,
            ))
            idx += 1

        if result.context:
            _add(
                "context_analyst",
                result.context.summary,
                "",
                result.context.confidence_score,
                claim_type="fact",
            )
        if result.players:
            _add(
                "player_analyst",
                result.players.power_dynamics or result.players.summary,
                "",
                result.players.confidence_score,
                claim_type="inference",
            )
        if result.dynamics:
            _add(
                "dynamics_analyst",
                result.dynamics.key_insight or result.dynamics.summary,
                result.dynamics.counter_view or "",
                result.dynamics.confidence_score,
                claim_type="inference",
            )
        if result.chain_reaction:
            chain_summary = result.chain_reaction.worst_case
            if not chain_summary and result.chain_reaction.chain:
                chain_summary = " → ".join(
                    s.get("title", "") for s in result.chain_reaction.chain[:5]
                )
            _add(
                "chain_reaction_analyst",
                chain_summary,
                "",
                result.chain_reaction.confidence_score,
                claim_type="prediction",
            )
        if result.scenarios:
            sc_summary = (
                result.scenarios.base_case_summary or result.scenarios.summary
            )
            _add(
                "scenario_architect",
                sc_summary,
                "",
                result.scenarios.confidence_score,
                claim_type="prediction",
            )
        return findings

    # ------------------------------------------------------------------
    # V3 Step 5-A — Lens Pool execution
    # ------------------------------------------------------------------
    #
    # AnalysisStrategy.recommended_lenses 의 lens_id 들을 registry 로 resolve 해서 sequential
    # 실행 (Anti-pattern: 병렬 실행 금지 — 1GB VM 메모리 보호, FUT-001 까지 보류).
    # 사건당 최대 4개 (Anti-pattern #6 cap). 각 lens 가 산출한 finding 을 list 로 누적.

    LENS_CAP_PER_EVENT: int = 4

    async def _run_lenses(
        self,
        result: FullAnalysisResult,
        evidence: list[Evidence],
        status_callback: StatusCallback,
    ) -> list[AnalyticalFinding]:
        if result.strategy is None:
            return []
        requested = list(result.strategy.recommended_lenses or [])
        # 등록된 lens 만 통과 + cap 적용 (Anti-pattern #6).
        registered = set(list_lenses())
        valid = [lid for lid in requested if lid in registered]
        skipped = [lid for lid in requested if lid not in registered]
        if skipped:
            logger.warning(
                "[orchestrator] Skipping unregistered lens IDs: %s "
                "(registered: %s)", skipped, list(registered),
            )
        if len(valid) > self.LENS_CAP_PER_EVENT:
            logger.warning(
                "[orchestrator] Lens cap exceeded — strategy requested %d, "
                "truncating to %d (Anti-pattern #6)",
                len(valid), self.LENS_CAP_PER_EVENT,
            )
            valid = valid[: self.LENS_CAP_PER_EVENT]

        if not valid:
            logger.info("[orchestrator] No registered lenses to run")
            return []

        event_meta = {
            "event_name": result.context.event_name if result.context else "",
            "summary": result.context.summary if result.context else "",
            "category": result.context.category if result.context else "",
        }
        core_questions = result.strategy.core_questions or []
        directives = result.strategy.legacy_directives or {}

        await self._notify(
            f"🔬 Lens 풀 실행: {valid} ({len(valid)}/{self.LENS_CAP_PER_EVENT} cap)",
            status_callback,
        )

        lens_findings: list[AnalyticalFinding] = []
        for idx, lens_id in enumerate(valid):
            lens = get_lens(lens_id, self.config)
            answers_q = (
                core_questions[idx % len(core_questions)] if core_questions else ""
            )
            # Reuse legacy directive when key matches (transitional shim).
            directive = directives.get(lens_id, "")
            try:
                produced = await lens.run(
                    evidence=evidence,
                    directive=directive,
                    event_meta=event_meta,
                    answers_question=answers_q,
                )
                logger.info(
                    "[orchestrator] lens=%s produced %d finding(s)",
                    lens_id, len(produced),
                )
                lens_findings.extend(produced)
            except Exception as e:
                logger.warning(
                    "[orchestrator] lens=%s execution error: %s; skipping",
                    lens_id, e,
                )
        return lens_findings

    # ------------------------------------------------------------------
    # V3 Step 4 — Gate runner (with retry + partial-analysis alert)
    # ------------------------------------------------------------------

    async def _run_gate_with_retries(
        self,
        gate_name: str,
        gate_fn,
        regenerate_fn,
        status_callback: "StatusCallback",
        max_retries: int = 2,
    ) -> tuple[bool, str]:
        """Run a quality gate with retries. On final failure, emit partial-analysis alert.

        Args:
            gate_name: e.g. "gate_1" or "gate_2" (used in stats + alert text).
            gate_fn: async () -> (passed, reason).
            regenerate_fn: async () -> None — called between retries to refresh inputs.
        Returns:
            (final_passed, final_reason). Even if False, caller should continue with
            partial output (Anti-pattern #7: never silently bypass).
        """
        attempts_key = f"{gate_name}_attempts"
        passes_key = f"{gate_name}_passes"
        retries_key = f"{gate_name}_retries"
        partial_key = f"{gate_name}_partial"

        self._gate_stats[attempts_key] += 1
        passed, reason = await gate_fn()
        if passed:
            self._gate_stats[passes_key] += 1
            return True, reason

        for attempt in range(1, max_retries + 1):
            self._gate_stats[retries_key] += 1
            logger.info(
                "[quality_inspector] %s failed (%s). retry %d/%d",
                gate_name, reason, attempt, max_retries,
            )
            try:
                await regenerate_fn()
            except Exception as e:
                logger.warning("[orchestrator] %s regenerate error: %s", gate_name, e)
            self._gate_stats[attempts_key] += 1
            passed, reason = await gate_fn()
            if passed:
                self._gate_stats[passes_key] += 1
                return True, reason

        self._gate_stats[partial_key] += 1
        await self._notify(
            f"⚠️ 부분 분석 완료. {gate_name} 실패 ({reason})",
            status_callback,
        )
        return False, reason

    async def _notify(
        self, message: str, status_callback: StatusCallback
    ) -> None:
        """Send status update via callback if available."""
        logger.info(message)
        if status_callback:
            await status_callback(message)

    def _build_text_report(self, result: FullAnalysisResult) -> str:
        """Build a clean text summary for Telegram (without glossary)."""
        lines: list[str] = []

        event_name = ""
        if result.context:
            event_name = result.context.event_name or result.context.event_name_en
        lines.append(f"<{event_name or 'Event Analysis'}>")
        lines.append("")

        if result.context:
            lines.append("[상황인식]")
            lines.append("")
            lines.append(result.context.summary)
            lines.append("")
            for fig in result.context.key_figures[:6]:
                label = fig.get("label", "")
                value = fig.get("value", "")
                context = fig.get("context", "")
                ctx_str = f" ({context})" if context else ""
                lines.append(f" -> {label}: {value}{ctx_str}")
            lines.append("")

        if result.players:
            lines.append("[이해관계자]")
            lines.append("")
            for i, p in enumerate(result.players.players[:8], 1):
                name = p.get("name", "")
                role = p.get("role_tag", "")
                lines.append(f"{i}) {name} : {role}")
            lines.append("")

        if result.dynamics:
            lines.append("[구조 및 상호작용]")
            lines.append("")
            lines.append(f"a. 프레임: {result.dynamics.framework}")
            lines.append(f"b. 긴장: {result.dynamics.core_tension}")
            lines.append(f"c. 통찰: {result.dynamics.key_insight}")
            lines.append("")

        if result.chain_reaction:
            lines.append("[연쇄반응]")
            lines.append("")
            for step in result.chain_reaction.chain[:12]:
                title = step.get("title", "")
                desc = step.get("description", "")
                if desc:
                    lines.append(f"→ {title}")
                else:
                    lines.append(f"→ {title}")
            lines.append("")

        if result.scenarios:
            lines.append("[향후 시나리오]")
            lines.append("")
            circled = ["①", "②", "③", "④"]
            for i, sc in enumerate(result.scenarios.scenarios[:4]):
                c = circled[i] if i < len(circled) else f"{i+1}."
                name = sc.get("name", "")
                prob = sc.get("probability", "")
                lines.append(f"{c} {name} ({prob})")
            lines.append("")

        if result.scenarios and result.scenarios.watch_signals:
            lines.append("[지켜봐야 할 시그널]")
            lines.append("")
            for ws in result.scenarios.watch_signals[:5]:
                icon = ws.get("icon", "●")
                signal = ws.get("signal", "")
                lines.append(f"{icon} {signal}")
            lines.append("")

        if result.context and result.context.sources:
            lines.append(f"출처: {', '.join(result.context.sources[:8])}")

        return "\n".join(lines)

    def _build_glossary_text(self, result: FullAnalysisResult) -> str:
        """Build glossary as a separate text for Telegram."""
        all_terms: list[dict] = []
        for section in [result.context, result.players, result.dynamics, result.chain_reaction, result.scenarios]:
            if section and hasattr(section, "glossary") and section.glossary:
                all_terms.extend(section.glossary)
        seen: set[str] = set()
        unique_terms: list[dict] = []
        for t in all_terms:
            term = t.get("term", "")
            if term and term not in seen:
                seen.add(term)
                unique_terms.append(t)
        if not unique_terms:
            return ""
        lines: list[str] = ["[용어 정의]", ""]
        for t in unique_terms:
            lines.append(f"  {t.get('term', '')} : {t.get('definition', '')}")
        return "\n".join(lines)

    async def run_analysis(
        self,
        event_description: str,
        chat_id: int,
        status_callback: StatusCallback = None,
        mode: AnalysisMode | None = None,
        parent_context: ParentContext | None = None,
        fetch_kr_market_internals: bool = False,
    ) -> FullAnalysisResult:
        """v4.0.0 Tier 4: 2-call unified pipeline.

        Phase 1 — ContextAnalyst (Sonnet 4.6, 웹검색): 사실/타임라인/출처 수집.
        Phase 2 — UnifiedComposer (Opus 4.7): 행위자/구조/시나리오/모순 분석 +
                  보고서 본문 작성을 *단일 LLM 호출*로 모두 수행.
        Phase 3 — HTML 렌더 + Cloudflare Pages 배포.
        Phase 4 — composed_report.watch_signals → SQLite Watchlist.

        v5.1.1 — ``parent_context`` 가 주어지면 후속 보고서 모드:
        - compose_unified payload 에 followup 필드 주입 → composer 가 부모 시나리오 인지
        - report.html 의 h1 풋노트 + 상단 부모 헤더 박스 렌더
        - 새 watch_signals 의 chain_depth = parent.chain_depth + 1 로 등록
          (v5.5.7 부터 chain depth 상한 없음 — 손자/증손자/N대손 모두 정상 등록.
          수동 [▶ 후속 보고 생성] 버튼이 폭주 차단)

        legacy 멀티 에이전트 (player/dynamics/chain_reaction/scenario/synthesis_judge/
        quality_inspector/visual_analyst/lens_pool) 는 v4.0.0 부터 호출 안 함.
        모듈 자체는 보존 (향후 정리 commit 에서 제거).
        """
        from src.models import ComposedReport, ComposedSection

        start_time = time.time()

        # v5.5.0 — /analyze --bundle: ReportBundle (.bundle.json) emit 트리거.
        # 토픽 문자열에서 플래그를 떼어내 사실 수집·mode 판정에 오염되지 않게 함.
        emit_bundle = False
        if "--bundle" in event_description:
            emit_bundle = True
            event_description = re.sub(r"\s{2,}", " ", event_description.replace("--bundle", "")).strip()

        if mode is None:
            mode = resolve_mode(event_description)

        # v8.0.0 — 보고서 포맷(장르) 판정. "르포" 트리거면 reportage.
        # 트리거 토큰을 떼어낸 나머지가 user_directive (이번 르포의 앵글). 트리거가
        # 없으면 format=standard / directive="" → 기존 경로와 완전 byte-equal.
        report_format = resolve_report_format(event_description)
        user_directive = ""
        if report_format == "reportage":
            # 트리거 토큰 제거 — 사실 수집·앵글에 "르포" 단어가 노이즈로 섞이지 않게.
            event_description = strip_reportage_trigger(event_description)
            user_directive = event_description

        # Telemetry per-run.
        self.telemetry = RunTelemetry(mode=mode)
        self._wire_telemetry()

        request = AnalysisRequest(
            event_description=event_description,
            chat_id=chat_id,
            mode=mode,
            parent_context=parent_context,
            emit_bundle=emit_bundle,
            report_format=report_format,
            user_directive=user_directive,
        )
        result = FullAnalysisResult(request=request, parent_context=parent_context)

        mode_label = {"fast": " ⚡fast", "deep": " 🔬deep"}.get(mode, " 🟢standard")

        # v4.1.0 — fast 모드에서도 context 모델 다운그레이드 안 함.
        # Tier 4 2-call 파이프라인에서 context 는 편집장이 보는 유일한 사실 입력이라
        # 어떤 모드든 Opus 4.7 reasoning 필요 (사실 추출 품질 = 보고서 품질의 상한).

        # -- Phase 1: 상황 분석관 (사실 수집 + 웹 검색) --
        await self._notify(
            f"🔍 상황 분석관: \"{event_description}\" 사실 수집 중.\n"
            f"Analysis Team {VERSION}{mode_label}",
            status_callback,
        )
        stage = self.telemetry.stage_start("context_analyst")
        result.context = await self.context_analyst.analyze(request)
        self.telemetry.stage_end(stage)

        # v5.2.0 — Market data fetch hook.
        # ContextAnalyst 가 emit 한 instruments_mentioned 를 받아 KRX/FRED/ECOS
        # 에서 실데이터 fetch. fetch 실패해도 보고서 진행 — composer 가
        # time_series 빈 경우 차트만 생략. API key 누락 시에도 동일 (warning log).
        try:
            instruments = list(getattr(result.context, "instruments_mentioned", None) or [])
            if instruments:
                from datetime import date
                from src.tools.market_fetcher import fetch_many

                anchor = None
                event_date_str = (result.context.date or "").strip()
                if event_date_str:
                    try:
                        anchor = date.fromisoformat(event_date_str[:10])
                    except ValueError:
                        anchor = None

                # Mode-aware period 선택 (v5.2.0):
                #  - daily briefing (간밤 / 어제 / 오늘 키워드) → 1M
                #  - historical (IMF / 글금위 / 10년 만에 / 역사적 키워드) → 3Y
                #  - 그 외 (사건 보고서) → 3M (이벤트 ±30일 ≈ 60 영업일)
                fetch_period = _select_market_period(request, result.context)
                stage_mf = self.telemetry.stage_start("market_fetch")
                series_list = await fetch_many(
                    instruments, period=fetch_period, config=self.config,
                    anchor_date=anchor,
                )
                self.telemetry.stage_end(stage_mf)

                # MarketSeries → dict (Pydantic dump) 로 context.time_series 에 저장.
                # composer 는 dict 그대로 읽음 (ComposedSection.charts 와 동일 패턴).
                result.context.time_series = [s.model_dump() for s in series_list]
                # CHART-AP-29 — 비유한값(NaN/inf) 봉을 차트·스트립 합류 전에 결정적 제거.
                _nan_dropped = _sanitize_market_nan(result.context.time_series)
                if _nan_dropped:
                    logger.warning(
                        "[orchestrator] market_fetch: NaN/inf 봉 %d개 제거 (CHART-AP-29 가드)",
                        _nan_dropped,
                    )
                non_empty = sum(1 for s in series_list if s.data)
                logger.info(
                    "[orchestrator] market_fetch period=%s: %d instruments requested, %d returned data",
                    fetch_period, len(instruments), non_empty,
                )
        except Exception as _e:  # pragma: no cover  — fetch 실패가 보고서 흐름 영향 X
            logger.warning("[orchestrator] market_fetch skipped: %s", _e)

        # v5.4.0 — Report image fetch hook.
        # ContextAnalyst 가 수집한 sources URL 의 og:image / og:title / og:description
        # 을 추출해 ContextAnalysis.available_images 채움. composer 가 그 후보 풀
        # 중에서 본문 흐름에 맞는 사진을 골라 hero_image / 섹션 images 로 emit.
        # market_fetcher 와 동일한 graceful degrade — fetch 실패해도 보고서 진행
        # (사진만 emit X). 네트워크 정책으로 외부 차단된 환경에선 빈 list + warning.
        try:
            sources = list(getattr(result.context, "sources", None) or [])
            if sources:
                from src.tools.image_fetcher import fetch_many_images
                stage_if = self.telemetry.stage_start("image_fetch")
                # 최대 5 장만 후보로 (composer 가 그 중 1~3 장 골라 사용).
                # per-URL timeout 5s · total 12s — 보고서 흐름 영향 최소화.
                images = await fetch_many_images(
                    sources[:8], max_count=5,
                    per_url_timeout=5.0, total_timeout=12.0,
                )
                self.telemetry.stage_end(stage_if)
                result.context.available_images = images
                logger.info(
                    "[orchestrator] image_fetch: %d sources tried, %d og:image returned",
                    min(len(sources), 8), len(images),
                )
        except Exception as _e:  # pragma: no cover — fetch 실패가 보고서 흐름 영향 X
            logger.warning("[orchestrator] image_fetch skipped: %s", _e)

        # v7.9.0 — 한국 장마감 브리핑 전용 *시장 내부* 데이터 hook (선물·옵션 + 시장 폭).
        # market_briefing 스케줄러가 fetch_kr_market_internals=True 로 호출할 때만 작동
        # (일반 /analyze·일일브리핑은 default False → byte-equal). 결과는 composer 가
        # 이미 소비하는 key_figures 로 병합(실수치를 본문에 노출). breadth 의 decline-ratio
        # line 차트는 compose 후 결정적으로 주입(아래). 모든 fetch 는 graceful degrade.
        breadth_charts: list[dict] = []
        derivatives_charts: list[dict] = []
        index_ohlc: dict[str, list[dict]] = {}
        kospi_candle_card: dict | None = None
        if fetch_kr_market_internals:
            from datetime import date as _date
            _anchor = None
            _edate = (getattr(result.context, "date", "") or "").strip()
            if _edate:
                try:
                    _anchor = _date.fromisoformat(_edate[:10])
                except ValueError:
                    _anchor = None
            # (1) 지수 선물·옵션 — 그릭 포함 key_figures.
            if getattr(self.config, "enable_kr_derivatives", True):
                try:
                    from src.tools.derivatives_fetcher import fetch_kr_derivatives_snapshot
                    stage_dv = self.telemetry.stage_start("derivatives_fetch")
                    dsnap = await fetch_kr_derivatives_snapshot(
                        anchor_date=_anchor, config=self.config,
                    )
                    self.telemetry.stage_end(stage_dv)
                    if dsnap.key_figures:
                        result.context.key_figures = (
                            list(result.context.key_figures or []) + dsnap.key_figures
                        )
                    # v7.9.9 — 옵션 데스크 직관 차트(IV 스큐·풋콜·OI) 결정적 주입용.
                    derivatives_charts = list(dsnap.charts)
                    logger.info(
                        "[orchestrator] derivatives: +%d key_figures, %d charts (warn=%d)",
                        len(dsnap.key_figures), len(derivatives_charts), len(dsnap.warnings),
                    )
                except Exception as _e:  # pragma: no cover — fetch 실패가 보고서 흐름 영향 X
                    logger.warning("[orchestrator] derivatives_fetch skipped: %s", _e)
            # (2) 시장 폭(등락 종목 수) — key_figures + decline-ratio line 차트.
            if getattr(self.config, "enable_market_breadth", True):
                try:
                    from src.tools.breadth_fetcher import fetch_market_breadth_snapshot
                    # 상관 분석용 지수 종가 — 이미 fetch 한 context.time_series 재사용.
                    idx_closes: dict[str, dict[str, float]] = {}
                    for s in (getattr(result.context, "time_series", None) or []):
                        nm = str(s.get("instrument", ""))
                        mkt = "KOSPI" if "코스피" in nm or "KOSPI" in nm.upper() else (
                            "KOSDAQ" if "코스닥" in nm or "KOSDAQ" in nm.upper() else None
                        )
                        if mkt:
                            idx_closes[mkt] = {
                                d.get("date"): d.get("close")
                                for d in (s.get("data") or [])
                                if d.get("date") and d.get("close") is not None
                            }
                    stage_bd = self.telemetry.stage_start("breadth_fetch")
                    bsnap = await fetch_market_breadth_snapshot(
                        anchor_date=_anchor, config=self.config, index_closes=idx_closes,
                    )
                    self.telemetry.stage_end(stage_bd)
                    if bsnap.key_figures:
                        result.context.key_figures = (
                            list(result.context.key_figures or []) + bsnap.key_figures
                        )
                    breadth_charts = list(bsnap.charts)
                    logger.info(
                        "[orchestrator] breadth: +%d key_figures, %d charts (warn=%d)",
                        len(bsnap.key_figures), len(breadth_charts), len(bsnap.warnings),
                    )
                except Exception as _e:  # pragma: no cover — fetch 실패가 보고서 흐름 영향 X
                    logger.warning("[orchestrator] breadth_fetch skipped: %s", _e)

            # (3) v7.9.9 — combo_candle(하락비율+지수, item2) + 코스피 캔들 카드(item1)용 지수 OHLC.
            for s in (getattr(result.context, "time_series", None) or []):
                nm = str(s.get("instrument", ""))
                mkt = (
                    "KOSPI" if ("코스피" in nm or "KOSPI" in nm.upper())
                    else ("KOSDAQ" if ("코스닥" in nm or "KOSDAQ" in nm.upper()) else None)
                )
                if mkt and s.get("data"):
                    index_ohlc[mkt] = [d for d in s["data"] if d.get("high") is not None]
            # item1 — 코스피 종합지수 *3개월* 캔들 + 20일 이동평균선 (대표 이평선). 브리핑
            # 기본 fetch 는 1M 이라 20일선이 안 그려져, 이 카드만 3M 을 따로 받는다.
            try:
                from src.tools.market_fetcher import fetch_many as _fm_k
                _k3 = await _fm_k(["코스피"], period="3M", config=self.config, anchor_date=_anchor)
                _rows = ((_k3[0].model_dump().get("data") if _k3 else None) or [])
                _rows = [r for r in _rows if r.get("high") is not None and r.get("close") is not None]
                if len(_rows) >= 20:
                    kospi_candle_card = {
                        "type": "candle",
                        "title": "코스피 종합지수",
                        "data": _rows,
                        "moving_average": {"period": 20, "label": "20일 이동평균"},
                        "source": "Yahoo Finance / 최근 3개월 / 일간",
                        "note": (
                            "최근 3개월 일봉 캔들 + 20일 이동평균선. 종가가 이동평균선 위에 "
                            "있으면 단기 상승 추세, 아래면 하락 추세로 본다."
                        ),
                    }
            except Exception as _e:  # pragma: no cover
                logger.warning("[orchestrator] kospi 3M candle skipped: %s", _e)

        # V5 Phase 0C — ContextAnalysis → EvidencePack adapter (telemetry only).
        # v4.5.7 호출 경로는 ComposedReport 를 받는 NarrativeComposer 가 그대로
        # ContextAnalysis 를 입력으로 사용. EvidencePack 은 *측정 + 향후 Phase 의
        # 사전 SSOT* 목적으로 추출. AP-V5-30 (RawContext 가 후속 단계로 누설되는
        # 것을 막는 guard) 의 분기점이 되는 객체.
        try:
            from src.state import (
                evidence_pack_from_context_analysis,
                estimate_state_token_size,
            )
            evidence_pack = evidence_pack_from_context_analysis(result.context)
            ep_tokens = estimate_state_token_size(evidence_pack)
            ctx_tokens = estimate_state_token_size(result.context)
            logger.info(
                "[orchestrator] Phase 0C: EvidencePack extracted — "
                "context_tokens≈%d, evidence_pack_tokens≈%d, compaction_ratio=%.2f, "
                "claims=%d, timeline=%d, sources=%d",
                ctx_tokens, ep_tokens,
                (ep_tokens / ctx_tokens) if ctx_tokens else 1.0,
                len(evidence_pack.claims),
                len(evidence_pack.timeline),
                len(evidence_pack.source_index),
            )
            # 후속 Phase 가 EvidencePack 을 보고 싶을 때 사용 가능 — Phase 1A/2 진입
            # 시 self.research_director / self.composer_v5 가 본 객체를 입력으로 받는다.
            # 현재는 telemetry attribute 로만 보존.
            if self.telemetry is not None:
                setattr(self.telemetry, "evidence_pack_token_estimate", ep_tokens)
                setattr(self.telemetry, "context_token_estimate", ctx_tokens)
        except Exception as _e:  # pragma: no cover  — adapter 실패는 v4.5.7 흐름 영향 X
            logger.debug("[orchestrator] Phase 0C adapter skipped: %s", _e)
            evidence_pack = None

        # V5 Phase 1A — ResearchDirector. opt-in flag 가 켜진 환경에서만 LLM 호출.
        # 꺼져 있는 경우 design_via_heuristics 가 LLM 호출 없이 결정적 brief 를
        # emit. 두 경우 모두 Plan §6.6 인수 기준 #1 ("모든 사건에 대해 AnalysisBrief
        # 를 emit") 충족. v4.5.7 의 NarrativeComposer 호출 형태는 변경되지 않음 —
        # AnalysisBrief 는 telemetry 에 보존되어 *후속 Phase 의 sanity check* 와
        # Plan §6.6 인수 기준 #4 (Golden Prompt 20건 ≥80% 일치) 측정의 입력.
        try:
            from src.agents.research_director import design_via_heuristics
            analysis_brief = None
            if getattr(self.config, "enable_research_director", False):
                self.research_director.telemetry = self.telemetry
                analysis_brief = await self.research_director.design_or_heuristic(
                    user_request=event_description,
                    evidence_pack=evidence_pack,
                    mode=mode,
                    user_intent="",
                )
                source = "llm"
            else:
                analysis_brief = design_via_heuristics(event_description, mode=mode)
                source = "heuristic"
            method_ids = [m.method for m in (analysis_brief.selected_methods or [])]
            logger.info(
                "[orchestrator] Phase 1A: AnalysisBrief emit (source=%s) — "
                "report_mode=%s, methods=%s, strategic_hint=%s, sections=%d",
                source,
                analysis_brief.report_mode,
                method_ids,
                analysis_brief.strategic_hint,
                analysis_brief.report_shape.section_count,
            )
            if self.telemetry is not None:
                setattr(self.telemetry, "analysis_brief_methods", method_ids)
                setattr(self.telemetry, "analysis_brief_report_mode", analysis_brief.report_mode)
                setattr(self.telemetry, "analysis_brief_strategic_hint", analysis_brief.strategic_hint)
                setattr(self.telemetry, "analysis_brief_source", source)
        except Exception as _e:  # pragma: no cover  — Phase 1A 실패는 v4.5.7 흐름 영향 X
            logger.debug("[orchestrator] Phase 1A skipped: %s", _e)

        event_name = result.context.event_name or event_description[:30]
        self.telemetry.event_name = event_name
        await self._notify(
            f"📋 상황 분석관: \"{event_name}\" 사실 정리 완료.\n"
            f"  · 사건 분류: {result.context.category}\n"
            f"  · 타임라인 {len(result.context.timeline)}건, "
            f"핵심 지표 {len(result.context.key_figures)}건, "
            f"출처 {len(result.context.sources)}건\n"
            f"{self._progress_bar(1, total=2)}",
            status_callback,
        )

        # -- Phase 2: UnifiedComposer — 분석 + 작성 단일 호출 --
        # v8.2.3 — 르포는 Opus 4.8, 일반은 4.7. 알림 라벨도 실제 호출 모델과 정합.
        _composer_model_used = self.narrative_composer._model_for_format(report_format)
        _model_label = "Opus 4.8" if report_format == "reportage" else "Opus 4.7"
        await self._notify(
            f"✍️ 편집장 ({_model_label}): 행위자/구조/시나리오/모순 분석 + 보고서 작성 (단일 호출)",
            status_callback,
        )
        stage = self.telemetry.stage_start("unified_composer")
        try:
            result.composed_report = await self.narrative_composer.compose_unified(
                result.context, mode=mode, parent_context=parent_context,
                report_format=report_format, user_directive=user_directive,
            )
        except Exception as e:
            logger.warning("[orchestrator] unified_composer error: %s", e)
            result.composed_report = None
        self.telemetry.stage_end(stage)

        # composer 실패 시 graceful fallback — minimal report from context only
        if result.composed_report is None:
            # v8.2.4 — 편집장이 *왜* 실패했는지(타임아웃/파싱불가/예외)를 사람-읽기
            # 한 줄로 가져와 degradation_reason 으로 노출. 그동안 WARNING 로그로만
            # 삼켜지던 실패 원인을 텔레그램·배너로 표면화 (WRITE-AP-25).
            _fail_reason = (
                getattr(self.narrative_composer, "_last_failure_reason", "")
                or "편집장 호출 실패"
            )
            logger.warning(
                "[orchestrator] composer failed (%s); emitting minimal fallback",
                _fail_reason,
            )
            result.composed_report = ComposedReport(
                headline=event_name,
                deck=(result.context.summary or "")[:200],
                sections=[ComposedSection(
                    heading="요약",
                    prose=result.context.summary or "(분석 실패: composer 호출 오류)",
                )],
                confidence_score=0.0,
                confidence_summary="composer 호출 실패. 사실 자료만 표시.",
                degraded=True,
                degradation_reason=_fail_reason,
            )
            self.telemetry.record_llm_skip(
                "unified_composer", f"failed → minimal fallback ({_fail_reason})",
            )

        # v5.2.0+ — 시계열 차트 안전망 (composer LLM 이 available_time_series 무시
        # 했을 때 자동 보충). prompt 강화는 LLM 의 *지시 준수* 에 의존 — 100% 보장
        # 안 됨. 결정적 hook 으로 시계열 데이터가 있는데 시계열 차트 0개면
        # 첫 섹션에 자동 추가. composer 가 이미 박은 instrument 는 skip (중복 회피).
        # v5.2.2 — context 전체를 전달 (timeline 매칭으로 이벤트 마커 자동 부착,
        # summary 로 takeaway 자동 생성 — mockup 수준 quality).
        # v5.2.5 — instrument 3개↑ 면 compact strip 으로 먼저 한 줄 요약. 그 다음
        # _ensure_time_series_chart 가 *나머지* 풀 차트 보충 (instrument 중복 회피).
        # v8.0.0 — 르포는 상시 시장차트 *자동 주입* 을 건너뛴다 (행위자·흐름 중심,
        # 차트 최소화). composer 가 직접 emit 한 차트는 그대로(_densify 는 적용).
        if request.report_format != "reportage":
            try:
                _ensure_market_strip(result.composed_report, result.context)
            except Exception as _e:  # pragma: no cover
                logger.warning("[orchestrator] _ensure_market_strip skipped: %s", _e)
            try:
                _ensure_time_series_chart(result.composed_report, result.context)
            except Exception as _e:  # pragma: no cover  — hook 실패가 보고서 흐름 영향 X
                logger.warning("[orchestrator] _ensure_time_series_chart skipped: %s", _e)
        # v7.0.2 (CHART-AP-31) — composer 가 직접 emit 한 시계열 차트의 일별 밀도
        # 보장. LLM 이 토큰 절약으로 듬성하게 추린 데이터를 실측 행으로 교체.
        try:
            _densify_ts_charts(result.composed_report, result.context)
        except Exception as _e:  # pragma: no cover  — hook 실패가 보고서 흐름 영향 X
            logger.warning("[orchestrator] _densify_ts_charts skipped: %s", _e)
        # v8.2.9 — 깨진 시각물 약속 제거 (사용자 catch). 본문이 '(아래 관계도/지도/
        # 그래프)' 로 약속한 시각물이 실제로 없으면 그 문구를 지워 없는 그림을 가리키지
        # 않게 한다. 르포에서 stakeholder_map 누락이 빈발 — 르포에 우선 적용(일반
        # 보고서는 byte-equal 보존). 프롬프트가 emit 을 강제하는 게 1차, 이건 안전망.
        if request.report_format == "reportage":
            try:
                _reconcile_visual_references(result.composed_report)
            except Exception as _e:  # pragma: no cover  — hook 실패가 보고서 흐름 영향 X
                logger.warning("[orchestrator] _reconcile_visual_references skipped: %s", _e)
        # v7.9.0/v7.9.9 — 장마감 브리핑 결정적 차트 주입 (composer 비의존 → 모든 브리핑 반영).
        #  (a) breadth line → combo_candle (좌 하락비율 + 우 지수 캔들, item2)
        #  (b) 코스피 종합지수 → 3M candle + 20일선 (item1)
        #  (c) 옵션 데스크 직관 차트 (IV 스큐·풋콜·OI, item4/5)
        if (
            (breadth_charts or derivatives_charts or kospi_candle_card)
            and result.composed_report and result.composed_report.sections
        ):
            try:
                secs = result.composed_report.sections
                # (a) breadth — 지수 OHLC 있으면 combo_candle, 없으면 기존 line 유지.
                bcharts: list[dict] = []
                for ch in breadth_charts:
                    title = ch.get("title", "")
                    mkt = (
                        "KOSPI" if ("KOSPI" in title.upper() or "코스피" in title)
                        else ("KOSDAQ" if ("KOSDAQ" in title.upper() or "코스닥" in title) else None)
                    )
                    ohlc = index_ohlc.get(mkt) if mkt else None
                    if ohlc and len(ohlc) >= 3:
                        bcharts.append({
                            "type": "combo_candle",
                            "title": title,
                            "data": {
                                "line": {"series": ch.get("data") or [], "label": "하락 종목 비율"},
                                "candle": {"series": ohlc, "label": (mkt or "지수")},
                            },
                            "note": ch.get("note"),
                            "source": ch.get("source") or "KRX 정보데이터시스템 · Yahoo Finance",
                        })
                    else:
                        bcharts.append(ch)
                if bcharts:
                    btarget = next(
                        (s for s in secs
                         if any(kw in (s.heading or "") for kw in ("등락", "시장 폭", "폭", "breadth"))),
                        secs[0],
                    )
                    btarget.charts = list(btarget.charts or []) + bcharts
                # (b) 코스피 종합지수 candle 카드 — 기존 line 종합지수 카드 교체(없으면 선두 삽입).
                if kospi_candle_card:
                    placed = False
                    for s in secs:
                        for i, c in enumerate(list(s.charts or [])):
                            ct = (c.get("title") or "") if isinstance(c, dict) else ""
                            if "종합지수" in ct and "코스피" in ct:
                                s.charts[i] = kospi_candle_card
                                placed = True
                                break
                        if placed:
                            break
                    if not placed:
                        secs[0].charts = [kospi_candle_card] + list(secs[0].charts or [])
                # (c) 옵션 데스크 차트 — '옵션/파생/선물/데스크' 섹션, 없으면 마지막 섹션.
                if derivatives_charts:
                    dtarget = next(
                        (s for s in secs
                         if any(kw in (s.heading or "") for kw in ("옵션", "파생", "선물", "데스크"))),
                        secs[-1],
                    )
                    dtarget.charts = list(dtarget.charts or []) + derivatives_charts
                logger.info(
                    "[orchestrator] 브리핑 차트 주입: breadth=%d deriv=%d kospi_candle=%s",
                    len(bcharts), len(derivatives_charts), bool(kospi_candle_card),
                )
            except Exception as _e:  # pragma: no cover
                logger.warning("[orchestrator] 브리핑 차트 주입 skipped: %s", _e)
        # v7.9.14 — composer 가 '지수 등락률 vs 종목 하락비율' diverging_bar 에서
        # KOSPI/KOSDAQ 등락률(neg)을 0/누락으로 emit 하는 회귀 방어 (CHART-AP-35,
        # 사용자 catch). time_series 실측 등락률(절댓값)로 채운다. 행사가 라벨 OI
        # diverging_bar(neg=put_oi) 등은 KOSPI/KOSDAQ 라벨이 아니라 안 건드림.
        if fetch_kr_market_internals and index_ohlc and result.composed_report:
            try:
                def _idx_abs_pct(mkt: str):
                    rows = index_ohlc.get(mkt) or []
                    if len(rows) >= 2:
                        a, b = rows[-2].get("close"), rows[-1].get("close")
                        if a and b:
                            return round(abs((b / a - 1) * 100), 2)
                    return None
                for s in result.composed_report.sections:
                    for c in (s.charts or []):
                        if not (isinstance(c, dict) and c.get("type") == "diverging_bar"):
                            continue
                        for row in (c.get("data") or []):
                            lab = str(row.get("label", ""))
                            mkt = ("KOSPI" if ("KOSPI" in lab.upper() or "코스피" in lab)
                                   else ("KOSDAQ" if ("KOSDAQ" in lab.upper() or "코스닥" in lab) else None))
                            if mkt and not row.get("neg"):
                                pct = _idx_abs_pct(mkt)
                                if pct is not None:
                                    row["neg"] = pct
                                    logger.info(
                                        "[orchestrator] diverging_bar %s 등락률 0→%.2f 보정 (CHART-AP-35)",
                                        mkt, pct,
                                    )
            except Exception as _e:  # pragma: no cover
                logger.warning("[orchestrator] index 등락률 guard skipped: %s", _e)
        # v5.6.6 — SNS broadcast 문구 결정적 폴백 (composer 누락/부분 살림본 대비).
        try:
            _ensure_broadcast_summary(result.composed_report, result.context)
        except Exception as _e:  # pragma: no cover  — 폴백 실패가 보고서 흐름 영향 X
            logger.warning("[orchestrator] _ensure_broadcast_summary skipped: %s", _e)

        # v8.2.4 — critic 루프가 composed_report 를 교체(loop_result.report)할 수 있어
        # degraded 플래그가 유실될 수 있다. 루프 전 상태를 잡아 뒤에서 복원 (WRITE-AP-25).
        _was_degraded = bool(getattr(result.composed_report, "degraded", False))
        _degraded_reason = getattr(result.composed_report, "degradation_reason", "")

        v6_loop_result = None  # Phase V6-7/c — 렌더 후 report_id 태깅 요약 로그용
        # -- Phase 2.5 (V6): Codex fact-critic 루프 (opt-in, flag OFF = byte-equal) --
        # Opus 작성 → Codex 검수 → Opus 보완(≤1) → Codex 확인패스(≤1). 외부 degrade /
        # 보완 실패 시 원본 보존 (AP-V6-12). V6_CODEX_CRITIC OFF 면 이 블록 통째 스킵
        # → v5.8.8 호출 경로 byte-equal (AP-V6-3).
        if self.config.enable_codex_critic:
            try:
                from src.agents.codex_critic import CodexCritic
                from src.factcheck.critic_loop import CriticLoop, NarrativeComposerReviser
                from src.timeutil import today_kst

                loop = CriticLoop(
                    self.config,
                    CodexCritic(self.config),
                    NarrativeComposerReviser(self.narrative_composer),
                )

                async def _loop_progress(msg: str) -> None:
                    await self._notify(msg, status_callback)

                loop_result = await loop.run(
                    result.composed_report, result.context,
                    publication_date=today_kst(),
                    on_progress=_loop_progress,
                    report_format=getattr(request, "report_format", "") or "",
                )
                v6_loop_result = loop_result
                if loop_result.report is not None:
                    result.composed_report = loop_result.report
                # Phase V6-7 — 검수 바이라인. *실제 검수 수행 시에만* (AP-V6-10).
                # v8.2.3 — 르포는 4.8 로 작성됐으므로 byline writer 모델도 4.8.
                if self.config.enable_byline and not loop_result.skipped:
                    from src.factcheck.critic_loop import build_verification_byline
                    result.composed_report.verification = build_verification_byline(
                        loop_result,
                        self.narrative_composer._model_for_format(request.report_format),
                        web_verified=self.config.enable_codex_webverify,
                    )
                logger.info(
                    "[orchestrator] V6 critic loop: skipped=%s reason=%s revised=%s "
                    "confirm=%s init_viol=%d residual=%d unresolved=%d dropped=%d pre_flags=%d",
                    loop_result.skipped, loop_result.skip_reason, loop_result.revised,
                    loop_result.confirm_ran, loop_result.initial_violations,
                    loop_result.residual_violations, loop_result.unresolved_count,
                    len(loop_result.dropped_quotes), loop_result.pre_flag_count,
                )
                for claim in loop_result.applied_claims:
                    logger.info("[orchestrator] V6 검수 식별: %s", claim)
                for change in loop_result.changes:
                    logger.info("[orchestrator] V6 변경: %s", change)
                if loop_result.residual_summary:
                    logger.info(
                        "[orchestrator] V6 residual (미해결): %s",
                        " | ".join(loop_result.residual_summary),
                    )
                # Phase V6-6 — 자율 보강: critique 적립(자동) → 소프트가드 자동등재(log-only)
                # → 승격 후보 표면화(사람 게이트). 적립↔적용 분리 (AP-V6-9).
                if self.config.enable_autolearn and not loop_result.skipped:
                    try:
                        from src.factcheck import critique_log
                        rid = f"{result.context.event_name or 'report'}|{result.context.date}"
                        critique_log.append_critique(rid, loop_result.claim_records)
                        newly = critique_log.auto_register_soft_guards()
                        if newly:
                            logger.info("[orchestrator] V6 소프트가드 자동등재(log-only): %s", newly)
                        cands = critique_log.promotion_candidates()
                        if cands:
                            logger.info(
                                "[orchestrator] V6 정식 승격 후보(사람 확인 필요): %s",
                                [f"{c['signature']}×{c['count']}" for c in cands],
                            )
                    except Exception as _e:  # pragma: no cover
                        logger.warning("[orchestrator] V6 autolearn skipped: %s", _e)
            except Exception as _e:  # pragma: no cover — 외부 의존 실패가 발행을 막지 않음
                logger.warning("[orchestrator] V6 critic loop skipped: %s", _e)

        # v5.6.7 — 최종 기호 정화 (사용자 최우선 규칙). composer 경로는 자체 정화하지만
        # minimal fallback / hook 가 추가한 텍스트 / context 기반 합성본까지 *모든* 경로를
        # 여기서 한 번 더 보장. NarrativeComposer 의 정화 규칙 재사용.
        try:
            self.narrative_composer._sanitize_symbols(result.composed_report)
        except Exception as _e:  # pragma: no cover  — 정화 실패가 보고서 흐름 영향 X
            logger.warning("[orchestrator] _sanitize_symbols skipped: %s", _e)

        # v8.2.4 — critic 루프가 보고서를 교체했어도 degraded 상태는 유지 (WRITE-AP-25).
        if _was_degraded and result.composed_report is not None and not result.composed_report.degraded:
            result.composed_report.degraded = True
            result.composed_report.degradation_reason = (
                result.composed_report.degradation_reason or _degraded_reason
            )

        n_sections = len(result.composed_report.sections)
        n_signals = len(result.composed_report.watch_signals)
        n_contradictions = len(result.composed_report.contradictions)
        await self._notify(
            f"✍️ 보고서 완성: {n_sections}개 섹션, "
            f"감시 신호 {n_signals}건, 모순 {n_contradictions}건 명시.\n"
            f"  · 신뢰도: {result.composed_report.confidence_score * 100:.0f}%\n"
            f"{self._progress_bar(2, total=2)}",
            status_callback,
        )

        # -- Phase 3: HTML 렌더링 + Cloudflare Pages 배포 --
        result.total_duration_seconds = time.time() - start_time

        # composer 산출 → executive_summary (markdown/index 공통 텍스트로 사용).
        result.executive_summary = (
            result.composed_report.deck or result.composed_report.headline or ""
        )

        # Theme: code-rule via lens_policy.select_theme. v8.0.0 — 르포는 전용
        # 테마 풀(REPORTAGE_THEMES 8 다크)에서 선택, 일반은 ALL_THEMES.
        if request.report_format == "reportage":
            from src.lens_policy import select_reportage_theme
            result.report_theme = select_reportage_theme()
        else:
            result.report_theme = select_theme(result.context.category or "general")
        archetype = get_archetype("freeform_essay")
        logger.info(
            "[orchestrator] Tier 4 routing — theme=%s, archetype=%s, mode=%s",
            result.report_theme, archetype.archetype_id, mode,
        )

        stage = self.telemetry.stage_start("report_synthesis")
        report_url = await self.report_synthesizer.synthesize(
            result, theme=result.report_theme, archetype=archetype,
        )
        self.telemetry.stage_end(stage)
        result.report_url = report_url

        # Phase V6-7/c — report_id 태깅 검수 요약 (발행 URL 과 1:1 매칭되는 grep 키).
        if v6_loop_result is not None and not v6_loop_result.skipped:
            _rid = (
                (getattr(result, "report_path", "") or report_url or "")
                .rstrip("/").split("/")[-1].replace(".html", "")
            )
            logger.info(
                "[orchestrator] V6 [%s] 검수 요약: 식별 %d · 변경 %d · 잔존 %d · 미해결 %d",
                _rid, v6_loop_result.initial_violations, len(v6_loop_result.changes),
                v6_loop_result.residual_violations, v6_loop_result.unresolved_count,
            )

        # -- Phase V6-4: Codex 미학 검수 (opt-in, 발행 후 log-only) --
        # 렌더된 보고서의 차트 PNG 를 codex 비전으로 교차검수. 현재 측정(log)만 —
        # 차트 자동수정 안 함 (V5 deterministic_gate / chart_critic 와 병행). flag OFF /
        # Playwright·codex 비전 미가용 시 graceful skip (AP-V6-12). byte-equal 보존.
        if self.config.enable_codex_visual and getattr(result, "report_path", None):
            try:
                from src.agents.codex_critic import CodexCritic
                vverdict = await CodexCritic(self.config).critique_report_visuals(
                    result.composed_report, result.report_path,
                )
                if vverdict.skipped:
                    logger.info("[orchestrator] V6 미학 검수 skip: %s", vverdict.skip_reason)
                else:
                    logger.info(
                        "[orchestrator] V6 미학 검수: %s findings=%d",
                        vverdict.verdict_status, vverdict.violation_count,
                    )
                    for c in vverdict.claims:
                        logger.info(
                            "[orchestrator] V6 미학 지적: [%s] %s: %s",
                            c.error_class, c.location, c.fix_instruction,
                        )
            except Exception as _e:  # pragma: no cover — 미학 검수 실패가 발행 막지 않음
                logger.warning("[orchestrator] V6 미학 검수 skipped: %s", _e)

        # v5.2.14 — chart type usage 추적 (캔들 starvation 회귀 방지).
        # composed.sections 의 모든 charts 를 순회해 type 수집 → telemetry +
        # 영구 JSONL. ``warn_if_starved`` 가 누적 N 보고서 동안 0회 emit type 감지.
        # v5.5.8 — `result.sections` / `result.embedded_map` 은 `FullAnalysisResult`
        # 에 존재하지 않는 필드 (AttributeError silent). 정확한 위치는
        # `result.composed_report.sections` / `.embedded_map`. v5.2.14 도입부터
        # 매 보고서마다 try/except 가 잡고 warning 만 찍어 차트 type 기록이 0건.
        try:
            from src.visual.usage_log import append_run, warn_if_starved
            emitted_types: list[str] = []
            for sec in (result.composed_report.sections or []):
                for ch in (sec.charts or []):
                    if isinstance(ch, dict):
                        ct = ch.get("type")
                        if isinstance(ct, str) and ct:
                            emitted_types.append(ct)
            # embedded_map 도 시각화 채널 → starvation 분모 포함
            if getattr(result.composed_report, "embedded_map", None):
                emitted_types.append("map")
            if self.telemetry is not None:
                self.telemetry.record_chart_types(emitted_types)
            append_run(event=event_name, mode=mode, chart_types=emitted_types)
            warn_if_starved()
        except Exception as e:  # noqa: BLE001
            logger.warning("[orchestrator] chart usage tracking fail: %s", e)

        # -- Phase 4: Watchlist 등록 (composed_report.watch_signals 에서) --
        # v5.5.7: chain depth 가드 제거. v5.4.9 의 MAX_CHAIN_DEPTH=0 은 자동 후속
        # 폭주 차단이 목적이었으나 v5.5.6 의 [▶ 후속 보고 생성] 수동 버튼 모델
        # (사용자가 매번 의식적으로 활성화) 로 자동 폭주 위험이 사라졌고, 가드가
        # 부모 보고서 (depth=0) 의 watchlist 등록까지 막아 후속 분석에 필요한 부모
        # 메타 자체를 잃는 사이드이펙트가 v5.5.6 회귀의 root cause. 부모/자식/손자/
        # N대손 모두 정상 등록.
        child_chain_depth = (parent_context.chain_depth + 1) if parent_context is not None else 0
        # v8.0.0 — 르포 포맷은 말미 감시신호(watchlist) 단계를 건너뛴다. 프롬프트가
        # watch_signals 를 비우도록 지시하므로 보통 빈 list 지만, composer 가 그래도
        # emit 하더라도 reportage 는 등록하지 않는다 (장르 정체성 — 신호 epilogue 없음).
        if (
            self.watchlist_registry is not None
            and result.composed_report.watch_signals
            and request.report_format != "reportage"
        ):
            try:
                report_id = ""
                if result.report_path:
                    import os as _os
                    report_id = _os.path.splitext(_os.path.basename(result.report_path))[0]
                signals = convert_watch_signals(
                    scenario_signals=result.composed_report.watch_signals,
                    parent_report_url=result.report_url or "",
                    parent_report_id=report_id,
                    parent_chat_id=request.chat_id,
                    chain_depth=child_chain_depth,
                )
                # v5.1.1: 부모 메타 등록 — monitor 가 신호 발화 시 ParentContext 즉시 조립용.
                # v5.5.8: 시나리오는 `result.scenarios` (ScenarioAnalysis, Optional)
                # 의 `.scenarios` 에 있음. v5.1.1 도입 시 `result.composed_report.scenarios`
                # 로 잘못 쓰여 AttributeError silent → v5.5.7 이전 모든 보고서의
                # report_meta 등록 실패 (36건 부모 모두 메타 없음). v4.0.0 Tier 4
                # 부터 ComposedReport 는 시나리오 분석을 sections 안에 통합하므로
                # 별도 scenarios 필드 없음. `result.scenarios` 가 None 이면 빈 list.
                try:
                    parent_scenarios: list[dict] = []
                    if result.scenarios is not None and result.scenarios.scenarios:
                        parent_scenarios = list(result.scenarios.scenarios)
                    # v5.8.0: 부모 헤드라인을 메타에 저장 — 후속 보고서의
                    # '이 분석의 출발점' (제목 + 링크) 렌더용.
                    parent_title = ""
                    if result.composed_report and result.composed_report.headline:
                        parent_title = result.composed_report.headline
                    self.watchlist_registry.register_report_meta(
                        report_id=report_id,
                        event_description=event_description,
                        scenarios=parent_scenarios,
                        chain_depth=child_chain_depth,
                        report_title=parent_title,
                    )
                except Exception as meta_err:
                    logger.warning(
                        "[orchestrator] register_report_meta failed (계속 진행): %s",
                        meta_err,
                    )
                inserted = sum(
                    1 for sig in signals if self.watchlist_registry.register(sig)
                )
                logger.info(
                    "[orchestrator] Watchlist: %d/%d signals registered (chat=%d, depth=%d)",
                    inserted, len(signals), request.chat_id, child_chain_depth,
                )
                if inserted:
                    await self._notify(
                        f"📒 감시 신호 {inserted}건 DB 등록. /watchlist 로 확인.",
                        status_callback,
                    )
            except Exception as e:
                logger.warning("[orchestrator] Watchlist register error: %s", e)

        # v4.1.0: 모델 다운그레이드 자체를 안 하므로 복원 로직도 불필요.

        # Gate stats logging (변경 없음).
        s = self._gate_stats
        for g in ("gate_1", "gate_2"):
            attempts = s[f"{g}_attempts"]
            passes = s[f"{g}_passes"]
            retries = s[f"{g}_retries"]
            partial = s[f"{g}_partial"]
            pass_rate = (passes / attempts * 100.0) if attempts else 0.0
            retry_rate = (retries / attempts * 100.0) if attempts else 0.0
            logger.info(
                "[quality_inspector] %s stats: attempts=%d passes=%d retries=%d "
                "partial=%d (pass_rate=%.1f%% retry_rate=%.1f%%)",
                g, attempts, passes, retries, partial, pass_rate, retry_rate,
            )

        # Telemetry summary.
        if self.telemetry is not None:
            self.telemetry.log_summary()
            # v4.0.0 Tier 4: 모든 모드 max_llm_calls=2 고정 (context + composer).
            from src.token_budget import TokenBudget
            cap = TokenBudget.for_mode(mode).max_llm_calls
            # V6: critic 루프의 Opus 보완(revise_for_facts)이 RunTelemetry 1콜을 정당하게
            # 추가 (codex 검수/확인패스/미학은 외부 subprocess라 RunTelemetry 미집계).
            # 켜졌을 때 budget 경고가 헛울리지 않게 보정.
            if self.config.enable_codex_critic:
                cap += 1
            if self.telemetry.total_llm_calls > cap:
                logger.warning(
                    "[telemetry] LLM call budget exceeded: %d > %d (mode=%s). "
                    "Consider reviewing per-step decisions.",
                    self.telemetry.total_llm_calls, cap, mode,
                )

        return result
