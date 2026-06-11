"""V7 Track B — 기승전결(起承轉結) 스크롤 아크의 섹션→단계 매핑 (REFACTOR_V7_PLAN.md §2).

freeform_essay 보고서 배경에 블러된 한자 워터마크(起/承/轉/結)를 깔고, 스크롤
진행에 따라 다음 한자가 이전 한자를 밀어올리는 연출의 *데이터 공급자*. 매핑은
결정적(0-LLM):

  - composer 가 ``ComposedSection.narrative_phase`` 를 emit 했으면 그 값을 쓰되,
    누락 칸은 직전 단계로 채운다 (LLM 부분 누락 회복).
  - 하나도 없으면 **위치 기반 폴백** — 첫 섹션=기, 마지막 본문 섹션=전, 그 사이=승.
    쟁점(contradictions)=전, 에필로그(감시 신호/타임라인/맺음)=결.
    구 JSON·recompose·flag OFF 환경에서도 항상 성공해야 한다 (AP-V7-4).

렌더는 freeform_essay.html 의 인라인 CSS/JS (템플릿에만 존재 — charts.js 같은
공유 자산을 건드리지 않아 발행본 소급 영향 0, REFACTOR_V7_PLAN.md §2.5).
flag ``V7_SCROLL_ARC`` OFF 면 synthesizer 가 본 모듈을 호출하지 않는다.
"""

from __future__ import annotations

from src.models import ComposedReport

# 단계 → 한자 글리프. 순서가 곧 스크롤 아크의 전환 순서.
ARC_ORDER: tuple[str, ...] = ("기", "승", "전", "결")
ARC_GLYPHS: dict[str, str] = {"기": "起", "승": "承", "전": "轉", "결": "結"}


def _positional_phases(n: int) -> list[str]:
    """위치 기반 결정적 폴백 — 본문 섹션 n 개의 단계 배열."""
    if n <= 0:
        return []
    if n == 1:
        return ["기"]
    if n == 2:
        return ["기", "전"]
    return ["기"] + ["승"] * (n - 2) + ["전"]


def build_scroll_arc(composed: ComposedReport) -> dict | None:
    """ComposedReport → 템플릿 컨텍스트용 스크롤 아크 매핑 dict.

    반환 형태::

        {"section_phases": ["기","승","승","전"],   # composed.sections 와 1:1
         "contradictions_phase": "전",
         "epilogue_phase": "결",
         "order": ["기","승","전","결"],
         "glyphs": {"기": "起", ...}}

    섹션이 없으면 None (배경 아크 자체를 안 그림).
    """
    sections = composed.sections or []
    if not sections:
        return None
    provided = [
        p if p in ARC_GLYPHS else ""
        for p in (getattr(s, "narrative_phase", "") for s in sections)
    ]
    if any(provided):
        # 부분 누락 회복 — 첫 칸 누락은 "기", 이후 누락은 직전 단계 계승.
        cur = "기"
        phases: list[str] = []
        for p in provided:
            if p:
                cur = p
            phases.append(cur)
    else:
        phases = _positional_phases(len(sections))
    return {
        "section_phases": phases,
        "contradictions_phase": "전",
        "epilogue_phase": "결",
        "order": list(ARC_ORDER),
        "glyphs": dict(ARC_GLYPHS),
    }
