"""V6 Phase V6-8 — per-fact provenance 회귀.

REFACTOR_V6_PLAN.md §3 Phase V6-8. ContextAnalyst 가 provenance 를 emit 하면
NoveltyDelta/Scope 가드가 *프롬프트 없이 데이터로* 판정. flag OFF byte-equal.
"""

from __future__ import annotations

from src.agents.context_analyst import SYSTEM_PROMPT as CTX_PROMPT, ContextAnalyst
from src.config import Config
from src.factcheck.deterministic_guards import (
    run_fact_guards,
    scope_notes_from_context,
    source_dates_from_context,
)
from src.models import ComposedReport, ComposedSection, ContextAnalysis


# --------------------------------------------------------------------------
# 프롬프트 flag-gating
# --------------------------------------------------------------------------


def test_provenance_prompt_byte_equal_when_off() -> None:
    ca = ContextAnalyst(Config(_env_file=None))
    assert ca._build_system_prompt("2026-06-03") == CTX_PROMPT.replace("{current_date}", "2026-06-03")


def test_provenance_prompt_appended_when_on() -> None:
    ca = ContextAnalyst(Config(_env_file=None, enable_provenance=True))
    built = ca._build_system_prompt("2026-06-03")
    assert "사실 출처 메타" in built and "source_date" in built and "scope_note" in built


def test_recency_and_provenance_compose() -> None:
    ca = ContextAnalyst(Config(_env_file=None, enable_recency_bound=True, enable_provenance=True))
    built = ca._build_system_prompt("2026-06-03")
    assert "최신성 제한" in built and "사실 출처 메타" in built


# --------------------------------------------------------------------------
# provenance → 가드 데이터 공급
# --------------------------------------------------------------------------


def test_derive_helpers_from_provenance() -> None:
    ctx = ContextAnalysis(provenance=[
        {"fact": "x", "source_date": "2026-03-16", "scope_note": "130만=랙 전체"},
        {"fact": "y", "source_date": "", "scope_note": ""},
    ])
    assert source_dates_from_context(ctx) == ["2026-03-16"]
    assert scope_notes_from_context(ctx) == ["130만=랙 전체"]


def test_scope_guard_fires_from_provenance() -> None:
    # scope_note 가 provenance 에 있으면 명시 인자 없이도 ScopeBarewordGuard 발화.
    report = ComposedReport(
        headline="h",
        sections=[ComposedSection(heading="발표", prose="베라 루빈 보드 한 장에 130만 개")],
    )
    ctx = ContextAnalysis(provenance=[
        {"fact": "부품 수", "scope_note": "130만 = 랙(NVL72) 전체 단위. 보드/superchip 단위 아님."},
    ])
    flags = {f.flag for f in run_fact_guards(report, ctx)}
    assert "scope_bareword" in flags


def test_novelty_guard_fires_from_provenance() -> None:
    report = ComposedReport(
        headline="h",
        sections=[ComposedSection(heading="발표", prose="GR00T 상용화를 오늘 공개했다")],
    )
    ctx = ContextAnalysis(provenance=[{"fact": "GR00T", "source_date": "2026-03-16"}])
    flags = {f.flag for f in run_fact_guards(report, ctx, publication_date="2026-06-01")}
    assert "novelty_delta" in flags


def test_no_provenance_guards_inert() -> None:
    # provenance 비면 (구 데이터/flag OFF) novelty·scope 가드 inert = 기존 동작.
    report = ComposedReport(
        headline="h",
        sections=[ComposedSection(heading="발표", prose="GR00T 상용화를 오늘 공개했다. 보드 한 장에 130만 개")],
    )
    flags = {f.flag for f in run_fact_guards(report, ContextAnalysis(), publication_date="2026-06-01")}
    assert "novelty_delta" not in flags and "scope_bareword" not in flags
