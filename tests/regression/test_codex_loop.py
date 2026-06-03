"""V6 Phase V6-3 — Bounded Codex critic 루프 회귀 (T-3/T-4).

REFACTOR_V6_PLAN.md §4.3. codex/Opus 실호출은 *모킹* (CI 결정적, 실연동은 VM).
검증: 루프 bound(재작성≤1·확인패스≤1) + 결정적 종료 + degrade + flag OFF byte-equal
+ 착지(unsourced drop) + 사전필터 합류.
"""

from __future__ import annotations

import asyncio

from src.config import Config
from src.factcheck.critic_loop import CriticLoop, CriticLoopResult
from src.models import (
    ComposedReport,
    ComposedSection,
    ContextAnalysis,
    CritiqueClaim,
    FactVerdict,
)


# --------------------------------------------------------------------------
# 스텁
# --------------------------------------------------------------------------


def _claim(error_class="unsourced_number", quote="27년 만의", location="발표 요지") -> CritiqueClaim:
    return CritiqueClaim(
        location=location, error_class=error_class, quote=quote,
        evidence_conflict="근거에 없음", fix_instruction=f"{quote} 교정",
        severity="high",
    )


def _clean() -> FactVerdict:
    return FactVerdict()


def _violations(*claims) -> FactVerdict:
    return FactVerdict(claims=list(claims) or [_claim()])


class StubCritic:
    """순차 verdict 큐 + 호출 기록 (codex 대체)."""

    def __init__(self, verdicts: list[FactVerdict]) -> None:
        self._verdicts = list(verdicts)
        self.calls = 0
        self.pre_flags_seen: list[list[str]] = []

    async def critique(self, report, context, *, publication_date="", pre_flags=None):
        self.calls += 1
        self.pre_flags_seen.append(list(pre_flags or []))
        return self._verdicts.pop(0) if self._verdicts else _clean()


class StubReviser:
    """보완 호출 기록 + 정정본 반환 (Opus 대체)."""

    def __init__(self, revised: ComposedReport | None = None, *, fail: bool = False) -> None:
        self._revised = revised
        self._fail = fail
        self.calls = 0
        self.fix_instructions_seen: list[list[str]] = []

    async def revise_for_facts(self, report, context, *, fix_instructions, publication_date):
        self.calls += 1
        self.fix_instructions_seen.append(list(fix_instructions))
        if self._fail:
            raise RuntimeError("opus revise failed")
        return self._revised if self._revised is not None else report


def _report(prose="베라 루빈 보드 한 장에 부품이 130만 개. 27년 만의 칩.") -> ComposedReport:
    return ComposedReport(
        headline="27년 만의 PC 칩",
        sections=[ComposedSection(heading="발표 요지", prose=prose)],
    )


def _cfg(**kw) -> Config:
    base = dict(enable_codex_critic=True)
    base.update(kw)
    return Config(_env_file=None, **base)


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------
# flag OFF / degrade — passthrough
# --------------------------------------------------------------------------


def test_flag_off_passthrough_no_critic_call() -> None:
    critic = StubCritic([_violations()])
    reviser = StubReviser()
    rep = _report()
    loop = CriticLoop(_cfg(enable_codex_critic=False), critic, reviser)
    res = _run(loop.run(rep, ContextAnalysis()))
    assert res.skipped and res.skip_reason == "flag_off"
    assert res.report is rep  # byte-equal — 원본 그대로
    assert critic.calls == 0 and reviser.calls == 0


def test_degrade_skipped_verdict_passthrough() -> None:
    critic = StubCritic([FactVerdict.skip("rate_limited")])
    reviser = StubReviser()
    rep = _report()
    loop = CriticLoop(_cfg(), critic, reviser)
    res = _run(loop.run(rep, ContextAnalysis()))
    assert res.skipped and res.skip_reason == "rate_limited"
    assert res.report is rep
    assert critic.calls == 1 and reviser.calls == 0  # 보완·확인 안 함


# --------------------------------------------------------------------------
# T-3 — 정상 수렴
# --------------------------------------------------------------------------


def test_clean_first_verdict_no_revision() -> None:
    critic = StubCritic([_clean()])
    reviser = StubReviser()
    loop = CriticLoop(_cfg(), critic, reviser)
    res = _run(loop.run(_report(), ContextAnalysis()))
    assert not res.revised and reviser.calls == 0
    assert critic.calls == 1  # 확인패스도 안 함 (위반 0)
    assert res.initial_violations == 0


def test_violation_then_revise_then_clean_confirm() -> None:
    revised = _report(prose="베라 루빈 NVL72 랙 전체에 약 130만 부품.")
    critic = StubCritic([_violations(_claim()), _clean()])
    reviser = StubReviser(revised)
    loop = CriticLoop(_cfg(), critic, reviser)
    res = _run(loop.run(_report(), ContextAnalysis()))
    assert res.revised is True and reviser.calls == 1
    assert res.confirm_ran is True and critic.calls == 2
    assert res.residual_violations == 0
    assert res.report.sections[0].prose == revised.sections[0].prose


def test_residual_unsourced_dropped_at_landing() -> None:
    # 보완 후에도 unsourced 가 남으면 착지에서 결정적 drop → unresolved 0 (해소됨).
    still_bad = _report(prose="여전히 27년 만의 칩이라는 표현이 남아있다.")
    critic = StubCritic([
        _violations(_claim()),
        _violations(_claim(quote="27년 만의")),  # 확인패스에 잔존
    ])
    reviser = StubReviser(still_bad)
    loop = CriticLoop(_cfg(), critic, reviser)
    res = _run(loop.run(_report(), ContextAnalysis()))
    assert "27년 만의" in res.dropped_quotes
    assert "27년 만의" not in res.report.sections[0].prose
    # drop 으로 해소됐으니 미해결 0, 신뢰도 하향 없음.
    assert res.unresolved_count == 0


# --------------------------------------------------------------------------
# T-4 — bound (재작성 ≤1, 확인패스 ≤1, 결정적 종료)
# --------------------------------------------------------------------------


def test_bounded_single_rewrite_even_if_confirm_still_violates() -> None:
    # 확인패스에 *비-unsourced* 위반이 남아도 2차 재작성·3차 검수 안 함.
    critic = StubCritic([
        _violations(_claim(error_class="causal_overreach", quote="직격탄")),
        _violations(_claim(error_class="causal_overreach", quote="직격탄")),
    ])
    reviser = StubReviser(_report(prose="보완본"))
    loop = CriticLoop(_cfg(), critic, reviser)
    res = _run(loop.run(_report(), ContextAnalysis()))
    assert reviser.calls == 1, "재작성은 정확히 1회 (bound)"
    assert critic.calls == 2, "검수 1 + 확인패스 1 = 2회 (bound)"
    assert res.residual_violations == 1
    assert res.dropped_quotes == []  # causal 은 drop 대상 아님 (헤지는 Opus 가 이미)
    # ② 가시성: 잔존이 요약으로 남는다. ③ 정직: 미해결 1 → 신뢰도 하향.
    assert res.unresolved_count == 1
    assert any("causal_overreach" in s and "직격탄" in s for s in res.residual_summary)
    assert res.report.confidence_score < 0.5  # 정직한 하향 (default 0.5 → 0.4)


def test_reviser_failure_keeps_original_but_confirms() -> None:
    critic = StubCritic([_violations(_claim()), _clean()])
    reviser = StubReviser(fail=True)
    rep = _report()
    loop = CriticLoop(_cfg(), critic, reviser)
    res = _run(loop.run(rep, ContextAnalysis()))
    assert res.revised is False  # 보완 실패
    assert reviser.calls == 1 and critic.calls == 2  # 확인패스는 원본으로 진행
    assert res.report.sections[0].prose == rep.sections[0].prose


# --------------------------------------------------------------------------
# 사전필터 합류 (Phase 2 → Phase 3)
# --------------------------------------------------------------------------


def test_pre_flags_passed_to_critic_when_guards_enabled() -> None:
    # enable_fact_guards 켜면 결정적 가드 신호가 codex 1차 검수에 pre_flags 로 전달.
    critic = StubCritic([_clean()])
    reviser = StubReviser()
    ctx = ContextAnalysis(background="공식 표현은 30년", date="2026-06-01")
    loop = CriticLoop(_cfg(enable_fact_guards=True), critic, reviser)
    res = _run(loop.run(_report(), ctx, publication_date="2026-06-01"))
    # 본문 "27년 만" 이 근거(30년)에 없으니 사전필터가 잡아 pre_flags 에 실림.
    assert res.pre_flag_count >= 1
    assert any("unsourced" in f for f in critic.pre_flags_seen[0])


def test_clean_convergence_no_confidence_penalty() -> None:
    # 위반→보완→확인 clean 이면 미해결 0, 신뢰도 그대로 (잔존 없음).
    revised = _report(prose="정확히 교정된 본문.")
    critic = StubCritic([_violations(_claim()), _clean()])
    loop = CriticLoop(_cfg(), critic, StubReviser(revised))
    res = _run(loop.run(_report(), ContextAnalysis()))
    assert res.unresolved_count == 0 and res.residual_summary == []
    assert res.report.confidence_score == 0.5  # 하향 없음


def test_revise_prompt_forbids_new_framing() -> None:
    # ① 예방 — 보완 프롬프트가 '새 주장/프레이밍 도입 금지'를 명시하는지.
    from src.agents.narrative_composer import NarrativeComposer
    sp = NarrativeComposer.REVISE_SYSTEM_PROMPT
    assert "새로운" in sp and ("복귀" in sp or "프레이밍" in sp)
    assert "독자 우선" in sp  # AP-V6-13 가드 유지


def test_pre_flags_alone_do_not_trigger_rewrite() -> None:
    # 사전필터만 잡고 codex 가 clean 이면 재작성 안 함 (가드 FP 가 본문 안 망침).
    critic = StubCritic([_clean()])
    reviser = StubReviser()
    ctx = ContextAnalysis(background="공식 표현은 30년", date="2026-06-01")
    loop = CriticLoop(_cfg(enable_fact_guards=True), critic, reviser)
    res = _run(loop.run(_report(), ctx, publication_date="2026-06-01"))
    assert reviser.calls == 0 and not res.revised
