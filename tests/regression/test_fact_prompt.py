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
