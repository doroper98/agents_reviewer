"""V6 Phase V6-3 — Bounded Codex critic 루프 회귀 (T-3/T-4).

REFACTOR_V6_PLAN.md §4.3. codex/Opus 실호출은 *모킹* (CI 결정적, 실연동은 VM).
검증: 루프 bound(재작성≤1·확인패스≤1) + 결정적 종료 + degrade + flag OFF byte-equal
+ 착지(unsourced drop) + 사전필터 합류.
"""

from __future__ import annotations

import asyncio

from src.config import Config
from src.factcheck.critic_loop import (
    CriticLoop,
    CriticLoopResult,
    _pretty_writer,
    build_verification_byline,
)
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
        self.report_format_seen: list[str] = []

    async def critique(self, report, context, *, publication_date="", pre_flags=None,
                       report_format=""):
        self.calls += 1
        self.pre_flags_seen.append(list(pre_flags or []))
        self.report_format_seen.append(report_format or "")
        return self._verdicts.pop(0) if self._verdicts else _clean()


class StubReviser:
    """보완 호출 기록 + 정정본 반환 (Opus 대체)."""

    def __init__(self, revised: ComposedReport | None = None, *, fail: bool = False) -> None:
        self._revised = revised
        self._fail = fail
        self.calls = 0
        self.fix_instructions_seen: list[list[str]] = []
        self.report_format_seen: list[str] = []

    async def revise_for_facts(self, report, context, *, fix_instructions, publication_date,
                               report_format="standard"):
        self.calls += 1
        self.fix_instructions_seen.append(list(fix_instructions))
        self.report_format_seen.append(report_format or "")
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


def test_duplicate_heading_hard_triggers_revision() -> None:
    # codex 가 clean 이어도 제목 중복(HARD 결정 신호)이면 revision 강제 (매 보고서 보장).
    dup = ComposedReport(headline="h", sections=[
        ComposedSection(heading="같은제목", prose="가"),
        ComposedSection(heading="같은제목", prose="나"),
    ])
    revised = ComposedReport(headline="h", sections=[
        ComposedSection(heading="첫번째", prose="가"), ComposedSection(heading="두번째", prose="나")])
    reviser = StubReviser(revised)
    loop = CriticLoop(_cfg(enable_fact_guards=True), StubCritic([_clean(), _clean()]), reviser)
    res = _run(loop.run(dup, ContextAnalysis()))
    assert reviser.calls == 1, "제목 중복이면 codex clean 이어도 강제 보완"
    assert any("duplicate_heading" in r.get("error_class", "") for r in res.claim_records)
    assert any("서로 다른" in fi for fi in reviser.fix_instructions_seen[0])


def test_clean_no_dup_still_no_revision() -> None:
    # 제목 중복 없고 codex clean 이면 보완 안 함 (기존 동작 유지).
    ok = ComposedReport(headline="h", sections=[
        ComposedSection(heading="A", prose="평범한 본문"), ComposedSection(heading="B", prose="평범한 본문")])
    reviser = StubReviser()
    loop = CriticLoop(_cfg(enable_fact_guards=True), StubCritic([_clean()]), reviser)
    res = _run(loop.run(ok, ContextAnalysis()))
    assert reviser.calls == 0 and not res.revised


def test_market_correction_hint_recomputes() -> None:
    # R1 — time_series 에서 특정일 종가·전일대비% 역산.
    from src.factcheck.critic_loop import market_correction_hint
    ctx = ContextAnalysis(date="2026-06-03", time_series=[{"instrument": "삼성전자", "data": [
        {"date": "2026-05-28", "close": 295500.0}, {"date": "2026-05-29", "close": 318500.0}]}])
    hint = market_correction_hint("삼성전자는 5월 29일 종가 기준 10.1% 뛰었다", ctx)
    assert hint and "318,500" in hint and "+7.78%" in hint and "교체" in hint
    assert market_correction_hint("없는종목 9999", ctx) is None


def test_market_claim_revision_gets_correction_hint() -> None:
    # 루프가 market 지적의 fix_instruction 에 역산 정정값을 덧대 reviser 에 전달.
    ctx = ContextAnalysis(date="2026-06-03", time_series=[{"instrument": "삼성전자", "data": [
        {"date": "2026-05-28", "close": 295500.0}, {"date": "2026-05-29", "close": 318500.0}]}])
    claim = _claim(error_class="market_data_mismatch", quote="삼성전자 5월 29일 종가 기준 10.1%")
    reviser = StubReviser(_report(prose="보완본"))
    loop = CriticLoop(_cfg(), StubCritic([_violations(claim), _clean()]), reviser)
    _run(loop.run(_report(), ctx))
    joined = " ".join(reviser.fix_instructions_seen[0])
    assert "318,500" in joined and "7.78%" in joined  # Opus 가 정확값으로 교체하게


def test_landing_drops_market_residual() -> None:
    # Phase V6-8/A — 잔존 market_data_mismatch 도 drop (틀린 시장 수치 발행 방지).
    from src.factcheck.critic_loop import apply_landing
    rep = _report(prose="삼성전자는 5월 29일 종가 기준 10.1% 뛰었다. 다음 문장은 남는다.")
    claim = _claim(error_class="market_data_mismatch", quote="삼성전자는 5월 29일 종가 기준 10.1% 뛰었다.")
    out, dropped = apply_landing(rep, [claim])
    assert "10.1%" not in out.sections[0].prose
    assert "다음 문장은 남는다" in out.sections[0].prose
    assert any("삼성" in d for d in dropped)


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


def test_audit_applied_claims_and_changes() -> None:
    # 감사 — 무엇이 식별됐고(applied_claims) 어떻게 바뀌었는지(changes) 노출.
    revised = _report(prose="베라 루빈 NVL72 랙 전체에 약 130만 부품.")
    critic = StubCritic([_violations(_claim(error_class="scope_misattribution", quote="보드 한 장 130만")), _clean()])
    loop = CriticLoop(_cfg(), critic, StubReviser(revised))
    res = _run(loop.run(_report(), ContextAnalysis()))
    # 식별: error_class + 인용구 + 보완 지시가 보인다.
    assert any("scope_misattribution" in c and "보드 한 장 130만" in c for c in res.applied_claims)
    # 변경: before→after 가 보인다 (prose 가 바뀌었으니).
    assert res.changes and any("→" in ch for ch in res.changes)


def test_audit_empty_when_clean() -> None:
    loop = CriticLoop(_cfg(), StubCritic([_clean()]), StubReviser())
    res = _run(loop.run(_report(), ContextAnalysis()))
    assert res.applied_claims == [] and res.changes == []


def test_revise_prompt_forbids_new_framing() -> None:
    # ① 예방 — 보완 프롬프트가 '새 주장/프레이밍 도입 금지'를 명시하는지.
    from src.agents.narrative_composer import NarrativeComposer
    sp = NarrativeComposer.REVISE_SYSTEM_PROMPT
    assert "새로운" in sp and ("복귀" in sp or "프레이밍" in sp)
    assert "독자 우선" in sp  # AP-V6-13 가드 유지


# --------------------------------------------------------------------------
# 진행 status (on_progress) — 텔레그램/CLI 라이브 표시
# --------------------------------------------------------------------------


def _collect_progress():
    msgs: list[str] = []

    async def cb(m):  # noqa: ANN001
        msgs.append(m)
    return msgs, cb


def test_progress_clean_path() -> None:
    msgs, cb = _collect_progress()
    loop = CriticLoop(_cfg(), StubCritic([_clean()]), StubReviser())
    _run(loop.run(_report(), ContextAnalysis(), on_progress=cb))
    assert any("교차검증 중" in m for m in msgs)   # 검수 시작
    assert any("검수 통과" in m for m in msgs)      # clean 결과
    assert not any("반영 중" in m for m in msgs)    # 보완 없음


def test_progress_violation_path() -> None:
    msgs, cb = _collect_progress()
    critic = StubCritic([_violations(_claim()), _clean()])
    loop = CriticLoop(_cfg(), critic, StubReviser(_report(prose="보완본")))
    _run(loop.run(_report(), ContextAnalysis(), on_progress=cb))
    assert any("교차검증 중" in m for m in msgs)
    assert any("반영 중" in m for m in msgs)        # Opus 보완 단계
    assert any("검수 완료" in m for m in msgs)       # 최종


def test_progress_skipped_is_honest() -> None:
    # degrade 시 "통과" 가 아니라 "건너뜀" 으로 정직하게 (AP-V6-10).
    msgs, cb = _collect_progress()
    loop = CriticLoop(_cfg(), StubCritic([FactVerdict.skip("rate_limited")]), StubReviser())
    _run(loop.run(_report(), ContextAnalysis(), on_progress=cb))
    assert any("건너뜀" in m for m in msgs)
    assert not any("검수 통과" in m for m in msgs)


def test_progress_none_is_safe() -> None:
    # on_progress 미지정이어도 정상 동작 (기존 호출 호환).
    loop = CriticLoop(_cfg(), StubCritic([_clean()]), StubReviser())
    res = _run(loop.run(_report(), ContextAnalysis()))
    assert res.initial_violations == 0


# --------------------------------------------------------------------------
# 바이라인 (Phase V6-7) — 버전 명시 + 정직 (검수 수행 시만)
# --------------------------------------------------------------------------


def test_diff_span_shows_only_changed_region() -> None:
    from src.factcheck.critic_loop import _diff_span
    o = "공통 앞부분 길게길게 어제(2일) 공통 뒷부분 길게길게 끝"
    n = "공통 앞부분 길게길게 지난 2일 공통 뒷부분 길게길게 끝"
    span = _diff_span(o, n)
    assert span is not None
    before, after = span
    # 바뀐 토큰이 before/after 에 다르게 보인다 (앞 140자 동일 회귀 해소).
    assert "어제" in before and "지난" in after
    assert before != after
    assert _diff_span("같다", "같다") is None


def test_pretty_writer_version() -> None:
    assert _pretty_writer("claude-opus-4-7") == "Claude Opus 4.7"
    assert _pretty_writer("claude-sonnet-4-6") == "Claude Sonnet 4.6"
    assert _pretty_writer("claude-opus-5") == "Claude Opus 5"  # v8.5.0
    assert _pretty_writer("") == "Claude (Opus)"


def test_byline_includes_both_versions() -> None:
    res = CriticLoopResult(
        report=_report(), initial_violations=2, unresolved_count=0,
        critic_label="OpenAI Codex (gpt-5.5)",
    )
    b = build_verification_byline(res, "claude-opus-4-7", web_verified=True)
    assert b["writer"] == "Claude Opus 4.7"
    assert "gpt-5.5" in b["critic"]
    # 한 줄에 두 모델 버전 + 지적 수 + 웹 대조 모두.
    assert "Claude Opus 4.7" in b["text"] and "gpt-5.5" in b["text"]
    assert "2건 반영" in b["text"] and "웹 대조" in b["text"]


def test_byline_clean_pass_and_unresolved() -> None:
    clean = build_verification_byline(
        CriticLoopResult(report=_report(), initial_violations=0, critic_label="OpenAI Codex (gpt-5.5)"),
        "claude-opus-4-7",
    )
    assert "지적 없음 통과" in clean["text"]
    unres = build_verification_byline(
        CriticLoopResult(report=_report(), initial_violations=3, unresolved_count=1, critic_label="OpenAI Codex (gpt-5.5)"),
        "claude-opus-4-7",
    )
    assert "3건 반영" in unres["text"] and "1건 미해결" in unres["text"]


def test_critic_label_flows_from_verdict() -> None:
    v1 = FactVerdict(claims=[_claim()], model_label="OpenAI Codex (gpt-5.5)")
    loop = CriticLoop(_cfg(), StubCritic([v1, _clean()]), StubReviser(_report(prose="보완")))
    res = _run(loop.run(_report(), ContextAnalysis()))
    assert res.critic_label == "OpenAI Codex (gpt-5.5)"


def test_skipped_has_no_critic_label() -> None:
    # degrade → critic_label 빈값 → orchestrator 가 바이라인 안 만듦 (AP-V6-10).
    loop = CriticLoop(_cfg(), StubCritic([FactVerdict.skip("rate_limited")]), StubReviser())
    res = _run(loop.run(_report(), ContextAnalysis()))
    assert res.critic_label == ""


def test_pre_flags_alone_do_not_trigger_rewrite() -> None:
    # 사전필터만 잡고 codex 가 clean 이면 재작성 안 함 (가드 FP 가 본문 안 망침).
    critic = StubCritic([_clean()])
    reviser = StubReviser()
    ctx = ContextAnalysis(background="공식 표현은 30년", date="2026-06-01")
    loop = CriticLoop(_cfg(enable_fact_guards=True), critic, reviser)
    res = _run(loop.run(_report(), ctx, publication_date="2026-06-01"))
    assert reviser.calls == 0 and not res.revised


# --------------------------------------------------------------------------
# V7 Track C — 기준시점 계약 (REFACTOR_V7_PLAN.md §3)
# --------------------------------------------------------------------------

_V7_TS = [{"instrument": "코스피", "data": [
    {"date": "2026-06-01", "close": 2901.50},
    {"date": "2026-06-02", "close": 2920.00},
    {"date": "2026-06-03", "close": 2935.40},
    {"date": "2026-06-04", "close": 2948.12},
]}]


def test_timeframe_correction_hint_uses_latest_bar() -> None:
    # 시점 지적은 인용된 옛 날짜가 아니라 *최신 가용* bar 가 정답.
    from src.factcheck.critic_loop import timeframe_correction_hint
    ctx = ContextAnalysis(date="2026-06-05", time_series=_V7_TS)
    hint = timeframe_correction_hint("6월 1일 코스피는 2,901.50으로 마감", ctx)
    assert hint and "2026-06-04" in hint and "2,948" in hint and "+0.43%" in hint
    assert "날짜를 명기" in hint
    assert timeframe_correction_hint("없는종목 9999", ctx) is None


def test_wrong_timeframe_claim_revision_gets_latest_hint() -> None:
    # 루프가 wrong_timeframe 지적의 fix_instruction 에 최신 bar 힌트를 덧대 전달.
    ctx = ContextAnalysis(date="2026-06-05", time_series=_V7_TS)
    claim = _claim(
        error_class="wrong_timeframe", quote="6월 1일 코스피는 2,901.50으로 마감",
    )
    reviser = StubReviser(_report(prose="보완본"))
    loop = CriticLoop(_cfg(), StubCritic([_violations(claim), _clean()]), reviser)
    _run(loop.run(_report(), ctx))
    joined = " ".join(reviser.fix_instructions_seen[0])
    assert "2026-06-04" in joined and "2,948" in joined


def test_landing_drops_wrong_timeframe_residual() -> None:
    # V7 — 잔존 wrong_timeframe 도 drop (정확하지만 옛 시점인 수치 무표기 발행 방지).
    from src.factcheck.critic_loop import apply_landing
    rep = _report(prose="6월 1일 코스피는 2,901.50으로 마감했다. 다음 문장은 남는다.")
    claim = _claim(
        error_class="wrong_timeframe", quote="6월 1일 코스피는 2,901.50으로 마감했다.",
    )
    out, dropped = apply_landing(rep, [claim])
    assert "2,901.50" not in out.sections[0].prose
    assert "다음 문장은 남는다" in out.sections[0].prose
    assert dropped


def test_ref_frame_guards_join_pre_flags_without_fact_guards() -> None:
    # V7_REF_FRAME 단독으로도 기준시점 가드가 pre_flags 로 합류 (V6_FACT_GUARDS 불요).
    ctx = ContextAnalysis(date="2026-06-05", time_series=_V7_TS)
    stale = _report(prose="6월 1일 코스피는 2,901.50으로 마감했고 방향성이 없다.")
    critic = StubCritic([_clean()])
    loop = CriticLoop(
        _cfg(enable_ref_frame=True), critic, StubReviser(),
    )
    _run(loop.run(stale, ctx, publication_date="2026-06-05"))
    assert any("stale_anchor" in f for f in critic.pre_flags_seen[0])


def test_ref_frame_off_no_v7_pre_flags() -> None:
    # 디폴트(OFF) — 같은 입력에서 V7 pre_flag 미합류 (byte-equal 경로).
    ctx = ContextAnalysis(date="2026-06-05", time_series=_V7_TS)
    stale = _report(prose="6월 1일 코스피는 2,901.50으로 마감했고 방향성이 없다.")
    critic = StubCritic([_clean()])
    loop = CriticLoop(_cfg(enable_fact_guards=True), critic, StubReviser())
    _run(loop.run(stale, ctx, publication_date="2026-06-05"))
    assert not any("stale_anchor" in f for f in critic.pre_flags_seen[0])
