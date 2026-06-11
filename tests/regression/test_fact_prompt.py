"""V6 Phase V6-2 — 프롬프트 하드닝 byte-equal + 주입 회귀.

composer 사실규율 블록(V6_FACT_PROMPT) + ContextAnalyst 최신성 제한(V6_RECENCY_BOUND).
둘 다 flag OFF 시 v5.8.8 프롬프트와 byte-equal, ON 시 직교 블록 추가.
"""

from __future__ import annotations

from src.agents.context_analyst import SYSTEM_PROMPT as CTX_PROMPT, ContextAnalyst
from src.agents.narrative_composer import (
    SYSTEM_PROMPT as COMPOSER_PROMPT,
    _FACT_DISCIPLINE_BLOCK,
    NarrativeComposer,
)
from src.config import Config


# --------------------------------------------------------------------------
# composer — V6_FACT_PROMPT
# --------------------------------------------------------------------------


def test_composer_prompt_byte_equal_when_off() -> None:
    nc = NarrativeComposer(Config(_env_file=None))
    assert nc._compose_system_prompt() == COMPOSER_PROMPT


def test_composer_prompt_appends_block_when_on() -> None:
    nc = NarrativeComposer(Config(_env_file=None, enable_fact_prompt=True))
    sp = nc._compose_system_prompt()
    assert sp == COMPOSER_PROMPT + _FACT_DISCIPLINE_BLOCK
    # 핵심 규율 + 등재된 anti-pattern 참조가 살아있는지.
    for marker in ("사실 규율", "랙 전체 130만", "단일 소스", "WRITE-AP-15", "WRITE-AP-16", "귀속"):
        assert marker in sp, f"규율 블록에 '{marker}' 누락"


def test_fact_block_is_orthogonal_suffix() -> None:
    # 블록은 기존 SYSTEM_PROMPT 를 *수정* 하지 않고 뒤에 붙는다 (V5 어조와 직교).
    nc_on = NarrativeComposer(Config(_env_file=None, enable_fact_prompt=True))
    assert nc_on._compose_system_prompt().startswith(COMPOSER_PROMPT)


# --------------------------------------------------------------------------
# ContextAnalyst — V6_RECENCY_BOUND
# --------------------------------------------------------------------------


def test_context_prompt_byte_equal_when_off() -> None:
    ca = ContextAnalyst(Config(_env_file=None))
    built = ca._build_system_prompt("2026-06-03")
    assert built == CTX_PROMPT.replace("{current_date}", "2026-06-03")


def test_context_prompt_appends_recency_when_on() -> None:
    ca = ContextAnalyst(Config(_env_file=None, enable_recency_bound=True))
    built = ca._build_system_prompt("2026-06-03")
    base = CTX_PROMPT.replace("{current_date}", "2026-06-03")
    assert built.startswith(base) and len(built) > len(base)
    assert "최신성 제한" in built
    assert "24~48시간" in built
    # current_date 가 recency 블록 안에서도 치환됐는지 (미치환 placeholder 없음).
    assert "{current_date}" not in built
    assert "2026-06-03" in built.split(base, 1)[1]


# --------------------------------------------------------------------------
# V7 Track C — 기준시점 계약 블록 (V7_REF_FRAME)
# --------------------------------------------------------------------------


def test_composer_prompt_byte_equal_when_ref_frame_off() -> None:
    # V7 flag 디폴트 OFF → v6.2.0 프롬프트 byte-equal (AP-V6-3 상속).
    nc = NarrativeComposer(Config(_env_file=None))
    assert "기준시점 계약" not in nc._compose_system_prompt()


def test_composer_prompt_appends_ref_frame_block_when_on() -> None:
    from src.agents.narrative_composer import _REF_FRAME_BLOCK
    nc = NarrativeComposer(Config(_env_file=None, enable_ref_frame=True))
    sp = nc._compose_system_prompt()
    assert sp == COMPOSER_PROMPT + _REF_FRAME_BLOCK
    for marker in ("기준시점 계약", "last_available_date", "WRITE-AP-22", "절대 날짜"):
        assert marker in sp, f"기준시점 블록에 '{marker}' 누락"


def test_ref_frame_and_fact_blocks_compose_orthogonally() -> None:
    from src.agents.narrative_composer import _REF_FRAME_BLOCK
    nc = NarrativeComposer(
        Config(_env_file=None, enable_fact_prompt=True, enable_ref_frame=True),
    )
    assert nc._compose_system_prompt() == (
        COMPOSER_PROMPT + _FACT_DISCIPLINE_BLOCK + _REF_FRAME_BLOCK
    )


def test_codex_prompt_gains_ref_frame_only_when_on() -> None:
    # codex 프롬프트 — flag ON 시 wrong_timeframe 계약 추가, OFF 시 byte-equal.
    from src.agents.codex_critic import CodexCritic
    from src.models import ComposedReport, ComposedSection, ContextAnalysis
    report = ComposedReport(
        headline="h", sections=[ComposedSection(heading="시장", prose="본문")],
    )
    ctx = ContextAnalysis(date="2026-06-05", time_series=[{
        "instrument": "코스피",
        "data": [{"date": "2026-06-04", "close": 2948.12}],
    }])
    off = CodexCritic(
        Config(_env_file=None, enable_codex_critic=True), persona="",
    )._build_prompt(report, ctx, publication_date="2026-06-05", pre_flags=None)
    on = CodexCritic(
        Config(_env_file=None, enable_codex_critic=True, enable_ref_frame=True),
        persona="",
    )._build_prompt(report, ctx, publication_date="2026-06-05", pre_flags=None)
    assert "wrong_timeframe" not in off and "기준시점 계약" not in off
    for marker in ("wrong_timeframe", "기준시점 계약", "2026-06-04", "2948.12"):
        assert marker in on, f"codex 기준시점 블록에 '{marker}' 누락"
    # ON 프롬프트는 OFF 프롬프트의 직교 확장 (기존 지침 보존).
    assert off.split("=== 발행일")[0] in on
