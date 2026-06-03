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
    for i, sec in enumerate(final.sections):
        if i < len(orig.sections):
            sp = _diff_span(orig.sections[i].prose, sec.prose)
            if sp:
                out.append(f"섹션 '{sec.heading}': «{sp[0]}» → «{sp[1]}»")
    return out


def apply_landing(
    report: ComposedReport, residual_claims: list,
) -> tuple[ComposedReport, list[str]]:
    """확인패스 후 잔존 위반 착지 — `unsourced_number` 계열만 결정적 drop.

    Opus 보완이 이미 헤지/교정을 수행했으므로, 여기서는 *출처 없는 특정 수치* 가
    그래도 남았을 때만 그 인용구를 본문에서 제거한다 (Claim validator 사상). 나머지
    error_class 는 surgery 하지 않는다 (FP 가 멀쩡한 본문을 망치지 않게, log-only).
    """
    drop_quotes = [
        c.quote
        for c in residual_claims
        if "unsourced" in getattr(c, "error_class", "").lower() and getattr(c, "quote", "")
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
    ) -> CriticLoopResult:
        # flag OFF → 즉시 passthrough (byte-equal, AP-V6-3). status 도 emit 안 함.
        if not self.config.enable_codex_critic:
            return CriticLoopResult(report=report, skipped=True, skip_reason="flag_off")

        # 1. 결정적 사전필터 (log-only 힌트 → Codex 에 pre_flags 로 전달).
        pre_flags: list[str] = []
        if self.config.enable_fact_guards:
            try:
                pre_flags = [
                    f.as_pre_flag()
                    for f in run_fact_guards(
                        report, context, publication_date=publication_date,
                    )
                ]
            except Exception as exc:  # noqa: BLE001
                logger.warning("[critic_loop] pre-filter guards skipped: %s", exc)

        # 2. 1차 검수.
        await self._emit(
            on_progress,
            "🔎 외부 팩트체크 데스크 (Codex): 사실·수치·시점 교차검증 중…",
        )
        v1 = await self.critic.critique(
            report, context, publication_date=publication_date, pre_flags=pre_flags,
        )
        if v1.skipped:
            # 외부 degrade → 단일패스 (AP-V6-12). 검수 안 했으니 "통과" 라 거짓말 안 함.
            await self._emit(
                on_progress, "ⓘ 외부 사실 검수 건너뜀 — 단일 패스로 발행",
            )
            return CriticLoopResult(
                report=report, skipped=True, skip_reason=v1.skip_reason,
                pre_flag_count=len(pre_flags),
            )

        # 재작성 트리거는 *Codex 위반* 에만 (사전필터 FP 가 본문을 망치지 않게).
        if not v1.is_actionable:
            await self._emit(on_progress, "✅ 사실 검수 통과 (지적 없음)")
            return CriticLoopResult(
                report=report, initial_violations=v1.violation_count,
                pre_flag_count=len(pre_flags), critic_label=v1.model_label,
            )

        # 3. Opus 보완 (≤1). Codex 지시 + 사전필터 힌트를 합산해 전달.
        await self._emit(
            on_progress,
            f"✍️ 편집장 (Opus): 검수 지적 {v1.violation_count}건 반영 중…",
        )
        # 감사용 — 검수가 식별한 지적 + 보완 지시 (무엇을 왜 고치는지).
        applied_claims = [
            f"[{c.error_class}] {c.location}: «{_clip(c.quote)}» → {_clip(c.fix_instruction, 200)}"
            for c in v1.claims
        ]
        claim_records = [
            {"error_class": c.error_class, "location": c.location, "quote": _clip(c.quote, 80)}
            for c in v1.claims
        ]
        fix_instructions = [c.fix_instruction for c in v1.claims] + pre_flags
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
        v2 = await self.critic.critique(final, context, publication_date=publication_date)
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
            initial_violations=v1.violation_count,
            residual_violations=len(residual),
            dropped_quotes=dropped,
            residual_summary=residual_summary,
            unresolved_count=len(unresolved),
            applied_claims=applied_claims,
            changes=_diff_reports(report, final),
            critic_label=v1.model_label,
            claim_records=claim_records,
        )
