"""ReportArchetype Protocol — base contract for all report archetypes.

V3 Step 2 (v2.6.0). Spec: REFACTOR_V3_PLAN.md §5 Step 2.
PR3 (v3.4.6): contract() 메서드 추가 — AMC.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.models import (
    AnalysisMethodContract,
    AnalysisStrategy,
    ReportSectionPlan,
    UserIntent,
)


@runtime_checkable
class ReportArchetype(Protocol):
    """A report archetype defines section flow + template selection for an event class.

    Implementations are *value-like* — typically singleton class instances registered
    in ``src/archetypes/registry.py``. They expose metadata (``archetype_id``, ``name``,
    ``suitable_intents``, ``suitable_event_types``) and three methods:

    - ``section_plan(strategy)``: returns the per-section plan for this archetype.
      각 ``ReportSectionPlan`` 는 PR3 부터 ``narrative_stage`` 를 선언할 수 있다
      (fact / mechanism / divergence / decision / trigger).
    - ``template_path()``: returns the Jinja template filename.
    - ``contract()``: returns an ``AnalysisMethodContract`` declaring which narrative
      stages this archetype must cover and which block types are forbidden. PR3 (AMC).
    """

    archetype_id: str
    name: str
    suitable_intents: list[UserIntent]
    suitable_event_types: list[str]

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        ...

    def template_path(self) -> str:
        ...


def default_contract(archetype_id: str) -> AnalysisMethodContract:
    """PR3: archetype 이 contract() 를 선언하지 않을 때의 기본값.

    아무 stage 도 강제하지 않고 아무 block 도 금지하지 않는 *느슨한* 계약 —
    backward-compat. archetype 작성자가 contract() 를 명시 선언하면 강한 보증.
    """
    return AnalysisMethodContract(method_id=archetype_id)
