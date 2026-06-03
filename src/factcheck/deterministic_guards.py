"""V6 Phase V6-2 — 결정적 사실 사전필터 가드 (REFACTOR_V6_PLAN.md §3).

codex 호출(=ChatGPT 한도) 전에 *명백한* 사실 위반을 **0-LLM** 으로 거른다.
`src/visual/` 의 결정적 가드(schemas/sanity_check)와 대칭 구조.

원칙:
  - **log-only 우선** — 본 모듈은 위반을 *검출만* 하고 본문을 drop/수정하지 않는다.
    GuardFlag 를 반환할 뿐, drop/enforce 는 호출측이 측정 후 단계적으로 승격
    (REFACTOR_V6_PLAN.md §4.5, AP-V6-9). flag `V6_FACT_GUARDS` default OFF.
  - **결정적 영역만** — 출처에 없는 수치 / scope 경고 위반 / 신규성 날짜차 /
    시장 수치 불일치 / NaN 노출. *의미 판단이 필요한* 사건 혼동·주장→사실·인과
    과장 등은 본 가드가 아니라 Codex critic(Phase 3)이 맡는다 (역할 분리).
  - **낮은 FP** — good_prose 에서 0 FP 를 목표로 보수적으로 검출. 의심스러우면
    flag 하지 않는다 (멀쩡한 본문 보호 — AP-V6-8 사상).
  - **사전필터 합류** — 반환된 GuardFlag 는 Phase 3 에서 ``CodexCritic.critique(
    pre_flags=...)`` 로 합류해 codex 토큰 없이 Opus 보완 지시에 합산된다.

orchestrator 미연결 = byte-equal (Phase 2 코드 랜딩 단계).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.models import ComposedReport, ContextAnalysis

# 가드 이름 상수 (fixture 의 ``guard`` 필드와 정합).
GUARD_UNSOURCED = "UnsourcedNumberGuard"
GUARD_SCOPE = "ScopeBarewordGuard"
GUARD_NOVELTY = "NoveltyDeltaGuard"
GUARD_MARKET = "MarketDataSourceGuard"
GUARD_NAN = "NaNExposureGuard"


class ProseBlock(BaseModel):
    """검수 대상 본문 단위 (위치 + 텍스트)."""

    location: str
    text: str


class GuardFlag(BaseModel):
    """결정적 가드 1건의 검출 결과. fixture 의 ``expected_flag`` 와 ``flag`` 정합.

    Codex 의 ``CritiqueClaim`` 보다 가벼운 *사전* 신호 — 호출측이 stringify 해
    ``pre_flags`` 로 codex 에 합류시키거나 log-only 로 적립한다.
    """

    guard: str
    flag: str
    location: str
    quote: str
    detail: str = ""
    severity: Literal["high", "medium", "low"] = "medium"

    def as_pre_flag(self) -> str:
        """codex pre_flags 합류용 한 줄 표현."""
        return f"[{self.flag}] {self.location}: {self.quote} — {self.detail}".strip(" —")


# --------------------------------------------------------------------------
# 정규식 / 헬퍼
# --------------------------------------------------------------------------

# 검사 대상 "정량 주장" — 숫자 + 살아있는 단위. 날짜(plain 년)는 FP 위험으로 제외.
_CLAIM_NUM_RE = re.compile(r"(\d[\d,]*)\s*(년\s*만|개|만|억|%|배|명)")
# 본문/근거에서 숫자 런 추출 (소수 포함). 비교는 콤마 제거 정규화 후.
_NUM_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
# scope 경고: "보드/superchip 단위 아님" 류에서 금지 scope 명사 추출.
_SCOPE_FORBID_RE = re.compile(r"([가-힣A-Za-z][가-힣A-Za-z/]*)\s*단위\s*아님")
# 대형 수치 동반 여부 (scope 가드 발화 조건).
_LARGE_NUM_RE = re.compile(r"\d[\d,]*\s*(만|억|개)")
# NaN 노출.
_NAN_RE = re.compile(r"(?<![A-Za-z])nan(?![A-Za-z])", re.IGNORECASE)
# 가격-like 숫자 (콤마 그룹 / 소수 / 4자리+ 정수). 날짜(5월·29일)·한자리 정수 제외.
_PRICE_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{4,}")

# 신규성 단어.
_ABSOLUTE_NOVELTY = ("오늘", "방금", "지금 막", "막 공개", "오늘 공개", "오늘 발표", "이날 공개")
_RELATIVE_NOVELTY = ("이틀 전", "사흘 전", "어젯밤", "어제", "엊그제", "간밤", "하루 전")


def _norm_num(s: str) -> str:
    return s.replace(",", "")


def _corpus_digit_set(corpus: str) -> set[str]:
    return {_norm_num(m) for m in _NUM_TOKEN_RE.findall(corpus)}


def _parse_date(s: str) -> date | None:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def blocks_from_report(report: ComposedReport) -> list[ProseBlock]:
    """ComposedReport 의 사용자 노출 텍스트를 (위치, 텍스트) 단위로 평탄화."""
    blocks: list[ProseBlock] = []
    if report.headline:
        blocks.append(ProseBlock(location="headline", text=report.headline))
    if report.deck:
        blocks.append(ProseBlock(location="deck", text=report.deck))
    for sec in report.sections:
        if sec.prose:
            blocks.append(ProseBlock(location=sec.heading or "(섹션)", text=sec.prose))
    if report.closing:
        blocks.append(ProseBlock(location="closing", text=report.closing))
    return blocks


def source_dates_from_context(context: ContextAnalysis) -> list[str]:
    """Phase V6-8 — provenance 의 source_date 들 (NoveltyDeltaGuard 데이터 공급)."""
    return [
        p["source_date"]
        for p in getattr(context, "provenance", []) or []
        if isinstance(p, dict) and p.get("source_date")
    ]


def scope_notes_from_context(context: ContextAnalysis) -> list[str]:
    """Phase V6-8 — provenance 의 scope_note 들 (ScopeBarewordGuard 데이터 공급)."""
    return [
        p["scope_note"]
        for p in getattr(context, "provenance", []) or []
        if isinstance(p, dict) and p.get("scope_note")
    ]


def evidence_corpus_from_context(context: ContextAnalysis) -> str:
    """ContextAnalysis 의 근거 텍스트를 검색용 단일 코퍼스로 합본."""
    parts: list[str] = [context.summary, context.background, context.event_name]
    for item in context.timeline:
        parts.extend(str(v) for v in item.values())
    for fig in context.key_figures:
        parts.extend(str(v) for v in fig.values())
    parts.extend(context.sources)
    return "\n".join(p for p in parts if p)


# --------------------------------------------------------------------------
# 가드들
# --------------------------------------------------------------------------


def unsourced_number_guard(blocks: list[ProseBlock], corpus: str) -> list[GuardFlag]:
    """본문의 정량 주장(숫자+단위) 중 *근거 코퍼스에 없는* 수치를 flag.

    예: 본문 "27년 만" 인데 근거엔 "30년" 만 → "27" 미존재 → flag.
    """
    corpus_digits = _corpus_digit_set(corpus)
    flags: list[GuardFlag] = []
    for blk in blocks:
        for m in _CLAIM_NUM_RE.finditer(blk.text):
            num = _norm_num(m.group(1))
            if num not in corpus_digits:
                flags.append(
                    GuardFlag(
                        guard=GUARD_UNSOURCED,
                        flag="unsourced_number",
                        location=blk.location,
                        quote=m.group(0),
                        detail=f"수치 '{m.group(0)}' 가 수집 근거에 없음",
                        severity="high",
                    )
                )
    return flags


def scope_bareword_guard(
    blocks: list[ProseBlock], scope_notes: list[str],
) -> list[GuardFlag]:
    """근거 scope_note 가 "X 단위 아님" 으로 경고한 X 에 대형 수치를 귀속하면 flag.

    예: scope_note "130만 = 랙 전체 단위. 보드/superchip 단위 아님" + 본문이
    "보드 ... 130만" → scope 오귀속.
    """
    forbidden: list[str] = []
    for note in scope_notes:
        for m in _SCOPE_FORBID_RE.finditer(note):
            forbidden.extend(w.strip() for w in m.group(1).split("/") if w.strip())
    if not forbidden:
        return []
    flags: list[GuardFlag] = []
    for blk in blocks:
        if not _LARGE_NUM_RE.search(blk.text):
            continue
        for word in forbidden:
            if word and word in blk.text:
                flags.append(
                    GuardFlag(
                        guard=GUARD_SCOPE,
                        flag="scope_bareword",
                        location=blk.location,
                        quote=word,
                        detail=f"근거가 '{word} 단위 아님' 으로 경고했는데 대형 수치를 '{word}' 에 귀속",
                        severity="high",
                    )
                )
                break
    return flags


def novelty_delta_guard(
    blocks: list[ProseBlock], publication_date: str, source_dates: list[str],
) -> list[GuardFlag]:
    """출처 작성일이 발행일과 크게 다른데 본문이 신규성/근접 시점을 단정하면 flag.

    절대 신규성("오늘/방금") + 출처가 1일 초과 과거 → novelty_delta.
    상대 시점("이틀 전/어젯밤") + 출처가 3일 초과 과거 → stale_relative_timepoint.
    """
    pub = _parse_date(publication_date)
    if pub is None:
        return []
    deltas = [
        (pub - sd).days for sd in (_parse_date(s) for s in source_dates) if sd is not None
    ]
    if not deltas:
        return []
    max_delta = max(deltas)
    flags: list[GuardFlag] = []
    for blk in blocks:
        abs_hit = next((w for w in _ABSOLUTE_NOVELTY if w in blk.text), None)
        rel_hit = next((w for w in _RELATIVE_NOVELTY if w in blk.text), None)
        if abs_hit and max_delta > 1:
            flags.append(
                GuardFlag(
                    guard=GUARD_NOVELTY,
                    flag="novelty_delta",
                    location=blk.location,
                    quote=abs_hit,
                    detail=f"출처 작성일이 발행일보다 {max_delta}일 과거인데 '{abs_hit}' 로 신규 단정",
                    severity="high",
                )
            )
        elif rel_hit and max_delta > 3:
            flags.append(
                GuardFlag(
                    guard=GUARD_NOVELTY,
                    flag="stale_relative_timepoint",
                    location=blk.location,
                    quote=rel_hit,
                    detail=f"출처가 {max_delta}일 과거인데 상대 시점 '{rel_hit}' 를 그대로 베낌",
                    severity="high",
                )
            )
    return flags


def market_data_source_guard(
    blocks: list[ProseBlock],
    market_series: dict,
    *,
    tolerance: float = 0.005,
) -> list[GuardFlag]:
    """본문의 시장 *가격 레벨* 이 time_series 의 어느 종가와도 안 맞으면 flag (Phase V6-8/B).

    market_series: {종목명: 기준값(float) | 종가 리스트(list[float])}. 종목명 직후의
    *가격* 숫자만 검사 — % 등락률은 건너뜀(코덱스 담당). 날짜 모호성에 강하도록
    *시계열의 어느 값과도* 일치하지 않을 때만 flag (low-FP). 비어있으면 inert.
    """
    flags: list[GuardFlag] = []
    for name, ref in market_series.items():
        closes = [float(x) for x in (ref if isinstance(ref, (list, tuple)) else [ref]) if x]
        if not name or not closes:
            continue
        for blk in blocks:
            start = 0
            while True:
                p = blk.text.find(name, start)
                if p < 0:
                    break
                start = p + len(name)
                window = blk.text[start:start + 30]  # 종목명 직후 30자 (날짜 끼어도 가격 포착)
                for m in _PRICE_RE.finditer(window):
                    # 가격 숫자 직후가 '%' 면 등락률 → 가격 가드 대상 아님 (코덱스 담당).
                    if window[m.end():m.end() + 1] == "%":
                        continue
                    try:
                        got = float(_norm_num(m.group()))
                    except ValueError:
                        continue
                    if got == 0:
                        continue
                    # 시계열의 *어느 종가와도* tolerance 안에서 안 맞으면 flag (날짜 모호성 강건).
                    if not any(abs(got - c) / c <= tolerance for c in closes):
                        flags.append(
                            GuardFlag(
                                guard=GUARD_MARKET,
                                flag="market_value_mismatch",
                                location=blk.location,
                                quote=f"{name} {m.group()}",
                                detail=f"'{name}' 본문 가격 {got} 가 time_series 어느 종가와도 불일치",
                                severity="high",
                            )
                        )
    return flags


def market_series_from_context(context: ContextAnalysis) -> dict:
    """Phase V6-8/B — context.time_series → {종목명: [종가 리스트]} (MarketDataSourceGuard 공급).

    날짜 모호성에 강하도록 *전체 종가 리스트* 를 넘긴다 (특정일 인용도 매치되게).
    """
    out: dict[str, list[float]] = {}
    for ts in getattr(context, "time_series", []) or []:
        if not isinstance(ts, dict):
            continue
        name = ts.get("instrument") or ts.get("name")
        data = ts.get("data") or []
        if not name or not data:
            continue
        closes = [
            float(d["close"])
            for d in data
            if isinstance(d, dict) and d.get("close")
        ]
        if closes:
            out[name] = closes
    return out


def nan_exposure_guard(
    blocks: list[ProseBlock], report: ComposedReport | None = None,
) -> list[GuardFlag]:
    """본문 또는 차트 데이터에 'nan' 이 노출되면 flag (CHART-AP-29 의 본문측 대칭)."""
    flags: list[GuardFlag] = []
    for blk in blocks:
        if _NAN_RE.search(blk.text):
            flags.append(
                GuardFlag(
                    guard=GUARD_NAN,
                    flag="nan_exposed",
                    location=blk.location,
                    quote="nan",
                    detail="본문에 'nan' 노출",
                    severity="high",
                )
            )
    if report is not None:
        for sec in report.sections:
            for chart in sec.charts:
                if isinstance(chart, dict) and _NAN_RE.search(str(chart.get("data", ""))):
                    flags.append(
                        GuardFlag(
                            guard=GUARD_NAN,
                            flag="nan_exposed",
                            location=f"chart:{chart.get('title', sec.heading)}",
                            quote="nan",
                            detail="차트 데이터에 'nan' 노출",
                            severity="high",
                        )
                    )
    return flags


# --------------------------------------------------------------------------
# 집계
# --------------------------------------------------------------------------


def run_fact_guards(
    report: ComposedReport,
    context: ContextAnalysis,
    *,
    publication_date: str = "",
    source_dates: list[str] | None = None,
    market_series: dict | None = None,
    scope_notes: list[str] | None = None,
) -> list[GuardFlag]:
    """모든 결정적 가드를 돌려 GuardFlag 목록을 반환 (log-only — drop 안 함).

    날짜·시장·scope 부가 입력이 안 주어지면 context 에서 best-effort 로 끌어온다
    (Phase 2 단계에선 호출측이 명시 제공; Phase 8 provenance 가 정식 소스).
    """
    blocks = blocks_from_report(report)
    corpus = evidence_corpus_from_context(context)
    # Phase V6-8 — 명시 인자 없으면 context.provenance 에서 데이터로 끌어온다
    # (provenance 비면 [] → 가드 inert = 기존 동작, byte-equal).
    if scope_notes is None:
        scope_notes = scope_notes_from_context(context)
    if source_dates is None:
        source_dates = source_dates_from_context(context)
    if market_series is None:
        market_series = market_series_from_context(context)
    flags: list[GuardFlag] = []
    flags += unsourced_number_guard(blocks, corpus)
    flags += scope_bareword_guard(blocks, scope_notes)
    flags += novelty_delta_guard(
        blocks, publication_date or context.date, source_dates,
    )
    flags += market_data_source_guard(blocks, market_series)
    flags += nan_exposure_guard(blocks, report)
    return flags
