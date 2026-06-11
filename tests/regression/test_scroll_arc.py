"""V7 Track B — 기승전결 스크롤 아크 회귀 (REFACTOR_V7_PLAN.md §2).

가드 대상:
1. ``src/visual/scroll_arc.py`` — 위치 기반 결정적 폴백 (AP-V7-4) + composer 라벨
   부분 누락 회복. 구 JSON / flag OFF / LLM 누락에서도 항상 매핑이 성공해야 한다.
2. ``ComposedSection.narrative_phase`` — additive·Optional. 유효값 외엔 "" 회복.
3. composer ``_SCROLL_ARC_BLOCK`` — flag OFF 프롬프트 byte-equal (AP-V6-3 상속).
4. ``freeform_essay.html`` — scroll_arc 미주입 시 백드롭/속성 미렌더 (발행본과
   동일 출력), 주입 시 백드롭 + data-arc-phase + 엔진 + reduced-motion/print 숨김
   (AP-V7-2/3, 사용자 결정: reduced-motion 은 전체 숨김).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from src.models import ComposedReport, ComposedSection
from src.visual.scroll_arc import ARC_GLYPHS, ARC_ORDER, build_scroll_arc

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE_DIR = _REPO_ROOT / "src" / "templates" / "archetypes"


def _sections(n: int, phases: list[str] | None = None) -> list[ComposedSection]:
    out = []
    for i in range(n):
        kw = {"heading": f"섹션 {i + 1}", "prose": "본문."}
        if phases is not None:
            kw["narrative_phase"] = phases[i]
        out.append(ComposedSection(**kw))
    return out


# --------------------------------------------------------------------------
# 1. 결정적 폴백 매핑
# --------------------------------------------------------------------------


def test_positional_fallback_shapes() -> None:
    rep = ComposedReport(headline="h", sections=_sections(5))
    arc = build_scroll_arc(rep)
    assert arc is not None
    assert arc["section_phases"] == ["기", "승", "승", "승", "전"]
    assert arc["contradictions_phase"] == "전"
    assert arc["epilogue_phase"] == "결"
    assert arc["order"] == list(ARC_ORDER)
    assert arc["glyphs"] == ARC_GLYPHS
    # 엣지 — 짧은 보고서.
    assert build_scroll_arc(
        ComposedReport(headline="h", sections=_sections(1)),
    )["section_phases"] == ["기"]
    assert build_scroll_arc(
        ComposedReport(headline="h", sections=_sections(2)),
    )["section_phases"] == ["기", "전"]
    # 섹션 0 개 → 백드롭 자체를 안 그림.
    assert build_scroll_arc(ComposedReport(headline="h", sections=[])) is None


def test_composer_phases_used_and_gaps_inherited() -> None:
    # composer 가 일부만 라벨 — 누락 칸은 직전 단계 계승, 첫 칸 누락은 "기".
    rep = ComposedReport(
        headline="h", sections=_sections(4, ["", "승", "", "결"]),
    )
    arc = build_scroll_arc(rep)
    assert arc["section_phases"] == ["기", "승", "승", "결"]


def test_narrative_phase_validator_recovers_invalid() -> None:
    # 유효값 외 (null/영문/오타) 는 "" — 폴백 경로로 회복 (보고서 reject 금지).
    assert ComposedSection(heading="h", prose="p", narrative_phase=None).narrative_phase == ""
    assert ComposedSection(heading="h", prose="p", narrative_phase="intro").narrative_phase == ""
    assert ComposedSection(heading="h", prose="p", narrative_phase="기").narrative_phase == "기"
    # 구 JSON (필드 부재) 호환.
    assert ComposedSection(heading="h", prose="p").narrative_phase == ""


# --------------------------------------------------------------------------
# 2. composer 프롬프트 게이트
# --------------------------------------------------------------------------


def test_scroll_arc_prompt_gated() -> None:
    from src.agents.narrative_composer import (
        SYSTEM_PROMPT,
        _SCROLL_ARC_BLOCK,
        NarrativeComposer,
    )
    from src.config import Config

    off = NarrativeComposer(Config(_env_file=None))._compose_system_prompt()
    assert "narrative_phase" not in off and off == SYSTEM_PROMPT
    on = NarrativeComposer(
        Config(_env_file=None, enable_scroll_arc=True),
    )._compose_system_prompt()
    assert on == SYSTEM_PROMPT + _SCROLL_ARC_BLOCK
    for marker in ("narrative_phase", "되돌아가지 않는다", "첫 섹션은"):
        assert marker in on


# --------------------------------------------------------------------------
# 3. 템플릿 렌더 — OFF 미렌더 / ON 백드롭·속성·엔진
# --------------------------------------------------------------------------


def _render(scroll_arc: dict | None) -> str:
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=False)
    env.filters["structured"] = lambda s: s
    env.filters["strip_md"] = lambda s: s
    rep = ComposedReport(
        headline="헤드라인",
        deck="부제",
        sections=_sections(3),
        contradictions=[{"side_a": "A", "side_b": "B"}],
        watch_signals=[{"signal": "신호", "description": "설명"}],
        closing="맺음",
        confidence_score=0.8,
    )
    result = SimpleNamespace(
        composed_report=rep,
        context=SimpleNamespace(category="시장", date="2026-06-11", event_name="이벤트"),
        system_version="v7.0.0",
        revision_label="1.0",
        parent_context=None,
        blocks=[],
        report_url="",
        total_duration_seconds=1.0,
    )
    return env.get_template("freeform_essay.html").render(
        result=result,
        css_content="",
        generated_at="2026-06-11 00:00:00",
        key_summary_items=[],
        confidence_text="",
        report_theme="midnight_indigo",
        archetype_id="freeform_essay",
        archetype_name="freeform",
        report_timeline=None,
        scroll_arc=scroll_arc,
    )


def test_template_off_renders_no_backdrop() -> None:
    html = _render(None)
    for forbidden in ("arc-backdrop", "data-arc-phase", "arc-glyph"):
        assert forbidden not in html, f"flag OFF 인데 '{forbidden}' 렌더 — byte-equal 위반"


def test_template_on_renders_backdrop_attrs_and_engine() -> None:
    rep_arc = {
        "section_phases": ["기", "승", "전"],
        "contradictions_phase": "전",
        "epilogue_phase": "결",
        "order": list(ARC_ORDER),
        "glyphs": dict(ARC_GLYPHS),
    }
    html = _render(rep_arc)
    # 백드롭 + 4 글리프 (起承轉結).
    assert 'id="arc-backdrop"' in html
    for glyph in "起承轉結":
        assert glyph in html
    # 섹션·쟁점·에필로그 단계 속성.
    assert 'data-arc-phase="기"' in html
    assert 'data-arc-phase="승"' in html
    assert html.count('data-arc-phase="전"') >= 2  # 마지막 본문 섹션 + 쟁점
    assert 'data-arc-phase="결"' in html  # 감시 신호/맺음
    # 엔진 + 모션 정책 (AP-V7-2/3 + 사용자 결정: reduced-motion 전체 숨김).
    assert "prefers-reduced-motion" in html
    assert ".arc-backdrop{display:none}" in html
    assert "requestAnimationFrame" in html
    assert "pointer-events:none" in html
    # 차트·본문 레이어를 건드리지 않는 배경 전용 (z-index 음수).
    assert "z-index:-1" in html
