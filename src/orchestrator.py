"""Orchestrator -- mode-aware analysis pipeline coordinator (v3.1.0)."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from typing import Any, Callable, Coroutine, Optional

from src.archetypes.registry import get_archetype, list_archetypes, select_archetype
from src.config import Config
from src.lens_policy import select_lenses, select_theme
from src.lenses.registry import get_lens, list_lenses
from src.models import (
    AnalysisRequest, AnalysisStrategy, AnalyticalFinding, Claim, ConfidenceProfile,
    Evidence, FullAnalysisResult, JudgmentVerdict, MAX_CHAIN_DEPTH, ParentContext,
)
from src.telemetry import RunTelemetry
from src.token_budget import AnalysisMode, TokenBudget, resolve_mode
from src.visual_builder import needs_advanced_visuals
from src.watchlist import WatchlistRegistry, convert_watch_signals
from src.agents.context_analyst import ContextAnalyst
from src.agents.player_analyst import PlayerAnalyst
from src.agents.dynamics_analyst import DynamicsAnalyst
from src.agents.chain_reaction_analyst import ChainReactionAnalyst
from src.agents.scenario_architect import ScenarioArchitect
from src.agents.visual_analyst import VisualAnalyst
from src.agents.report_synthesizer import ReportSynthesizer
from src.agents.quality_inspector import QualityInspector
from src.agents.synthesis_judge import SynthesisJudge
from src.agents.narrative_composer import NarrativeComposer
from src.visual_builder import build_chart_catalog

logger = logging.getLogger(__name__)

VERSION = "v5.2.3"


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
    """composer 가 박은 시계열 차트 개수."""
    n = 0
    for sec in composed.sections or []:
        for ch in (sec.charts or []):
            if isinstance(ch, dict) and (ch.get("type") or "").lower() in _TS_CHART_TYPES:
                n += 1
    return n


def _composer_instruments(composed) -> set[str]:
    """composer 가 박은 시계열 차트의 instrument 이름 집합 (제목 기반 추측)."""
    out: set[str] = set()
    for sec in composed.sections or []:
        for ch in (sec.charts or []):
            if not isinstance(ch, dict):
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


def _format_ts_takeaway(data: list, ctype: str, context) -> str:
    """본문 narrative 우선, 없으면 변동성 기반 자동 해석."""
    # 1순위: context.summary 의 첫 문장 (≤100자)
    summary = (getattr(context, "summary", "") or "").strip()
    if summary:
        first = summary.split(".")[0].strip()
        if 10 <= len(first) <= 100:
            return first
    # 2순위: 데이터 기반 변동성
    if not data:
        return ""
    def _close(d):
        return d.get("close") if ctype == "candle" else d.get("y", d.get("close"))
    closes = [_close(d) or 0 for d in data]
    closes = [c for c in closes if c > 0]
    if len(closes) < 2:
        return ""
    hi, lo = max(closes), min(closes)
    if lo <= 0:
        return ""
    range_pct = (hi - lo) / lo * 100
    fmt_n = (lambda v: f"{v:,.0f}") if hi >= 1000 else (lambda v: f"{v:.2f}")
    return f"기간 중 최고 {fmt_n(hi)} · 최저 {fmt_n(lo)} — 변동폭 {range_pct:.1f}%"


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
        "takeaway": _format_ts_takeaway(chart_data, ctype, context),
    }


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
    to_add = [s for s in candidates if s.get("instrument") not in composer_names]
    if not to_add:
        return  # composer 가 다 박았으면 no-op

    # data 많은 순 (가장 정보 풍부한 series 가 첫 섹션)
    to_add.sort(key=lambda s: -len(s.get("data") or []))

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
        # v3.1.0: legacy persona 인스턴스는 보존하지만 fast/standard 에서는 호출하지 않음.
        # deep 모드에서만 6막 보고서 풍부 데이터 보존을 위해 호출 (FUT-LEGACY-001).
        self.player_analyst = PlayerAnalyst(config)
        self.dynamics_analyst = DynamicsAnalyst(config)
        self.chain_reaction_analyst = ChainReactionAnalyst(config)
        self.scenario_architect = ScenarioArchitect(config)
        self.visual_analyst = VisualAnalyst(config)
        self.report_synthesizer = ReportSynthesizer(config)
        # V3 Step 4 (v2.8.0)
        self.quality_inspector = QualityInspector(config)
        self.synthesis_judge = SynthesisJudge(config)
        # v3.3.0 — freeform editorial pass (Opus 4.7). deep 모드만 호출.
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
        for agent in (
            self.context_analyst, self.player_analyst, self.dynamics_analyst,
            self.chain_reaction_analyst, self.scenario_architect, self.visual_analyst,
        ):
            agent.telemetry = self.telemetry
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
          (``>= MAX_CHAIN_DEPTH`` 면 등록 자체 스킵 — 체인 종결)

        legacy 멀티 에이전트 (player/dynamics/chain_reaction/scenario/synthesis_judge/
        quality_inspector/visual_analyst/lens_pool) 는 v4.0.0 부터 호출 안 함.
        모듈 자체는 보존 (향후 정리 commit 에서 제거).
        """
        from src.models import ComposedReport, ComposedSection

        start_time = time.time()

        if mode is None:
            mode = resolve_mode(event_description)

        # Telemetry per-run.
        self.telemetry = RunTelemetry(mode=mode)
        self._wire_telemetry()

        request = AnalysisRequest(
            event_description=event_description,
            chat_id=chat_id,
            mode=mode,
            parent_context=parent_context,
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
                non_empty = sum(1 for s in series_list if s.data)
                logger.info(
                    "[orchestrator] market_fetch period=%s: %d instruments requested, %d returned data",
                    fetch_period, len(instruments), non_empty,
                )
        except Exception as _e:  # pragma: no cover  — fetch 실패가 보고서 흐름 영향 X
            logger.warning("[orchestrator] market_fetch skipped: %s", _e)

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

        # -- Phase 2: UnifiedComposer (Opus 4.7) — 분석 + 작성 단일 호출 --
        await self._notify(
            "✍️ 편집장 (Opus 4.7): 행위자/구조/시나리오/모순 분석 + 보고서 작성 (단일 호출)",
            status_callback,
        )
        stage = self.telemetry.stage_start("unified_composer")
        try:
            result.composed_report = await self.narrative_composer.compose_unified(
                result.context, mode=mode, parent_context=parent_context,
            )
        except Exception as e:
            logger.warning("[orchestrator] unified_composer error: %s", e)
            result.composed_report = None
        self.telemetry.stage_end(stage)

        # composer 실패 시 graceful fallback — minimal report from context only
        if result.composed_report is None:
            logger.warning("[orchestrator] composer failed; emitting minimal fallback")
            result.composed_report = ComposedReport(
                headline=event_name,
                deck=(result.context.summary or "")[:200],
                sections=[ComposedSection(
                    heading="요약",
                    prose=result.context.summary or "(분석 실패 — composer 호출 오류)",
                )],
                confidence_score=0.0,
                confidence_summary="composer 호출 실패. 사실 자료만 표시.",
            )
            self.telemetry.record_llm_skip(
                "unified_composer", "failed → minimal fallback",
            )

        # v5.2.0+ — 시계열 차트 안전망 (composer LLM 이 available_time_series 무시
        # 했을 때 자동 보충). prompt 강화는 LLM 의 *지시 준수* 에 의존 — 100% 보장
        # 안 됨. 결정적 hook 으로 시계열 데이터가 있는데 시계열 차트 0개면
        # 첫 섹션에 자동 추가. composer 가 이미 박은 instrument 는 skip (중복 회피).
        # v5.2.2 — context 전체를 전달 (timeline 매칭으로 이벤트 마커 자동 부착,
        # summary 로 takeaway 자동 생성 — mockup 수준 quality).
        try:
            _ensure_time_series_chart(result.composed_report, result.context)
        except Exception as _e:  # pragma: no cover  — hook 실패가 보고서 흐름 영향 X
            logger.warning("[orchestrator] _ensure_time_series_chart skipped: %s", _e)

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

        # Theme: code-rule via lens_policy.select_theme — mono 2종만 emit
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

        # -- Phase 4: Watchlist 등록 (composed_report.watch_signals 에서) --
        # v5.1.1: 체인 상한 — parent_context.chain_depth + 1 >= MAX_CHAIN_DEPTH 면 등록 스킵.
        # 손자(depth=2) 보고서가 다시 후속을 자동 트리거하지 못하도록 차단.
        child_chain_depth = (parent_context.chain_depth + 1) if parent_context is not None else 0
        chain_at_cap = child_chain_depth >= MAX_CHAIN_DEPTH
        if chain_at_cap:
            logger.info(
                "[orchestrator] Chain depth cap reached (depth=%d, MAX=%d); "
                "skipping watch_signals registration for this report",
                child_chain_depth, MAX_CHAIN_DEPTH,
            )
        if (
            self.watchlist_registry is not None
            and result.composed_report.watch_signals
            and not chain_at_cap
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
                try:
                    self.watchlist_registry.register_report_meta(
                        report_id=report_id,
                        event_description=event_description,
                        scenarios=list(result.composed_report.scenarios or []),
                        chain_depth=child_chain_depth,
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
            # v4.0.0 Tier 4: 모든 모드 max_llm_calls=2 고정. 직접 비교 (budget 변수 미사용).
            from src.token_budget import TokenBudget
            cap = TokenBudget.for_mode(mode).max_llm_calls
            if self.telemetry.total_llm_calls > cap:
                logger.warning(
                    "[telemetry] LLM call budget exceeded: %d > %d (mode=%s). "
                    "Consider reviewing per-step decisions.",
                    self.telemetry.total_llm_calls, cap, mode,
                )

        return result
