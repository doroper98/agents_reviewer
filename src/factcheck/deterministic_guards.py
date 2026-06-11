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
GUARD_DUP_HEADING = "DuplicateHeadingGuard"
# V7 Track C — 기준시점 가드 2종 (REFACTOR_V7_PLAN.md §3.2, V7_REF_FRAME 게이트).
GUARD_DATE_ANCHOR = "DateAnchoredMarketGuard"
GUARD_STALE_ANCHOR = "StaleAnchorGuard"


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

# V7 — 본문 날짜 표현 ("6월 1일" / "2026-06-01" / "2026.6.1"). 기준시점 가드용.
_MD_DATE_RE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_YMD_DATE_RE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")
# 종목명 주변에서 날짜·가격을 같이 보는 윈도우 폭 (앞: 날짜 선행 / 뒤: 수치 후행).
_ANCHOR_WIN_BEFORE = 25
_ANCHOR_WIN_AFTER = 45


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


# --------------------------------------------------------------------------
# V7 Track C — 기준시점 가드 (REFACTOR_V7_PLAN.md §3.2, AP-V7-5)
# --------------------------------------------------------------------------


def market_bars_from_context(context: ContextAnalysis) -> dict[str, list[dict]]:
    """context.time_series → {종목명: [bar dict (date 오름차순)]} (V7 기준시점 가드 공급).

    market_series_from_context 와 달리 *날짜를 보존* 한다 — "수치가 어느 날짜든
    맞으면 통과" 가 아니라 날짜 앵커 판정(AP-V7-5)을 하기 위해.
    """
    out: dict[str, list[dict]] = {}
    for ts in getattr(context, "time_series", []) or []:
        if not isinstance(ts, dict):
            continue
        name = ts.get("instrument") or ts.get("name")
        bars = [
            d for d in (ts.get("data") or [])
            if isinstance(d, dict) and d.get("date") and d.get("close")
        ]
        if name and bars:
            out[name] = sorted(bars, key=lambda d: str(d["date"]))
    return out


def _window_dates(window: str, default_year: str) -> list[str]:
    """윈도우 텍스트 내 날짜 표현 → ISO 문자열 list (등장 순서)."""
    found: list[str] = []
    for m in _YMD_DATE_RE.finditer(window):
        found.append(f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
    if default_year:
        for m in _MD_DATE_RE.finditer(window):
            found.append(f"{default_year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}")
    return found


def _strip_dates(window: str) -> str:
    """날짜 표현을 공백으로 치환 — 연도(4자리)가 가격 정규식에 잡히는 오염 방지."""
    out = _YMD_DATE_RE.sub(lambda m: " " * len(m.group()), window)
    return _MD_DATE_RE.sub(lambda m: " " * len(m.group()), out)


def _bar_values(bar: dict) -> list[float]:
    vals: list[float] = []
    for k in ("open", "high", "low", "close"):
        v = bar.get(k)
        try:
            if v and float(v):
                vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return vals


def date_anchored_market_guard(
    blocks: list[ProseBlock],
    market_bars: dict[str, list[dict]],
    *,
    default_year: str = "",
    tolerance: float = 0.005,
) -> list[GuardFlag]:
    """*날짜가 명시된* 시장 수치를 **그 날짜의** bar 와 대조 (V7, AP-V7-5).

    MarketDataSourceGuard 는 "어느 종가든 맞으면 통과" (날짜 비앵커) — 그래서
    '6월 1일 코스피 2,948' 처럼 *다른 날짜의 정확한 값* 을 쓴 회귀가 통과했다.
    본 가드는 종목명 주변에 날짜+가격이 함께 있을 때 그 날짜 bar 의 OHLC 와
    대조하고, 불일치인데 *다른 날짜 종가와는 일치* 하는 시그니처만 flag (low-FP —
    아예 안 맞는 값은 기존 market_value_mismatch 가 잡는다).
    """
    flags: list[GuardFlag] = []
    for name, bars in market_bars.items():
        if not name or not bars:
            continue
        by_date = {str(b["date"]): b for b in bars}
        all_closes = [float(b["close"]) for b in bars]
        for blk in blocks:
            start = 0
            while True:
                p = blk.text.find(name, start)
                if p < 0:
                    break
                start = p + len(name)
                window = blk.text[max(0, p - _ANCHOR_WIN_BEFORE):start + _ANCHOR_WIN_AFTER]
                dates = _window_dates(window, default_year)
                if not dates:
                    continue
                bar = by_date.get(dates[0])
                if bar is None:  # 비거래일/시계열 밖 날짜 — 보수적 skip (codex 담당)
                    continue
                ohlc = _bar_values(bar)
                clean = _strip_dates(window)
                for m in _PRICE_RE.finditer(clean):
                    if clean[m.end():m.end() + 1] == "%":
                        continue
                    try:
                        got = float(_norm_num(m.group()))
                    except ValueError:
                        continue
                    if got == 0:
                        continue
                    if any(abs(got - v) / v <= tolerance for v in ohlc):
                        continue  # 해당 일자 값과 정합
                    if any(abs(got - c) / c <= tolerance for c in all_closes):
                        flags.append(
                            GuardFlag(
                                guard=GUARD_DATE_ANCHOR,
                                flag="date_anchor_mismatch",
                                location=blk.location,
                                quote=f"{name} {dates[0]} {m.group()}",
                                detail=(
                                    f"'{name}' {dates[0]} 로 인용된 수치 {got} 가 해당 일자 "
                                    "OHLC 와 불일치 — 다른 날짜의 값을 그 날짜에 귀속한 시그니처"
                                ),
                                severity="high",
                            )
                        )
    return flags


def stale_anchor_guard(
    blocks: list[ProseBlock],
    market_bars: dict[str, list[dict]],
    *,
    default_year: str = "",
    lag_bars: int = 1,
) -> list[GuardFlag]:
    """보고서의 종목별 *최신* 인용 시점이 가용 시계열보다 lag_bars 거래일 초과
    뒤처지면 flag (V7 — '6/4 종가가 있는데 본문 최신 수치가 6/1' 직격, AP-V7-5).

    FP 억제: ① 날짜+가격이 *함께* 있는 인용만 anchor 로 인정 (역사 서술 제외),
    ② 종목별 **최댓값** 만 본다 — 과거 시점을 회고하는 문장이 있어도 같은 종목의
    더 최신 인용이 하나라도 있으면 통과, ③ 직전 1거래일 lag 는 허용 (작성 중
    당일 종가 미반영 케이스 보호).
    """
    flags: list[GuardFlag] = []
    for name, bars in market_bars.items():
        if not name or not bars:
            continue
        series_dates = [str(b["date"]) for b in bars]
        cited: list[tuple[str, str]] = []  # (date, location)
        for blk in blocks:
            start = 0
            while True:
                p = blk.text.find(name, start)
                if p < 0:
                    break
                start = p + len(name)
                window = blk.text[max(0, p - _ANCHOR_WIN_BEFORE):start + _ANCHOR_WIN_AFTER]
                dates = _window_dates(window, default_year)
                if not dates:
                    continue
                clean = _strip_dates(window)
                has_price = any(
                    clean[m.end():m.end() + 1] != "%"
                    for m in _PRICE_RE.finditer(clean)
                )
                if has_price:
                    cited.append((dates[0], blk.location))
        if not cited:
            continue
        d_cited, loc = max(cited)
        after = [d for d in series_dates if d > d_cited]
        if len(after) > lag_bars:
            flags.append(
                GuardFlag(
                    guard=GUARD_STALE_ANCHOR,
                    flag="stale_anchor",
                    location=loc,
                    quote=f"{name} {d_cited}",
                    detail=(
                        f"'{name}' 본문 최신 인용 시점이 {d_cited} 인데 time_series 엔 "
                        f"그 뒤 거래일 {len(after)}일치({after[-1]} 까지)가 있음 — "
                        "최신 가용 데이터를 두고 옛 일자 수치를 채택"
                    ),
                    severity="high",
                )
            )
    return flags


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


def _norm_heading(h: str) -> str:
    return re.sub(r"[\s·,.\-–—:()]+", "", (h or "")).lower()


def duplicate_heading_guard(report: ComposedReport) -> list[GuardFlag]:
    """제목이 보고서 내에서 *중복/유사 중복* 되면 flag (사용자 지시).

    검사 대상: 일반 섹션 제목 + **쟁점(모순) 섹션 제목(`contradictions_heading`)** + 헤드라인.
    공백·구두점 무시 정규화 후 동일하면 중복으로 간주(low-FP). 동일 제목이 여러 곳에
    (특히 섹션 제목 = 쟁점 섹션 제목) 나오는 회귀를 매 보고서 결정적 검출 → loop HARD 트리거.
    """
    items: list[tuple[str, str]] = [
        ("섹션", sec.heading) for sec in report.sections if sec.heading
    ]
    if getattr(report, "contradictions_heading", ""):
        items.append(("쟁점 섹션", report.contradictions_heading))
    if report.headline:
        items.append(("헤드라인", report.headline))

    norm_map: dict[str, list[tuple[str, str]]] = {}
    for label, h in items:
        nh = _norm_heading(h)
        if nh:
            norm_map.setdefault(nh, []).append((label, h))

    flags: list[GuardFlag] = []
    for _nh, group in norm_map.items():
        if len(group) > 1:
            where = " / ".join(f"{lbl}('{h}')" for lbl, h in group)
            flags.append(
                GuardFlag(
                    guard=GUARD_DUP_HEADING,
                    flag="duplicate_heading",
                    location="headings",
                    quote=group[0][1],
                    detail=f"제목 중복 ({len(group)}곳): {where}",
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
    market_bars: dict[str, list[dict]] | None = None,
    base: bool = True,
    ref_frame: bool = False,
) -> list[GuardFlag]:
    """모든 결정적 가드를 돌려 GuardFlag 목록을 반환 (log-only — drop 안 함).

    날짜·시장·scope 부가 입력이 안 주어지면 context 에서 best-effort 로 끌어온다
    (Phase 2 단계에선 호출측이 명시 제공; Phase 8 provenance 가 정식 소스).

    V7 — ``base`` 는 V6 가드 6종 (기존 동작), ``ref_frame`` 은 기준시점 가드 2종
    (V7_REF_FRAME). 디폴트 ``base=True, ref_frame=False`` = v6.2.0 byte-equal.
    """
    blocks = blocks_from_report(report)
    flags: list[GuardFlag] = []
    if base:
        corpus = evidence_corpus_from_context(context)
        # Phase V6-8 — 명시 인자 없으면 context.provenance 에서 데이터로 끌어온다
        # (provenance 비면 [] → 가드 inert = 기존 동작, byte-equal).
        if scope_notes is None:
            scope_notes = scope_notes_from_context(context)
        if source_dates is None:
            source_dates = source_dates_from_context(context)
        if market_series is None:
            market_series = market_series_from_context(context)
        flags += unsourced_number_guard(blocks, corpus)
        flags += scope_bareword_guard(blocks, scope_notes)
        flags += novelty_delta_guard(
            blocks, publication_date or context.date, source_dates,
        )
        flags += market_data_source_guard(blocks, market_series)
        flags += nan_exposure_guard(blocks, report)
        flags += duplicate_heading_guard(report)
    if ref_frame:
        if market_bars is None:
            market_bars = market_bars_from_context(context)
        year = (publication_date or context.date or "")[:4]
        flags += date_anchored_market_guard(blocks, market_bars, default_year=year)
        flags += stale_anchor_guard(blocks, market_bars, default_year=year)
    return flags
