"""freeform_essay archetype (v3.3.0) — Opus 4.7 narrative composer 출력 렌더링.

이 archetype 은 *데이터를 정형 슬롯에 부어넣지 않는다*. composer 가 자유 형식으로
짠 ``ComposedReport`` (sections, embedded_charts, embedded_blocks) 를 그대로 렌더.

매칭은 select_archetype() 의 priority 가 아니라 orchestrator 가 deep 모드 +
narrative_composer 성공 시 *명시적으로* 라우팅한다 (registry lookup 으로만 진입).

section_plan() 은 호환을 위해 빈 리스트 반환 — composer 출력이 SSOT 라서 strategy 의
section_plan 에 의존하지 않는다.
"""

from __future__ import annotations

from src.models import AnalysisStrategy, ReportSectionPlan


class FreeformEssayArchetype:
    archetype_id: str = "freeform_essay"
    name: str = "Freeform Essay"
    # 자유 형식이라 특정 intent/event_type 에 묶지 않음. 모드 기반 라우팅 (deep) 만.
    suitable_intents: list = []
    suitable_event_types: list[str] = []

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        # composer 가 ComposedReport.sections 로 SSOT 를 보유. strategy.section_plan
        # 은 본 archetype 에선 무의미하므로 빈 리스트.
        return []

    def template_path(self) -> str:
        return "archetypes/freeform_essay.html"


ARCHETYPE = FreeformEssayArchetype()
