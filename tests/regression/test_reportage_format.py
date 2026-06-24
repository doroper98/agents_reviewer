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


def test_reportage_block_has_tone_and_epilogue_rules() -> None:
    """v8.0.0 — 현재형 어투 + 에필로그 제거(timeline/closing) + '르포' 단어 금지 + 제목 차별."""
    for marker in ("현재형", "timeline_flow", "closing", "confidence_summary",
                   "'르포' 단어 금지", "서사형"):
        assert marker in _REPORTAGE_BLOCK, f"르포 블록에 '{marker}' 누락"


def test_reportage_block_has_investigative_persona() -> None:
    """v8.2.0 — 탐사 기자 페르소나(connecting dots + 시나리오 추론 + 3등급 표기) 가드.

    단순 기사 나열을 명시적으로 금지하고, 묻힌 디테일·점 잇기·가설 라벨이라는 세 도구가
    프롬프트에 명시돼야 한다. 그리고 사실/추론/가설 3등급 표기를 강제하는 어휘 marker.
    """
    # 세 가지 도구
    for marker in ("탐사 기자", "묻힌 디테일", "Connecting dots", "점 잇기", "시나리오 추론"):
        assert marker in _REPORTAGE_BLOCK, f"탐사 페르소나 블록에 '{marker}' 누락"
    # 3등급 표현 구분 + 헤지/가설 어휘
    for marker in ("표현 등급", "단정형", "헤지형", "가설", "한 가지 가설은",
                   "근거의 짜임"):
        assert marker in _REPORTAGE_BLOCK, f"3등급 표기 가드에 '{marker}' 누락"
    # 안전선
    for marker in ("fabrication", "음모론", "공허"):
        assert marker in _REPORTAGE_BLOCK, f"탐사 페르소나 안전선에 '{marker}' 누락"


def test_codex_persona_has_reportage_adaptation() -> None:
    """v8.2.0 — codex 검수자 단축본 + 전체 기준서가 르포(reportage) 인지를 갖는다.

    런타임 단축본은 표현 등급 검수와 speculation_as_fact 분류를 명시해야 하고,
    전체 기준서는 §14 르포 적응 섹션을 가져야 한다. 두 파일 정합 (CLAUDE.md SOP).
    """
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    short = (root / "prompts" / "codex_critic_persona.md").read_text(encoding="utf-8")
    full = (root / "prompts" / "market_factcheck_desk_v6.md").read_text(encoding="utf-8")
    for marker in ("reportage", "표현 등급", "speculation_as_fact", "가설 라벨"):
        assert marker in short, f"codex 단축본에 르포 적응 marker '{marker}' 누락"
        assert marker in full, f"codex 전체 기준서에 르포 적응 marker '{marker}' 누락"
    # 전체 기준서는 §14 섹션 헤더를 가져야 한다 (SOP — drift 시 정본)
    assert "### 14." in full and "르포" in full, "전체 기준서에 §14 르포 섹션 누락"


# --------------------------------------------------------------------------
# 르포 전용 테마 풀
# --------------------------------------------------------------------------


def test_reportage_theme_pool() -> None:
    from src.lens_policy import REPORTAGE_THEMES, ALL_THEMES, select_reportage_theme
    assert len(REPORTAGE_THEMES) == 8
    assert all(t.startswith("reportage_") for t in REPORTAGE_THEMES)
    # 일반 풀과 완전 분리 (교집합 0)
    assert not (set(REPORTAGE_THEMES) & set(ALL_THEMES))
    assert select_reportage_theme() in REPORTAGE_THEMES


def test_reportage_themes_defined_in_css() -> None:
    from pathlib import Path
    css = (Path(__file__).resolve().parents[2]
           / "src" / "templates" / "report.css").read_text(encoding="utf-8")
    from src.lens_policy import REPORTAGE_THEMES
    for t in REPORTAGE_THEMES:
        assert f'[data-theme="{t}"]' in css, f"report.css 에 {t} 블록 누락"
    # 르포 폰트/플랫/배지
    assert "GmarketSans" in css and 'reportage-badge' in css


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


# --------------------------------------------------------------------------
# v8.2.2 — 르포 전용 모델 (Opus 4.8), 일반은 4.7
# --------------------------------------------------------------------------


def test_reportage_uses_opus_4_8() -> None:
    nc = NarrativeComposer(Config(_env_file=None))
    assert nc._model_for_format("reportage") == "claude-opus-4-8"
    assert nc.COMPOSER_MODEL_REPORTAGE == "claude-opus-4-8"


def test_standard_keeps_opus_4_7() -> None:
    nc = NarrativeComposer(Config(_env_file=None))
    # 일반 보고서·빈 값·미지정은 모두 기존 4.7 (byte-equal 모델 경로)
    assert nc._model_for_format("standard") == "claude-opus-4-7"
    assert nc._model_for_format("") == "claude-opus-4-7"
    assert nc.COMPOSER_MODEL == "claude-opus-4-7"


def test_reviser_threads_report_format() -> None:
    """critic_loop 어댑터가 report_format 을 composer.revise_for_facts 로 전달하는지."""
    import asyncio
    from src.factcheck.critic_loop import NarrativeComposerReviser

    seen = {}

    class _StubComposer:
        async def revise_for_facts(self, report, context, *, fix_instructions,
                                   publication_date, report_format="standard"):
            seen["report_format"] = report_format
            return report

    reviser = NarrativeComposerReviser(_StubComposer())
    asyncio.run(reviser.revise_for_facts(
        object(), object(), fix_instructions=["x"],
        publication_date="2026-06-24", report_format="reportage",
    ))
    assert seen["report_format"] == "reportage"
