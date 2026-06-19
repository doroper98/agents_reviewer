"""v8.0.0 — 르포(탐사보도) 포맷 Phase 0 회귀.

report_format=reportage 트리거 라우팅 + directive 채널 복원 + 르포 장르 블록.
format=standard / directive 없을 때 기존 경로와 byte-equal (AP-V6-3 상속).
"""

from __future__ import annotations

from src.agents.narrative_composer import (
    SYSTEM_PROMPT as COMPOSER_PROMPT,
    _REPORTAGE_BLOCK,
    NarrativeComposer,
)
from src.config import Config
from src.models import ContextAnalysis
from src.token_budget import resolve_report_format, strip_reportage_trigger


# --------------------------------------------------------------------------
# 트리거 라우팅
# --------------------------------------------------------------------------


def test_resolve_format_default_standard() -> None:
    assert resolve_report_format("엔비디아 실적 분석해줘") == "standard"
    assert resolve_report_format("심층 분석") == "standard"  # mode 키워드는 무관
    assert resolve_report_format("") == "standard"


def test_resolve_format_reportage_on_trigger() -> None:
    assert resolve_report_format("르포 형식으로 반도체 공급망 분석") == "reportage"
    assert resolve_report_format("이 사건 르포로 파줘") == "reportage"


def test_strip_trigger_yields_directive() -> None:
    # 트리거 토큰을 떼어낸 나머지 = 앵글(directive).
    assert strip_reportage_trigger("르포 형식으로 반도체 공급망 분석") == "반도체 공급망 분석"
    assert strip_reportage_trigger("반도체 공급망을 르포로 파줘") == "반도체 공급망을 파줘"
    # 트리거 없으면 원문 그대로.
    assert strip_reportage_trigger("일반 분석") == "일반 분석"


# --------------------------------------------------------------------------
# 시스템 프롬프트 — 르포 블록 직교 주입
# --------------------------------------------------------------------------


def test_prompt_byte_equal_when_standard() -> None:
    nc = NarrativeComposer(Config(_env_file=None))
    assert nc._compose_system_prompt("standard") == COMPOSER_PROMPT
    assert nc._compose_system_prompt() == COMPOSER_PROMPT  # 기본 인자


def test_prompt_appends_reportage_block() -> None:
    nc = NarrativeComposer(Config(_env_file=None))
    sp = nc._compose_system_prompt("reportage")
    assert sp == COMPOSER_PROMPT + _REPORTAGE_BLOCK
    for marker in ("르포", "탐사보도", "user_directive", "5막", "발단", "이해당사자", "watch_signals"):
        assert marker in sp, f"르포 블록에 '{marker}' 누락"


def test_reportage_block_is_orthogonal_suffix() -> None:
    nc = NarrativeComposer(Config(_env_file=None))
    assert nc._compose_system_prompt("reportage").startswith(COMPOSER_PROMPT)


# --------------------------------------------------------------------------
# payload — directive 채널 (standard 면 미주입 = byte-equal)
# --------------------------------------------------------------------------


def test_payload_byte_equal_when_standard() -> None:
    ctx = ContextAnalysis(event_name="X", summary="요약")
    base = NarrativeComposer._build_unified_payload(ctx, "deep")
    fmt = NarrativeComposer._build_unified_payload(ctx, "deep", None, "standard", "무시될 텍스트")
    assert base == fmt
    assert "report_format" not in base
    assert "user_directive" not in base


def test_payload_injects_directive_when_reportage() -> None:
    ctx = ContextAnalysis(event_name="X", summary="요약")
    payload = NarrativeComposer._build_unified_payload(
        ctx, "deep", None, "reportage", "특히 자금 흐름의 내막을 파줘",
    )
    assert payload["report_format"] == "reportage"
    assert payload["user_directive"] == "특히 자금 흐름의 내막을 파줘"


def test_payload_reportage_without_directive_omits_field() -> None:
    ctx = ContextAnalysis(event_name="X", summary="요약")
    payload = NarrativeComposer._build_unified_payload(ctx, "deep", None, "reportage", "  ")
    assert payload["report_format"] == "reportage"
    assert "user_directive" not in payload  # 빈/공백 directive 는 미주입
