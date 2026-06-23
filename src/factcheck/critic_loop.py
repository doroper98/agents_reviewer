"""V6 Phase V6-3 — Bounded Codex critic 루프 (REFACTOR_V6_PLAN.md §3, 핵심).

확정 루프: **Opus 작성 → Codex 검수 → Opus 보완(≤1) → Codex 확인패스(≤1)**.

설계 (REFACTOR_V6_PLAN.md §1):
  - **루프 제어 = 0 LLM** (AP-V6-5). "보완할까" 판정은 Codex verdict 의 *위반 카운트*
    (결정적). 재작성 ≤1, 확인패스 ≤1, 결정적 종료 (위반 0 또는 cap 소진).
  - **본문 보완 = Opus** (AP-V6-1/11). Codex 는 `fix_instruction` 만 주고, 실제 재작성은
    Opus(reviser) 가 한다. Codex 는 본문 텍스트를 쓰지 않는다.
  - **사전필터 합류** — Phase 2 결정적 가드(log-only)를 Codex 에 *힌트* 로 전달
    (pre_flags). 단, 재작성 트리거는 Codex 위반에만 (가드 FP 가 본문을 망치지 않게).
  - **착지** — 확인패스 후 잔존 위반: `unsourced_number` 만 결정적 drop, 나머지는
    Opus 보완이 이미 헤지 처리(추가 surgery 안 함, log-only).
  - **graceful degrade** (AP-V6-12) — Codex skip / reviser 실패 → 원본 보존, 정상 발행.
  - **flag OFF = byte-equal** (AP-V6-3) — `V6_CODEX_CRITIC` OFF 면 즉시 passthrough.
"""

from __future__ import annotations

import logging
import re
from typing import Awaitable, Callable, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.agents.codex_critic import CodexCritic
from src.config import Config
from src.factcheck.deterministic_guards import run_fact_guards
from src.models import ComposedReport, ContextAnalysis, FactVerdict

logger = logging.getLogger(__name__)

# 결정적 가드 중 *고신뢰* — codex 와 무관하게 revision 을 강제 트리거 (FP 위험 낮음).
_HARD_TRIGGER_FLAGS = {"duplicate_heading", "nan_exposed"}


class Reviser(Protocol):
    """Opus 본문 보완자. Codex 지시를 받아 해당 부분을 재작성 (본문은 Opus 고정)."""

    async def revise_for_facts(
        self,
        report: ComposedReport,
        context: ContextAnalysis,
        *,
        fix_instructions: list[str],
        publication_date: str,
    ) -> ComposedReport: ...


class NarrativeComposerReviser:
    """`NarrativeComposer.revise_for_facts` 어댑터 (duck-typed, 순환 import 회피)."""

    def __init__(self, composer: object) -> None:
        self._composer = composer

    async def revise_for_facts(
        self,
        report: ComposedReport,
        context: ContextAnalysis,
        *,
        fix_instructions: list[str],
        publication_date: str,
    ) -> ComposedReport:
        return await self._composer.revise_for_facts(  # type: ignore[attr-defined]
            report, context,
            fix_instructions=fix_instructions,
            publication_date=publication_date,
        )


class CriticLoopResult(BaseModel):
    """루프 1회 실행 결과 + 텔레메트리."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    report: ComposedReport
    skipped: bool = False
    skip_reason: str = ""
    revised: bool = False
    confirm_ran: bool = False
    pre_flag_count: int = 0
    initial_violations: int = 0
    residual_violations: int = 0
    dropped_quotes: list[str] = Field(default_factory=list)
    # ② 가시성 — 확인패스 잔존 claim 의 사람-읽기 요약 (진단·텔레메트리).
    residual_summary: list[str] = Field(default_factory=list)
    # ③ 정직한 착지 — drop 으로도 해소 안 된 잔존 수 (≠ 0 이면 신뢰도 하향).
    unresolved_count: int = 0
    # 감사용 — 검수가 *식별* 한 지적(+보완 지시) 과 *실제* before→after 변경.
    applied_claims: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    # 바이라인용 (Phase V6-7) — 실측 검수 모델 라벨 (예: "OpenAI Codex (gpt-5.5)").
    critic_label: str = ""
    # 자율 보강용 (Phase V6-6) — 구조화 지적 (critique_log 적립). [{error_class, location, quote}]
    claim_records: list[dict] = Field(default_factory=list)


def _pretty_writer(model_id: str) -> str:
    """모델 ID → 사람-읽기 (예: 'claude-opus-4-7' → 'Claude Opus 4.7'). 바이라인용."""
    s = (model_id or "").strip()
    if not s:
        return "Claude (Opus)"
    s = s.replace("claude-", "Claude ")
    s = re.sub(
        r"(opus|sonnet|haiku)-(\d+)-(\d+)",
        lambda m: f"{m.group(1).capitalize()} {m.group(2)}.{m.group(3)}",
        s,
    )
    return s


def build_verification_byline(
    result: "CriticLoopResult", writer_model: str, *, web_verified: bool = False,
) -> dict:
    """검수 바이라인 dict (Phase V6-7). *검수 실제 수행 시에만* 호출 (AP-V6-10).

    버전 명시 — 작성=config 모델(Opus 4.7), 검수=codex 배너 실측(gpt-5.5).
    """
    writer = _pretty_writer(writer_model)
    critic = result.critic_label or "OpenAI Codex"
    if result.initial_violations == 0:
        detail = "지적 없음 통과"
    else:
        detail = f"지적 {result.initial_violations}건 반영"
        if result.unresolved_count:
            detail += f" · {result.unresolved_count}건 미해결(신뢰도 반영)"
    web = " · 웹 대조" if web_verified else ""
    return {
        "writer": writer,
        "critic": critic,
        "violations_fixed": result.initial_violations,
        "unresolved": result.unresolved_count,
        "web_verified": web_verified,
        "text": f"{writer} 작성 · {critic} 사실 검수{web} — {detail}",
    }


_MD_RE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_YMD_RE = re.compile(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})")


def _quote_date(quote: str, default_year: str) -> str | None:
    m = _YMD_RE.search(quote or "")
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = _MD_RE.search(quote or "")
    if m and default_year:
        return f"{default_year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return None


def _fmt_price(v: float) -> str:
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def market_correction_hint(quote: str, context: ContextAnalysis) -> str | None:
    """Phase V6-8/R1 — 틀린 시장 수치의 *올바른 값* 을 time_series 에서 역산해 Opus 에게
    제공 (drop 대신 교체). 인용구의 종목+날짜로 종가·전일대비% 를 계산.

    예: "삼성전자 5/29 +10.1%" → time_series 의 5/29 종가·전일종가로 실제 % 산출 →
    "[time_series 정정 참고] 삼성전자 2026-05-29 종가 318,500, 전일 대비 +7.78% …".
    매치 실패 시 None (그땐 착지 drop 으로 폴백).
    """
    year = (getattr(context, "date", "") or "")[:4] or ""
    for ts in getattr(context, "time_series", []) or []:
        if not isinstance(ts, dict):
            continue
        name = ts.get("instrument") or ts.get("name")
        data = ts.get("data") or []
        if not name or name not in (quote or "") or not data:
            continue
        target = _quote_date(quote, year)
        idx = None
        if target:
            for k, b in enumerate(data):
                if isinstance(b, dict) and b.get("date") == target:
                    idx = k
                    break
            if idx is None:  # 정확 날짜 없으면 그 이하 가장 가까운 거래일
                cands = [
                    k for k, b in enumerate(data)
                    if isinstance(b, dict) and b.get("date") and b["date"] <= target
                ]
                idx = cands[-1] if cands else None
        if idx is None:
            idx = len(data) - 1
        bar = data[idx]
        close = bar.get("close") if isinstance(bar, dict) else None
        if not close:
            continue
        prior = (
            data[idx - 1].get("close")
            if idx > 0 and isinstance(data[idx - 1], dict) else None
        )
        parts = [f"{name} {bar.get('date', '')} 종가 {_fmt_price(float(close))}"]
        if prior:
            pct = (float(close) - float(prior)) / float(prior) * 100
            parts.append(f"전일 대비 {pct:+.2f}%")
        return (
            "[time_series 정정 참고] " + ", ".join(parts)
            + " — 본문의 해당 시장 수치를 이 값으로 교체하라(삭제 말 것)."
        )
    return None


def timeframe_correction_hint(quote: str, context: ContextAnalysis) -> str | None:
    """V7 Track C — wrong_timeframe/stale_anchor 지적의 *최신 가용* 값을 time_series 에서
    역산해 Opus 에게 제공 (REFACTOR_V7_PLAN.md §3.5).

    market_correction_hint 는 인용구의 *그 날짜* bar 를 찾지만 (틀린 수치 교정), 시점
    지적은 반대로 **마지막 bar** 가 정답 — "옛 날짜 기준으로 정확" 한 수치를 최신 시점
    값으로 갈아끼우게 한다. 매치 실패 시 None (그땐 착지 drop 으로 폴백).
    """
    for ts in getattr(context, "time_series", []) or []:
        if not isinstance(ts, dict):
            continue
        name = ts.get("instrument") or ts.get("name")
        data = [
            d for d in (ts.get("data") or [])
            if isinstance(d, dict) and d.get("date") and d.get("close")
        ]
        if not name or name not in (quote or "") or not data:
            continue
        data = sorted(data, key=lambda d: str(d["date"]))
        bar = data[-1]
        parts = [f"{name} 최신 가용 {bar['date']} 종가 {_fmt_price(float(bar['close']))}"]
        if len(data) > 1 and data[-2].get("close"):
            prior = float(data[-2]["close"])
            pct = (float(bar["close"]) - prior) / prior * 100
            parts.append(f"전일 대비 {pct:+.2f}%")
        return (
            "[기준시점 정정 참고] " + ", ".join(parts)
            + " — 본문의 해당 시장 수치를 이 *최신 시점* 값으로 교체하고 날짜를 명기하라"
            "(옛 날짜 값을 유지하려면 절대 날짜와 사유를 본문에 명시할 것, 삭제는 말 것)."
        )
    return None


def _clip(s: str, n: int = 140) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n] + "…"


def _diff_span(old: str, new: str, ctx: int = 30) -> tuple[str, str] | None:
    """변경된 *부분만* + 앞뒤 문맥. 공통 prefix/suffix 제거 (긴 본문에서 1단어
    바뀌어도 그 부분만 보이게 — 섹션 앞 140자 클립의 '위아래 동일' 회귀 해소)."""
    old = (old or "").replace("\n", " ")
    new = (new or "").replace("\n", " ")
    if old == new:
        return None
    m = min(len(old), len(new))
    i = 0
    while i < m and old[i] == new[i]:
        i += 1
    j = 0
    while j < (m - i) and old[len(old) - 1 - j] == new[len(new) - 1 - j]:
        j += 1
    o_start, o_end = max(0, i - ctx), len(old) - j + ctx
    n_start, n_end = max(0, i - ctx), len(new) - j + ctx
    op = ("…" if o_start > 0 else "") + old[o_start:o_end].strip() + ("…" if o_end < len(old) else "")
    npv = ("…" if n_start > 0 else "") + new[n_start:n_end].strip() + ("…" if n_end < len(new) else "")
    return op, npv


def _diff_reports(orig: ComposedReport, final: ComposedReport) -> list[str]:
    """원본 → 최종 보고서의 *바뀐 부분만* 사람-읽기 목록으로 (감사용)."""
    out: list[str] = []
    hd = _diff_span(orig.headline, final.headline)
    if hd:
        out.append(f"headline: «{hd[0]}» → «{hd[1]}»")
    dk = _diff_span(orig.deck, final.deck)
    if dk:
        out.append(f"deck: «{dk[0]}» → «{dk[1]}»")
    ch = _diff_span(orig.contradictions_heading, final.contradictions_heading)
    if ch:
        out.append(f"쟁점 제목: «{ch[0]}» → «{ch[1]}»")
    for i, sec in enumerate(final.sections):
        if i < len(orig.sections):
            sp = _diff_span(orig.sections[i].prose, sec.prose)
            if sp:
                out.append(f"섹션 '{sec.heading}': «{sp[0]}» → «{sp[1]}»")
    return out


def apply_landing(
    report: ComposedReport, residual_claims: list,
) -> tuple[ComposedReport, list[str]]:
    """확인패스 후 잔존 위반 착지 — `unsourced_number`·`market_data_mismatch`·
    `wrong_timeframe` 결정적 drop.

    Opus 보완이 이미 헤지/교정을 수행했으므로, 여기서는 *출처 없는 특정 수치* 와 *틀린
    시장 수치* 가 그래도 남았을 때만 그 인용구를 본문에서 제거한다 (시장 수치는 최우선 —
    틀린 채 발행하느니 빼는 게 낫다, WRITE-AP-15 / Phase V6-8/A). V7 — *시점이 틀린*
    시장 수치(wrong_timeframe)도 동급으로 drop: 정확하지만 옛 날짜인 수치를 무표기로
    내보내는 것이 무수치보다 해롭다 (WRITE-AP-22, REFACTOR_V7_PLAN.md §3.6). 그 외
    error_class 는 surgery 하지 않는다 (FP 가 멀쩡한 본문을 망치지 않게, log-only).
    """
    drop_quotes = [
        c.quote
        for c in residual_claims
        if any(
            k in getattr(c, "error_class", "").lower()
            for k in ("unsourced", "market", "wrong_timeframe")
        )
        and getattr(c, "quote", "")
    ]
    if not drop_quotes:
        return report, []

    new = report.model_copy(deep=True)
    dropped: list[str] = []

    def _strip(text: str) -> str:
        out = text
        for q in drop_quotes:
            if q and q in out:
                out = out.replace(q, "")
                if q not in dropped:
                    dropped.append(q)
        # 제거로 생긴 이중 공백·고아 구두점 정리.
        out = re.sub(r"\s{2,}", " ", out)
        out = re.sub(r"\s+([,.)\]])", r"\1", out).strip()
        return out

    new.headline = _strip(new.headline)
    new.deck = _strip(new.deck)
    for sec in new.sections:
        sec.prose = _strip(sec.prose)
    if dropped:
        logger.info("[critic_loop] landing dropped unsourced quote(s): %s", dropped)
    return new, dropped


class CriticLoop:
    """Bounded Codex critic 루프 오케스트레이터."""

    def __init__(self, config: Config, critic: CodexCritic, reviser: Reviser) -> None:
        self.config = config
        self.critic = critic
        self.reviser = reviser

    @staticmethod
    async def _emit(cb: "Callable[[str], Awaitable[None]] | None", msg: str) -> None:
        """진행 status 1건 송신 (텔레그램/CLI). 실패가 검수를 막지 않는다."""
        if cb is None:
            return
        try:
            await cb(msg)
        except Exception:  # noqa: BLE001
            logger.debug("[critic_loop] progress emit failed", exc_info=True)

    async def run(
        self,
        report: ComposedReport,
        context: ContextAnalysis,
        *,
        publication_date: str = "",
        on_progress: "Callable[[str], Awaitable[None]] | None" = None,
        report_format: str = "",
    ) -> CriticLoopResult:
        # flag OFF → 즉시 passthrough (byte-equal, AP-V6-3). status 도 emit 안 함.
        if not self.config.enable_codex_critic:
            return CriticLoopResult(report=report, skipped=True, skip_reason="flag_off")

        # 1. 결정적 사전필터 (log-only 힌트 → Codex 에 pre_flags 로 전달).
        # 1. 결정적 사전필터. 대부분은 codex 힌트(soft)지만, *고신뢰* 결정 신호(제목
        #    중복·NaN)는 codex 와 무관하게 revision 을 *강제 트리거* 한다 (HARD).
        guard_flags = []
        if self.config.enable_fact_guards or self.config.enable_ref_frame:
            try:
                guard_flags = run_fact_guards(
                    report, context, publication_date=publication_date,
                    base=self.config.enable_fact_guards,
                    ref_frame=self.config.enable_ref_frame,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[critic_loop] pre-filter guards skipped: %s", exc)
        pre_flags: list[str] = [f.as_pre_flag() for f in guard_flags]
        hard_flags = [f for f in guard_flags if f.flag in _HARD_TRIGGER_FLAGS]

        # 2. 1차 검수.
        await self._emit(
            on_progress,
            "🔎 외부 팩트체크 데스크 (Codex): 사실·수치·시점 교차검증 중…",
        )
        v1 = await self.critic.critique(
            report, context, publication_date=publication_date, pre_flags=pre_flags,
            report_format=report_format,
        )
        if v1.skipped:
            # 외부 degrade → 단일패스 (AP-V6-12). 검수 안 했으니 "통과" 라 거짓말 안 함.
            # (codex degrade 시엔 byline 정합 위해 hard 보완도 생략 — 결정 신호는 로그로 남음.)
            await self._emit(
                on_progress, "ⓘ 외부 사실 검수 건너뜀 — 단일 패스로 발행",
            )
            return CriticLoopResult(
                report=report, skipped=True, skip_reason=v1.skip_reason,
                pre_flag_count=len(pre_flags),
            )

        # 재작성 트리거 = Codex 위반 *또는* HARD 결정 신호 (제목 중복·NaN).
        if not v1.is_actionable and not hard_flags:
            await self._emit(on_progress, "✅ 사실 검수 통과 (지적 없음)")
            return CriticLoopResult(
                report=report, initial_violations=v1.violation_count,
                pre_flag_count=len(pre_flags), critic_label=v1.model_label,
            )

        # 3. Opus 보완 (≤1). Codex 지시 + HARD 결정 신호 + 사전필터 힌트.
        n_total = v1.violation_count + len(hard_flags)
        await self._emit(
            on_progress,
            f"✍️ 편집장 (Opus): 검수 지적 {n_total}건 반영 중…",
        )
        # HARD 결정 신호의 강제 교정 지시 (제목 중복·NaN).
        hard_instr: list[str] = []
        for f in hard_flags:
            if f.flag == "duplicate_heading":
                hard_instr.append(
                    f"[중대·강제] {f.detail}. 겹치는 제목들(섹션 제목 / 쟁점 섹션 제목 "
                    "contradictions_heading / 헤드라인 포함)을 각각 그 부분 내용에 맞는 "
                    "*서로 다른* 제목으로 반드시 바꿔라(같은 제목 두 곳 금지)."
                )
            else:
                hard_instr.append(f"[{f.location}] {f.detail} — 제거/정정.")
        # 감사용 — 검수가 식별한 지적 + 보완 지시 (무엇을 왜 고치는지).
        applied_claims = [
            f"[{c.error_class}] {c.location}: «{_clip(c.quote)}» → {_clip(c.fix_instruction, 200)}"
            for c in v1.claims
        ] + [f"[{f.flag}] {f.detail}" for f in hard_flags]
        claim_records = [
            {"error_class": c.error_class, "location": c.location, "quote": _clip(c.quote, 80)}
            for c in v1.claims
        ] + [
            {"error_class": f.flag, "location": f.location, "quote": _clip(f.quote, 80)}
            for f in hard_flags
        ]
        # R1 — 시장 수치 지적엔 time_series 역산 정정값을 fix_instruction 에 덧대 Opus 가
        # *교체* 하게 (drop 폴백 전에). 매치 실패 시 원 지시 그대로.
        fix_instructions: list[str] = []
        for c in v1.claims:
            instr = c.fix_instruction
            ec = (c.error_class or "").lower()
            if "market" in ec:
                hint = market_correction_hint(c.quote, context)
                if hint:
                    instr = f"{instr} {hint}"
            elif "timeframe" in ec or "stale_anchor" in ec:
                # V7 — 시점 지적은 최신 가용 bar 가 정답 (틀린 날짜 bar 가 아니라).
                hint = timeframe_correction_hint(c.quote, context)
                if hint:
                    instr = f"{instr} {hint}"
            fix_instructions.append(instr)
        fix_instructions += hard_instr
        fix_instructions += pre_flags
        final = report
        revised_ok = False
        try:
            candidate = await self.reviser.revise_for_facts(
                report, context,
                fix_instructions=fix_instructions,
                publication_date=publication_date,
            )
            if isinstance(candidate, ComposedReport) and candidate.headline and candidate.sections:
                final = candidate
                revised_ok = True
        except Exception as exc:  # noqa: BLE001 — 보완 실패가 발행을 막지 않음
            logger.warning("[critic_loop] reviser failed, keeping original: %s", exc)

        # 4. 확인패스 (≤1, 재작성 없음 — 검증만).
        v2 = await self.critic.critique(
            final, context, publication_date=publication_date,
            report_format=report_format,
        )
        residual = [] if v2.skipped else list(v2.claims)

        # 5. 착지 — unsourced 잔존만 결정적 drop.
        final, dropped = apply_landing(final, residual)

        # ② 잔존 가시화 + ③ 정직한 착지.
        residual_summary = [
            f"[{c.error_class}] {c.location}: {c.quote}" for c in residual
        ]
        unresolved = [c for c in residual if getattr(c, "quote", "") not in dropped]
        if unresolved:
            final = final.model_copy(deep=True)
            final.confidence_score = max(
                0.3, round(final.confidence_score - 0.1 * len(unresolved), 3),
            )

        # 최종 status — 정직하게. "정정"(=drop)이 아니라 "보완 반영"으로 표기
        # (Opus 가 본문을 고친 것을 0건처럼 보이게 하던 회귀 해소).
        if not residual:
            await self._emit(
                on_progress,
                f"✅ 사실 검수 완료 — 지적 {v1.violation_count}건 보완 반영",
            )
        else:
            _parts = [f"지적 {v1.violation_count}건 보완 반영"]
            if dropped:
                _parts.append(f"{len(dropped)}건 삭제")
            if unresolved:
                _parts.append(f"{len(unresolved)}건 미해결(신뢰도 반영)")
            await self._emit(
                on_progress, "✅ 사실 검수·보완 완료 — " + ", ".join(_parts),
            )

        return CriticLoopResult(
            report=final,
            revised=revised_ok,
            confirm_ran=not v2.skipped,
            pre_flag_count=len(pre_flags),
            initial_violations=n_total,
            residual_violations=len(residual),
            dropped_quotes=dropped,
            residual_summary=residual_summary,
            unresolved_count=len(unresolved),
            applied_claims=applied_claims,
            changes=_diff_reports(report, final),
            critic_label=v1.model_label,
            claim_records=claim_records,
        )
