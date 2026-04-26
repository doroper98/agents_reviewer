"""ReportArchetype Protocol — base contract for all report archetypes.

V3 Step 2 (v2.6.0). Spec: REFACTOR_V3_PLAN.md §5 Step 2.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.models import AnalysisStrategy, ReportSectionPlan, UserIntent


@runtime_checkable
class ReportArchetype(Protocol):
    """A report archetype defines section flow + template selection for an event class.

    Implementations are *value-like* — typically singleton class instances registered
    in ``src/archetypes/registry.py``. They expose metadata (``archetype_id``, ``name``,
    ``suitable_intents``, ``suitable_event_types``) and two methods:

    - ``section_plan(strategy)``: returns the per-section plan for this archetype.
      Step 3 (block rendering) will consume the returned ``ReportSectionPlan`` list
      to render the report. In Step 2 the plan is informational only.
    - ``template_path()``: returns the Jinja template filename relative to
      ``src/templates/`` that renders this archetype.
    """

    archetype_id: str
    name: str
    suitable_intents: list[UserIntent]
    suitable_event_types: list[str]

    def section_plan(self, strategy: AnalysisStrategy) -> list[ReportSectionPlan]:
        ...

    def template_path(self) -> str:
        ...
